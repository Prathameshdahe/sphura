"""POST /api/chat over the finance graph with the mock model: SSE order/shapes, history, regenerate/edit, errors,
documents, stop and heartbeat. The helpers `send`, `first`, `names` are shared with the other chat tests."""
from __future__ import annotations

import asyncio
import sys
import threading
import types
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select

from app.agent import adapters
from app.agent import classify as classify_mod
from app.agent.run import AgentRun, Turn
from app.db.base import session_scope
from app.db.models import Document, Message
from app.llm import registry
from app.llm.mock import _answer as mock_answer
from app.llm.types import LLMError
from app.tools import web
from tests.conftest import parse_sse

MOCK = "mock:sphura-mock"


@pytest.fixture(autouse=True)
def keyword_router(monkeypatch, tmp_path):
    """Deterministic routing: the keyword fallback (the trained artifact may or may not exist on this machine)."""
    monkeypatch.setattr(classify_mod, "ROUTER_PATH", tmp_path / "missing-router.joblib")


def send(client, user, **body):
    payload = {"content": "", "webSearch": False, "docIds": [], "mode": "chat", "effort": "balanced", **body}
    r = client.post("/api/chat", json=payload, headers=user["headers"])
    return r, (parse_sse(r.text) if r.status_code == 200 else [])


def names(events):
    return [e for e, _ in events]


def first(events, name):
    return next(d for e, d in events if e == name)


def test_new_conversation_stream_order_and_shapes(client, user):
    r, events = send(client, user, content="What is an *SIP* and how does compounding work?")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"

    seq = names(events)
    assert seq[0] == "start" and seq[-1] == "done"
    assert set(seq) <= {"start", "status", "step", "sources", "delta", "title", "done"}
    assert seq.index("title") < seq.index("done")
    composing = next(i for i, (e, d) in enumerate(events) if e == "status" and d["phase"] == "composing")
    assert composing < seq.index("delta")

    start = first(events, "start")
    assert start["model"] == MOCK
    assert set(start) == {"conversationId", "userMessage", "assistantMessageId", "model"}
    um = start["userMessage"]
    assert um["role"] == "user" and um["content"] == "What is an *SIP* and how does compounding work?"
    assert um["conversationId"] == start["conversationId"] and um["createdAt"].endswith("Z")

    for _, data in (ev for ev in events if ev[0] == "status"):
        assert data["phase"] in {"thinking", "searching", "reading", "analyzing", "composing"} and data["label"]
    assert first(events, "status") == {"phase": "thinking", "label": "Understanding your question"}
    router = [d for e, d in events if e == "step" and d["name"] == "router"]
    assert router and router[-1]["status"] == "done" and router[-1]["label"].startswith("Finance concept")

    title = first(events, "title")
    assert title["conversationId"] == start["conversationId"] and title["title"]

    done = first(events, "done")["message"]
    assert done["id"] == start["assistantMessageId"]
    assert done["role"] == "assistant" and done["status"] == "complete" and done["model"] == MOCK
    assert done["content"] == "".join(d["text"] for e, d in events if e == "delta")
    assert "## Sphura mock answer" in done["content"]
    assert done["meta"]["durationMs"] >= 0 and done["meta"]["model"] == MOCK
    assert done["meta"]["router"] == {"label": "explain", "confidence": pytest.approx(0.75), "autoSearch": False}
    assert {"sources", "steps", "attachments", "createdAt", "conversationId"} <= set(done)

    detail = client.get(f"/api/conversations/{start['conversationId']}", headers=user["headers"]).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["conversation"]["title"] == title["title"]
    assert detail["messages"][1]["content"] == done["content"]


def test_follow_up_sees_history(client, user):
    _, ev1 = send(client, user, content="My name is Arjun and I want to start saving.")
    cid = first(ev1, "start")["conversationId"]
    _, ev2 = send(client, user, content="What is my name?", conversationId=cid)
    assert "title" not in names(ev2)  # only new conversations get a title event
    done = first(ev2, "done")["message"]
    assert "Earlier messages in this conversation: 2" in done["content"]
    detail = client.get(f"/api/conversations/{cid}", headers=user["headers"]).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]


def test_mode_is_accepted_and_ignored(client, user):
    _, events = send(client, user, content="explain the difference between FD and RD", mode="research")
    assert names(events)[-1] == "done"
    done = first(events, "done")["message"]
    assert [s["name"] for s in done["steps"]] == ["router"] and done["meta"]["router"]["label"] == "explain"


