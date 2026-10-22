"""Run the finance graph for one turn and map its stream to CONTRACT events.

`graph.astream(stream_mode=["updates", "messages", "custom"], version="v2")`:
  custom   → status / step / sources / delta (refusal, disclaimer) / verification, emitted by the nodes
  messages → AIMessageChunk tokens from the `draft` node → delta (through the same RoundBuffer as the node)
  updates  → the `draft` node's result closes a round (flush or drop the held-back text)
Stop (client disconnect) cancels the graph and saves what was streamed with status "stopped"; a provider error
saves status "error" and ends the stream with an `error` event; `done` is always the last event otherwise.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from app.agent import prompts
from app.agent.graph import get_graph
from app.agent.nodes.draft import RoundBuffer, separator
from app.agent.run import GENERIC_ERROR, AgentRun
from app.agent.store import message_out

log = logging.getLogger("sphura.agent.stream")

RECURSION_LIMIT = 60
STREAM_MODES = ["updates", "messages", "custom"]


def initial_state(run: AgentRun) -> dict[str, Any]:
    t = run.turn
    return {
        "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)], "run_id": run.id, "question": t.question,
        "redacted": [], "user_id": t.user_id, "conversation_id": t.conversation_id, "doc_ids": list(t.doc_ids),
        "web_search": t.web_search, "model_id": run.model.id, "effort": t.effort, "analytics": None,
        "retrieved": [], "market": None, "sources": [], "steps": [], "draft": "", "verification": None,
        "refusal": None, "memory_used": 0, "title": None, "tool_rounds": 0,
    }


class _Mapper:
    """Turns the graph's stream items into client events (deltas mirror the draft node's RoundBuffer)."""

    def __init__(self, run: AgentRun) -> None:
        self.run = run
        self.buffer: RoundBuffer | None = None
        self.so_far = ""
        self.first = True

    def _release(self, text: str) -> None:
        if not text:
            return
        if self.first:
            delta = separator(self.so_far, text)
            if not delta:
                return
            self.first = False
        else:
            delta = text
        self.run.deliver("delta", {"text": delta})

    def handle(self, item: dict[str, Any]) -> None:
        kind, data = item.get("type"), item.get("data")
        if kind == "custom" and isinstance(data, dict):
            event, payload = data.get("event"), data.get("data") or {}
            if event == "_round":
                hidden = bool(payload.get("hidden"))
                self.buffer = None if hidden else RoundBuffer(bool(payload.get("tools")))
                self.so_far, self.first = str(payload.get("draft") or ""), True
            elif event:
                self.run.deliver(event, payload)
        elif kind == "messages" and isinstance(data, tuple) and len(data) == 2:
            message, meta = data
            if (self.buffer is not None and isinstance(message, AIMessageChunk)
                    and (meta or {}).get("langgraph_node") in ("draft", "ensemble")):
                self._release(self.buffer.feed(message))
        elif kind == "updates" and isinstance(data, dict):
            update = data.get("draft") if data.get("draft") is not None else data.get("ensemble")
            if update is not None and self.buffer is not None:
                ai = next((m for m in reversed(update.get("messages") or []) if isinstance(m, AIMessage)), None)
                self._release(self.buffer.finish(bool(ai is not None and ai.tool_calls)))
                self.buffer = None


async def _consume(run: AgentRun) -> None:
    graph = get_graph()
    config = {"configurable": {"thread_id": run.turn.conversation_id}, "recursion_limit": RECURSION_LIMIT}
    mapper = _Mapper(run)
    stream = graph.astream(initial_state(run), config, stream_mode=STREAM_MODES, version="v2")
    try:
        async for item in stream:
            mapper.handle(item)
            if run.stop.is_set():
                return
    finally:
        with contextlib.suppress(Exception):
            await stream.aclose()


async def run_turn(run: AgentRun) -> dict[str, Any]:
    """Run the graph (until done, stopped or failed), persist the answer and emit `title` + `done`/`error`."""
    run.register()
    worker = asyncio.create_task(_consume(run))
    stopper = asyncio.create_task(run.stop.wait())
    try:
        await asyncio.wait({worker, stopper}, return_when=asyncio.FIRST_COMPLETED)
        if not worker.done() or (run.stop.is_set() and run.saved is None):
            worker.cancel()
            with contextlib.suppress(BaseException):
                await worker
            run.status = "stopped"
        elif worker.cancelled():  # cancelled from inside (not by stop): still end with an `error` event
            run.fail(RuntimeError("graph task was cancelled"))
        elif worker.exception() is not None:
            run.fail(worker.exception())  # type: ignore[arg-type]
    except asyncio.CancelledError:  # server shutting down: keep what we have
        worker.cancel()
        run.status = "stopped"
        run.finish_steps()
        with contextlib.suppress(Exception):
            run.save(run.streamed)
        raise
    finally:
        stopper.cancel()
        run.release()

    if run.saved is None:  # refusal, stop or error: the finalize node did not persist
        run.finish_steps()
        if run.status == "complete" and not run.content.strip():
            run.status, run.error = "error", "The model returned an empty answer. Try again or pick another model."
        if run.turn.is_new and run.status != "stopped" and not run.title:
            run.title = prompts.fallback_title(run.turn.question)
        content = run.content if run.status == "complete" else run.streamed
        try:
            await asyncio.to_thread(run.save, content)
        except Exception:  # noqa: BLE001
            log.exception("could not save assistant message")
            run.status, run.error = "error", "The answer couldn't be saved. Please try again."
            run.saved = message_out(run.message(run.meta(), content))
    message = run.saved
    if run.title:
        run.deliver("title", {"conversationId": run.turn.conversation_id, "title": run.title})
    if run.status == "error":
        run.deliver("error", {"message": run.error or GENERIC_ERROR})
    else:
        run.deliver("done", {"message": message})
    return message
