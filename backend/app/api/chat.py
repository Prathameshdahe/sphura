"""POST /chat: one agent turn streamed as Server-Sent Events (event names and order per docs/CONTRACT.md).

Request handling is unchanged from the first orchestrator (new conversation, regenerate, editMessageId, docIds,
stop on disconnect → status "stopped", heartbeat); the answer itself comes from the LangGraph finance graph.
`mode` is accepted for compatibility and ignored: the graph's classifier decides the branch.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.types import Receive, Scope, Send

from app.agent.models import gpu_busy
from app.agent.prompts import fallback_title
from app.agent.run import GENERIC_ERROR, AgentRun, Turn
from app.agent.store import message_out
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.base import get_db, session_scope
from app.db.models import Conversation, Document, Message, User, utcnow
from app.llm.catalog import default_model_id
from app.llm.registry import list_models, resolve_model
from app.llm.types import LLMError, ResolvedModel
from app.schemas import AttachmentRef, ChatRequest

log = logging.getLogger("sphura.chat")
router = APIRouter(tags=["chat"])

HEARTBEAT_S = 15.0
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
MOCK_ID = "mock:sphura-mock"
_running: set[asyncio.Task] = set()  # keep agent tasks referenced until they finish


@dataclass
class _Prepared:
    conversation_id: str
    is_new: bool
    user_message: dict[str, Any]
    question: str
    history: list[dict[str, str]]
    doc_ids: list[str]
    last_model: str | None  # the model the previous turn of this conversation used
    last_requested: str | None = None  # what that turn was asked to use, when it failed over to `last_model`


def _attachment(doc: Document) -> dict[str, Any]:
    return AttachmentRef(doc_id=doc.id, filename=doc.filename, mime_type=doc.mime_type,
                         size_bytes=doc.size_bytes).dump()


def _prepare(user_id: str, body: ChatRequest) -> _Prepared:
    """Create/validate the conversation and the user message; snapshot the history. One short transaction."""
    with session_scope() as db:
        if body.conversation_id:
            conv = db.get(Conversation, body.conversation_id)
            if conv is None or conv.user_id != user_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
            is_new = False
        else:
            if body.regenerate or body.edit_message_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "conversationId is required to regenerate or edit")
            conv = Conversation(user_id=user_id, title=fallback_title(body.content), mode=body.mode)
            db.add(conv)
            db.flush()
            is_new = True

        messages = list(db.scalars(select(Message).where(Message.conversation_id == conv.id)
                                   .order_by(Message.created_at, Message.id)))
        docs = list(db.scalars(select(Document).where(Document.user_id == user_id,
                                                      Document.id.in_(body.doc_ids)))) if body.doc_ids else []
        last_answer = next((m for m in reversed(messages) if m.role == "assistant" and m.model), None)
        last_model = last_answer.model if last_answer is not None else None
        last_meta = (last_answer.meta or {}) if last_answer is not None else {}
        last_requested = (last_meta.get("modelKept") or {}).get("requested") or last_meta.get("fallbackFrom")

        if body.regenerate or body.edit_message_id:
            if body.edit_message_id:
                idx = next((i for i, m in enumerate(messages)
                            if m.id == body.edit_message_id and m.role == "user"), None)
                if idx is None:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
            else:
                idx = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].role == "user"), None)
                if idx is None:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "There is no message to regenerate")
            user_msg, earlier = messages[idx], messages[:idx]
            for later in messages[idx + 1:]:
                db.delete(later)
            if body.edit_message_id:
                content = body.content.strip()
                if not content:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message is empty")
                user_msg.content = content
        else:
            content = body.content.strip()
            if not content:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message is empty")
            user_msg, earlier = Message(conversation_id=conv.id, role="user", content=content, status="complete",
                                        sources=[], steps=[], attachments=[]), messages
            db.add(user_msg)

        # attachments = documents first sent with this message (earlier ones are already shown above it)
        shown = {a.get("docId") for m in earlier if m.role == "user" for a in (m.attachments or [])}
        current = {a.get("docId") for a in (user_msg.attachments or [])}
        new_refs = [_attachment(d) for d in docs if d.id not in shown and d.id not in current]
        if new_refs:
            user_msg.attachments = [*(user_msg.attachments or []), *new_refs]
        for d in docs:
            if d.conversation_id is None:
                d.conversation_id = conv.id

        conv.mode = body.mode
        conv.updated_at = utcnow()
        db.flush()
        history = [{"role": m.role, "content": m.content} for m in earlier
                   if m.status != "error" and (m.content or "").strip()]
        order = {d_id: i for i, d_id in enumerate(body.doc_ids)}
        return _Prepared(
            conversation_id=conv.id, is_new=is_new, user_message=message_out(user_msg), question=user_msg.content,
            history=history, doc_ids=sorted((d.id for d in docs), key=order.__getitem__), last_model=last_model,
            last_requested=last_requested if isinstance(last_requested, str) else None,
        )


def _choose_model(last_model: str | None) -> ResolvedModel:
    """No explicit model: the one this conversation used last (if still available), else the server default."""
    models = list_models()
    available = {m.id for m in models if m.available}
    if last_model and last_model in available:
        return resolve_model(last_model)
    default = default_model_id(models)
    if default is None:
        raise LLMError("No AI model is available yet. Add GROQ_API_KEY or GEMINI_API_KEY to .env, "
                       "or start Ollama / LM Studio.", "unavailable")
    return resolve_model(default)


def _keep_conversation_model(explicit: ResolvedModel, prepared: _Prepared) -> ResolvedModel:
    """The previous turn failed over away from the model the user still has selected: keep the model that
    answered (switching back would reload a local model or hit the same provider error again)."""
    last = prepared.last_model
    if not last or last == explicit.id or prepared.last_requested != explicit.id:
        return explicit
    if last not in {m.id for m in list_models() if m.available}:
        return explicit
    try:
        return resolve_model(last)
    except LLMError:
        return explicit


def _respect_gpu(model: ResolvedModel) -> ResolvedModel:
    """While training owns the GPU (training/GPU_BUSY), local models are swapped for the mock or refused."""
    if model.provider != "ollama" or not gpu_busy():
        return model
    if settings.sphura_enable_mock:
        log.info("GPU busy: answering with the mock instead of %s", model.id)
        return resolve_model(MOCK_ID)
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                        "The local GPU is busy with a training job; pick a cloud model or try again later.")


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


class _SSEResponse(StreamingResponse):
    """Streams, and listens for http.disconnect concurrently so a closed tab stops the agent."""

    def __init__(self, content: AsyncIterator[str], stop: asyncio.Event) -> None:
        super().__init__(content, media_type="text/event-stream", headers=SSE_HEADERS)
        self._stop = stop

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def listen() -> None:
            with contextlib.suppress(Exception):  # an unusable receive channel just means no early stop
                while (await receive())["type"] != "http.disconnect":
                    pass
                self._stop.set()

        listener = asyncio.create_task(listen())
        try:
            await self.stream_response(send)
        except OSError:  # client went away mid-write
            pass
        finally:
            listener.cancel()
            self._stop.set()  # no-op after a finished turn; otherwise stops (and saves) the agent


async def _events(agent: AgentRun, queue: asyncio.Queue, finished: asyncio.Event) -> AsyncIterator[str]:
    async def drive() -> None:
        try:
            await agent.run()
        except Exception:  # noqa: BLE001
            log.exception("agent crashed")
            queue.put_nowait(("error", {"message": GENERIC_ERROR}))
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(drive())
    _running.add(task)
    task.add_done_callback(_running.discard)
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if item is None:
                finished.set()
                return
            yield _sse(*item)
    finally:
        if not finished.is_set():
            agent.stop.set()


@router.post("/chat")
async def chat(body: ChatRequest, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> StreamingResponse:
    user_id = user.id
    db.close()  # don't keep the auth session's connection for the whole stream
    explicit = (body.model or "").strip() or None
    model: ResolvedModel | None = None
    try:  # every refusal (400 / 503) happens before _prepare writes the user message
        if explicit:
            model = await asyncio.to_thread(resolve_model, explicit)
            _respect_gpu(model)
        else:
            _respect_gpu(await asyncio.to_thread(_choose_model, None))
    except LLMError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from None
    prepared = await asyncio.to_thread(_prepare, user_id, body)
    kept_from: str | None = None
    if model is None:
        try:
            model = await asyncio.to_thread(_choose_model, prepared.last_model)
        except LLMError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from None
    else:
        kept = await asyncio.to_thread(_keep_conversation_model, model, prepared)
        kept_from, model = (model.id if kept.id != model.id else None), kept
    requested = model.id
    model = _respect_gpu(model)

    turn = Turn(
        user_id=user_id, conversation_id=prepared.conversation_id, is_new=prepared.is_new,
        question=prepared.question, history=prepared.history, doc_ids=prepared.doc_ids,
        web_search=body.web_search, mode=body.mode, effort=body.effort, model=model,
    )
    queue: asyncio.Queue = asyncio.Queue()
    stop, finished = asyncio.Event(), asyncio.Event()
    agent = AgentRun(turn, lambda event, data: queue.put_nowait((event, data)), stop)
    queue.put_nowait(("start", {
        "conversationId": prepared.conversation_id, "userMessage": prepared.user_message,
        "assistantMessageId": turn.assistant_message_id, "model": model.id,
    }))
    if kept_from:
        agent.meta_extra["modelKept"] = {"requested": kept_from}
    if model.id != requested:  # the GPU swap above: say so in the thread instead of silently answering
        agent.meta_extra["gpuBusy"] = {"requested": requested}
        step = agent.step_start("switch_model", "Local GPU is reserved by a training job")
        agent.step_end(step, "done", f"Answering with {model.label} instead of {requested}")
    return _SSEResponse(_events(agent, queue, finished), stop)