def test_regenerate_replaces_last_answer(client, user):
    _, ev1 = send(client, user, content="First question about my budget")
    cid = first(ev1, "start")["conversationId"]
    _, ev2 = send(client, user, content="Second question about savings", conversationId=cid)
    old_answer = first(ev2, "done")["message"]["id"]
    last_user = first(ev2, "start")["userMessage"]["id"]

    _, ev3 = send(client, user, conversationId=cid, regenerate=True)
    start = first(ev3, "start")
    assert start["userMessage"]["id"] == last_user
    new_answer = first(ev3, "done")["message"]
    assert new_answer["id"] != old_answer
    assert "Earlier messages in this conversation: 2" in new_answer["content"]

    msgs = client.get(f"/api/conversations/{cid}", headers=user["headers"]).json()["messages"]
    assert len(msgs) == 4 and msgs[-1]["id"] == new_answer["id"]
    assert old_answer not in {m["id"] for m in msgs}


def test_edit_message_truncates_and_answers_again(client, user):
    _, ev1 = send(client, user, content="Original question about tax")
    cid = first(ev1, "start")["conversationId"]
    first_user = first(ev1, "start")["userMessage"]["id"]
    send(client, user, content="Another one about loans", conversationId=cid)

    _, ev = send(client, user, content="Edited question about tax", conversationId=cid, editMessageId=first_user)
    assert first(ev, "start")["userMessage"]["content"] == "Edited question about tax"
    done = first(ev, "done")["message"]
    assert "Earlier messages in this conversation: 0" in done["content"]
    msgs = client.get(f"/api/conversations/{cid}", headers=user["headers"]).json()["messages"]
    assert [(m["role"], m["id"]) for m in msgs] == [("user", first_user), ("assistant", done["id"])]
    assert msgs[0]["content"] == "Edited question about tax"


def test_chat_errors_are_plain_http(client, user, other_user):
    _, ev = send(client, user, content="mine")
    cid = first(ev, "start")["conversationId"]
    r, _ = send(client, other_user, content="steal", conversationId=cid)
    assert r.status_code == 404 and r.json() == {"detail": "Conversation not found"}

    r, _ = send(client, user, content="hi", model="groq:openai/gpt-oss-120b")
    assert r.status_code == 400 and "GROQ_API_KEY" in r.json()["detail"]
    r, _ = send(client, user, content="hi", model="nonsense")
    assert r.status_code == 400 and isinstance(r.json()["detail"], str)
    r, _ = send(client, user, content="   ")
    assert r.status_code == 400 and r.json()["detail"] == "Message is empty"
    r, _ = send(client, user, regenerate=True)
    assert r.status_code == 400
    assert client.post("/api/chat", json={"content": "x"}).status_code == 401


def test_provider_error_is_saved_and_emitted(client, user, monkeypatch):
    async def broken(*args, **kwargs):
        raise LLMError("Groq rate limit reached. Wait a minute or pick another model.", "rate_limit")
        yield  # pragma: no cover

    monkeypatch.setattr(registry, "chat_stream", broken)
    _, events = send(client, user, content="how much tax will I pay this year?")
    assert names(events)[-1] == "error"
    assert first(events, "error") == {"message": "Groq rate limit reached. Wait a minute or pick another model."}
    cid = first(events, "start")["conversationId"]
    msgs = client.get(f"/api/conversations/{cid}", headers=user["headers"]).json()["messages"]
    assert msgs[-1]["status"] == "error" and msgs[-1]["error"].startswith("Groq rate limit")


@dataclass
class _Chunk:
    doc_id: str
    filename: str
    page: int | None
    chunk_index: int
    text: str
    score: float
    section: str | None = None


def _add_document(user_id: str, status: str) -> str:
    doc_id = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Document(id=doc_id, user_id=user_id, filename="report.pdf", mime_type="application/pdf",
                        size_bytes=1234, sha256="0" * 64, storage_path="x", status=status))
    return doc_id


def _set_doc_status(doc_id: str, status: str) -> None:
    with session_scope() as db:
        db.get(Document, doc_id).status = status


