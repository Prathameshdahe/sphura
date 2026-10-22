"""Conversation list / detail / rename+pin / delete. Other users' conversations are always 404."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agent.store import conversation_out, message_out
from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import Conversation, Message, User
from app.schemas import ConversationPatch

router = APIRouter(prefix="/conversations", tags=["conversations"])


def get_owned_conversation(db: Session, conversation_id: str, user_id: str) -> Conversation:
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("")
def list_conversations(
    q: str | None = Query(default=None, max_length=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if q and q.strip():
        pattern = _like(q.strip())
        in_messages = select(Message.conversation_id).where(Message.content.ilike(pattern, escape="\\"))
        stmt = stmt.where(or_(Conversation.title.ilike(pattern, escape="\\"), Conversation.id.in_(in_messages)))
    stmt = stmt.order_by(Conversation.pinned.desc(), Conversation.updated_at.desc()).limit(500)
    return [conversation_out(c) for c in db.scalars(stmt)]


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    conv = get_owned_conversation(db, conversation_id, user.id)
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at, Message.id)
    ).all()
    return {"conversation": conversation_out(conv), "messages": [message_out(m) for m in messages]}


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: str, body: ConversationPatch, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> dict:
    conv = get_owned_conversation(db, conversation_id, user.id)
    if body.title is not None:
        title = " ".join(body.title.split())
        if not title:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Title can't be empty")
        conv.title = title[:200]
    if body.pinned is not None:
        conv.pinned = body.pinned
    db.commit()
    return conversation_out(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> Response:
    conv = get_owned_conversation(db, conversation_id, user.id)
    db.delete(conv)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
