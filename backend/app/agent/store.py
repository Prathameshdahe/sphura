"""Serialisation helpers shared by the chat agent and the conversation API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.models import Conversation, Message
from app.schemas import ConversationSummary, MessageOut


def to_utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on read; every stored timestamp is UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def utc_iso(dt: datetime | None = None) -> str:
    value = to_utc(dt) or datetime.now(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def conversation_out(conv: Conversation) -> dict[str, Any]:
    return ConversationSummary(
        id=conv.id, title=conv.title, mode=conv.mode if conv.mode in ("chat", "research", "finance") else "chat",
        pinned=bool(conv.pinned), created_at=to_utc(conv.created_at), updated_at=to_utc(conv.updated_at),
    ).dump()


def message_out(msg: Message) -> dict[str, Any]:
    return MessageOut(
        id=msg.id, conversation_id=msg.conversation_id, role=msg.role, content=msg.content or "",
        created_at=to_utc(msg.created_at), model=msg.model, status=msg.status or "complete", error=msg.error,
        sources=msg.sources or [], steps=msg.steps or [], attachments=msg.attachments or [], meta=msg.meta,
    ).dump()