def test_documents_are_searched_waited_for_and_attached(client, user, monkeypatch):
    seen = {}

    async def fake_search_documents(user_id, query, doc_ids, k=8):
        seen.update(user_id=user_id, query=query, doc_ids=doc_ids, k=k)
        return [_Chunk(doc_ids[0], "report.pdf", 3, 0, "Revenue grew 12% year over year.", 0.8, "Results")]

    fake = types.ModuleType("app.rag.service")
    fake.search_documents = fake_search_documents
    monkeypatch.setitem(sys.modules, "app.rag.service", fake)
    monkeypatch.setattr(adapters, "DOC_POLL_S", 0.05)

    doc_id = _add_document(user["user"]["id"], "processing")
    threading.Timer(0.4, _set_doc_status, args=(doc_id, "ready")).start()
    _, events = send(client, user, content="How much did revenue grow?", docIds=[doc_id, str(uuid.uuid4())])

    assert seen["user_id"] == user["user"]["id"] and seen["doc_ids"] == [doc_id]
    assert first(events, "done")["message"]["meta"]["router"]["label"] == "documents"
    steps = [d for e, d in events if e == "step" and d["name"] == "search_documents"]
    assert any(s["label"] == "Waiting for report.pdf to finish indexing" for s in steps)
    assert steps[-1]["status"] == "done" and steps[-1]["detail"] == "1 passage from 1 document"
    assert any(e == "status" and d == {"phase": "reading", "label": "Reading your documents"} for e, d in events)
    src = [d for e, d in events if e == "sources"][-1]["sources"][0]
    assert src["type"] == "doc" and src["docId"] == doc_id and src["page"] == 3 and src["filename"] == "report.pdf"
    assert "[1]" in first(events, "done")["message"]["content"]

    start = first(events, "start")
    assert start["userMessage"]["attachments"] == [
        {"docId": doc_id, "filename": "report.pdf", "mimeType": "application/pdf", "sizeBytes": 1234}]
    with session_scope() as db:
        assert db.get(Document, doc_id).conversation_id == start["conversationId"]

    # the same document on a follow-up is not attached to the new message again
    _, ev2 = send(client, user, content="And profit?", conversationId=start["conversationId"], docIds=[doc_id])
    assert first(ev2, "start")["userMessage"]["attachments"] == []


def test_other_users_documents_are_ignored(client, user, other_user):
    foreign = _add_document(other_user["user"]["id"], "ready")
    _, events = send(client, user, content="read it", docIds=[foreign])
    assert first(events, "start")["userMessage"]["attachments"] == []
    assert not [d for e, d in events if e == "step" and d["name"] == "search_documents"]
    with session_scope() as db:
        assert db.get(Document, foreign).conversation_id is None


def test_stop_saves_partial_answer(client, user):
    _, ev = send(client, user, content="seed conversation about savings")
    cid = first(ev, "start")["conversationId"]
    events: list[tuple[str, dict]] = []

    async def main():
        stop = asyncio.Event()

        def emit(event, data):
            events.append((event, data))
            if event == "delta" and len([e for e in events if e[0] == "delta"]) == 3:
                stop.set()

        turn = Turn(user_id=user["user"]["id"], conversation_id=cid, is_new=False,
                    question="tell me more about how SIP returns compound", history=[], doc_ids=[],
                    web_search=False, mode="chat", effort="fast", model=registry.resolve_model(MOCK))
        return await AgentRun(turn, emit, stop).run()

    message = asyncio.run(main())
    assert message["status"] == "stopped"
    full = mock_answer([{"role": "user", "content": "tell me more about how SIP returns compound"}])
    assert 0 < len(message["content"]) < len(full) and full.startswith(message["content"])
    assert events[-1][0] == "done" and events[-1][1]["message"]["status"] == "stopped"
    with session_scope() as db:
        saved = db.scalars(select(Message).where(Message.id == message["id"])).one()
        assert saved.status == "stopped" and saved.content == message["content"]


def test_heartbeat_comment_while_waiting(client, user, monkeypatch):
    from app.api import chat as chat_api

    async def slow_search(query, max_results=6):
        await asyncio.sleep(0.3)
        return web.SearchResults([], provider="fake")

    monkeypatch.setattr(chat_api, "HEARTBEAT_S", 0.05)
    monkeypatch.setattr(web, "web_search", slow_search)
    r, events = send(client, user, content="slow one", webSearch=True)
    assert ": ping\n\n" in r.text
    assert names(events)[0] == "start" and names(events)[-1] == "done"
    step = [d for e, d in events if e == "step" and d["name"] == "finance_news"][-1]
    assert step["status"] == "done" and step["detail"] == "No results"
