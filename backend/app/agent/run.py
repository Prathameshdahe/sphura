"""The live context of one chat turn: what the graph nodes read and write besides the JSON state.

`Turn` is the request (user, conversation, question, model); `AgentRun` carries the non-serialisable objects
(stop event, source registry, steps, the SSE emitter) and offers the same small surface the memory / verify
plugin code was written against (`phase`, `step_start`, `step_end`, `emit`, `registry`, `extra_system`,
`meta_extra`, `content`, `status`), so those modules run unchanged from graph nodes.

Inside a graph node every event goes through LangGraph's custom stream writer (set by `attach`), which keeps
status/step/sources/verification events ordered with the streamed tokens.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.agent.sources import SourceRegistry
from app.agent.store import message_out, utc_iso
from app.db.base import session_scope
from app.db.models import Conversation, Message
from app.llm.types import LLMError, ResolvedModel

log = logging.getLogger("sphura.agent")

Emit = Callable[[str, dict[str, Any]], None]
GENERIC_ERROR = "Something went wrong while answering. Please try again."

_runs: dict[str, AgentRun] = {}
current_run: contextvars.ContextVar[AgentRun | None] = contextvars.ContextVar("sphura_current_run", default=None)


@dataclass
class Turn:
    user_id: str
    conversation_id: str
    is_new: bool
    question: str
    history: list[dict[str, str]]
    doc_ids: list[str]
    web_search: bool
    mode: str
    effort: str
    model: ResolvedModel
    workspace_id: str | None = None  # kept for the verify plugin's signature; always None now
    assistant_message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AgentRun:
    """Mutable per-turn context shared by the API layer, the stream mapper and the graph nodes."""

    def __init__(self, turn: Turn, emit: Emit, stop: asyncio.Event | None = None) -> None:
        self.turn = turn
        self.model = turn.model
        self.stop = stop or asyncio.Event()
        self._emit = emit
        self.registry = SourceRegistry()
        self.steps: list[dict[str, Any]] = []
        self.content = ""          # the answer as the graph knows it (state["draft"])
        self.streamed = ""         # the answer as the client received it (deltas)
        self.usage = {"promptTokens": 0, "completionTokens": 0}
        self.status = "complete"
        self.error: str | None = None
        self.title: str | None = None
        self.fallbacks: list[str] = []
        self.extra_system: list[str] = []
        self.meta_extra: dict[str, Any] = {}
        self.notes: list[str] = []
        self.charts: list[dict[str, Any]] = []  # computed chart specs verify appends (app.agent.charts)
        self.searches: list[str] = []
        self.intent: str = "explain"
        self.tools_ok = True
        self.docs_ready = False
        self.tool_calls = 0
        self.saved: dict[str, Any] | None = None
        self.writer: Callable[[Any], None] | None = None
        self.started = time.perf_counter()
        self._phase_sent: tuple[str, str] | None = None
        self._sources_sent = 0

    # ── registry of live runs (the graph state only stores run_id) ───────────
    @property
    def id(self) -> str:
        return self.turn.assistant_message_id

    def register(self) -> AgentRun:
        _runs[self.id] = self
        return self

    def release(self) -> None:
        _runs.pop(self.id, None)
        self.writer = None

    # ── events ───────────────────────────────────────────────────────────────
    def emit(self, event: str, data: dict[str, Any]) -> None:
        """From a graph node: into LangGraph's ordered custom stream; otherwise straight to the client."""
        if self.writer is not None:
            self.writer({"event": event, "data": data})
        else:
            self.deliver(event, data)

    def deliver(self, event: str, data: dict[str, Any]) -> None:
        """Hand one CONTRACT event to the client (the stream mapper and the wrap-up use this)."""
        if event == "delta":
            self.streamed += data.get("text", "")
        self._emit(event, data)

    def phase(self, phase: str, label: str) -> None:
        if self._phase_sent != (phase, label):
            self._phase_sent = (phase, label)
            self.emit("status", {"phase": phase, "label": label})

    def emit_sources(self) -> None:
        if self.registry.version != self._sources_sent:
            self._sources_sent = self.registry.version
            self.emit("sources", {"sources": self.registry.sources()})

    def step_start(self, name: str, label: str) -> dict[str, Any]:
        step = {"id": str(uuid.uuid4()), "name": name, "label": label, "status": "running", "detail": None,
                "startedAt": utc_iso(), "finishedAt": None}
        self.steps.append(step)
        self.emit("step", dict(step))
        return step

    def step_update(self, step: dict[str, Any], **changes: Any) -> None:
        step.update(changes)
        self.emit("step", dict(step))

    def step_end(self, step: dict[str, Any], status: str, detail: str | None = None) -> None:
        self.step_update(step, status=status, detail=detail, finishedAt=utc_iso())

    def finish_steps(self) -> None:
        for step in self.steps:
            if step["status"] == "running":
                step.update(status="error", detail="Stopped" if self.status == "stopped" else "Interrupted",
                            finishedAt=utc_iso())

    def fail(self, exc: BaseException) -> None:
        self.status = "error"
        if isinstance(exc, LLMError):
            self.error = exc.message
        else:
            log.error("agent turn failed", exc_info=exc)
            self.error = GENERIC_ERROR

    # ── persistence (exactly what the previous orchestrator stored) ──────────
    def meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {"durationMs": int((time.perf_counter() - self.started) * 1000),
                                "model": self.model.id}
        if any(self.usage.values()):
            meta.update(self.usage)
        if self.fallbacks:
            meta["fallbackFrom"] = self.fallbacks[0]
        meta.update(self.meta_extra)
        return meta

    def message(self, meta: dict[str, Any], content: str | None = None) -> Message:
        return Message(
            id=self.turn.assistant_message_id, conversation_id=self.turn.conversation_id, role="assistant",
            content=self.content if content is None else content, model=self.model.id, status=self.status,
            error=self.error, sources=self.registry.sources(), steps=[dict(s) for s in self.steps],
            attachments=[], meta=meta, created_at=self.turn.started_at,
        )

    def save(self, content: str | None = None) -> dict[str, Any]:
        """Persist the assistant message and bump the conversation (blocking: call from a worker thread)."""
        msg = self.message(self.meta(), content)
        with session_scope() as db:
            conv = db.get(Conversation, self.turn.conversation_id)
            if conv is not None:  # the chat may have been deleted mid-answer
                db.add(msg)
                conv.updated_at = datetime.now(timezone.utc)
                if self.title:
                    conv.title = self.title[:200]
                db.flush()
            self.saved = message_out(msg)
            return self.saved

    async def run(self) -> dict[str, Any]:
        """Run the finance graph for this turn and emit CONTRACT events; returns the saved message."""
        from app.agent.stream import run_turn

        return await run_turn(self)


def lookup(run_id: str) -> AgentRun:
    try:
        return _runs[run_id]
    except KeyError:
        raise RuntimeError(f"no live run for {run_id}") from None


def attach(state: dict[str, Any]) -> AgentRun:
    """The run behind a graph state, with its events routed through LangGraph's custom stream."""
    from langgraph.config import get_stream_writer

    run = lookup(state["run_id"])
    try:
        run.writer = get_stream_writer()
    except Exception:  # noqa: BLE001 — outside a streaming graph run: fall back to the direct emitter
        run.writer = None
    current_run.set(run)
    return run
