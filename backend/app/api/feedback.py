"""Thumbs up/down on answers: one vote per user + message (the last one wins). Other users' messages are 404."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Conversation, Feedback, Message, User, utcnow
from app.schemas import CamelModel

router = APIRouter(prefix="/feedback", tags=["feedback"])

KIND = "thumb"


class FeedbackIn(CamelModel):
    message_id: str = Field(min_length=1, max_length=36)
    value: Literal[1, -1]
    comment: str | None = Field(default=None, max_length=2000)


@router.post("")
def submit_feedback(body: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    msg = db.get(Message, body.message_id)
    conv = db.get(Conversation, msg.conversation_id) if msg is not None else None
    if msg is None or conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")

    comment = " ".join((body.comment or "").split()) or None
    payload = {"comment": comment, "conversationId": conv.id, "model": msg.model,
               "verificationScore": ((msg.meta or {}).get("verification") or {}).get("score")}
    votes = list(db.scalars(select(Feedback).where(Feedback.user_id == user.id, Feedback.message_id == msg.id,
                                                   Feedback.kind == KIND).order_by(Feedback.created_at)))
    vote = votes[-1] if votes else Feedback(user_id=user.id, message_id=msg.id, kind=KIND)
    for stale in votes[:-1]:  # heal duplicates from concurrent clicks
        db.delete(stale)
    vote.value = float(body.value)
    vote.payload = payload
    vote.created_at = utcnow()
    db.add(vote)
    db.commit()
    return {"ok": True}
