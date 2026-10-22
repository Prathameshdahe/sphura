"""Feedback: thumbs up/down, one vote per user + message (last wins), owner-only."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import Conversation, Feedback, Message


def _answer(user_id: str) -> str:
    with session_scope() as db:
        conv = Conversation(user_id=user_id, title="t")
        db.add(conv)
        db.flush()
        msg = Message(conversation_id=conv.id, role="assistant", content="An answer.", model="mock:sphura-mock",
                      sources=[], steps=[], attachments=[], meta={"verification": {"score": 0.75}})
        db.add(msg)
        db.flush()
        return msg.id


def _votes(user_id: str, message_id: str) -> list[Feedback]:
    with session_scope() as db:
        return list(db.scalars(select(Feedback).where(Feedback.user_id == user_id,
                                                      Feedback.message_id == message_id)))


def test_feedback_upsert_last_vote_wins(client, user):
    message_id = _answer(user["user"]["id"])
    r = client.post("/api/feedback", json={"messageId": message_id, "value": 1}, headers=user["headers"])
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = client.post("/api/feedback", json={"messageId": message_id, "value": -1, "comment": "  Too   long "},
                    headers=user["headers"])
    assert r.status_code == 200 and r.json() == {"ok": True}

    votes = _votes(user["user"]["id"], message_id)
    assert len(votes) == 1
    vote = votes[0]
    assert vote.kind == "thumb" and vote.value == -1
    assert vote.payload["comment"] == "Too long" and vote.payload["model"] == "mock:sphura-mock"
    assert vote.payload["verificationScore"] == 0.75

    client.post("/api/feedback", json={"messageId": message_id, "value": 1}, headers=user["headers"])
    votes = _votes(user["user"]["id"], message_id)
    assert [(v.value, v.payload["comment"]) for v in votes] == [(1, None)]


def test_feedback_ownership_and_validation(client, user, other_user):
    message_id = _answer(user["user"]["id"])
    r = client.post("/api/feedback", json={"messageId": message_id, "value": 1}, headers=other_user["headers"])
    assert r.status_code == 404 and r.json() == {"detail": "Message not found"}
    r = client.post("/api/feedback", json={"messageId": str(uuid.uuid4()), "value": 1}, headers=user["headers"])
    assert r.status_code == 404
    for bad in ({"messageId": message_id, "value": 0}, {"messageId": message_id, "value": 2}, {"value": 1}):
        r = client.post("/api/feedback", json=bad, headers=user["headers"])
        assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert client.post("/api/feedback", json={"messageId": message_id, "value": 1}).status_code == 401
    assert _votes(other_user["user"]["id"], message_id) == [] and _votes(user["user"]["id"], message_id) == []
