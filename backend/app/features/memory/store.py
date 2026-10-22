"""Memory rows: serialisation and the short DB transactions used by the API and the chat plugin."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.store import to_utc
from app.db.base import session_scope
from app.db.models import Conversation, Memory, Message, User
from app.features.memory.ranking import normalise
from app.schemas import CamelModel

MAX_CONTENT = 500
MAX_AUTO_MEMORIES = 300  # automatic extraction stops here (the user can still add by hand)


class MemoryItem(CamelModel):
    id: str
    content: str
    created_at: datetime
    source_message_id: str | None = None


def item_out(memory: Memory) -> dict:
    return MemoryItem(id=memory.id, content=memory.content, created_at=to_utc(memory.created_at),
                      source_message_id=memory.source_message_id).dump()


def is_enabled(user: User) -> bool:
    return True if user.memory_enabled is None else bool(user.memory_enabled)


def list_memories(db: Session, user_id: str) -> list[Memory]:
    """Newest first."""
    stmt = select(Memory).where(Memory.user_id == user_id).order_by(Memory.created_at.desc(), Memory.id)
    return list(db.scalars(stmt))


def find_duplicate(db: Session, user_id: str, content: str) -> Memory | None:
    key = normalise(content)
    return next((m for m in list_memories(db, user_id) if normalise(m.content) == key), None)


def add(db: Session, user_id: str, content: str, source_message_id: str | None = None) -> Memory:
    memory = Memory(user_id=user_id, content=content[:MAX_CONTENT], source_message_id=source_message_id)
    db.add(memory)
    db.flush()
    return memory


def recall_state(user_id: str) -> tuple[bool, list[tuple[str, str]]]:
    """(memory enabled, [(id, content)] newest first) — one short read for the chat plugin."""
    with session_scope() as db:
        user = db.get(User, user_id)
        if user is None or not is_enabled(user):
            return False, []
        return True, [(m.id, m.content) for m in list_memories(db, user_id)]


def existing_contents(user_id: str) -> list[str]:
    with session_scope() as db:
        return [m.content for m in list_memories(db, user_id)]


def _source_message_id(db: Session, conversation_id: str) -> str | None:
    """The latest user message of the conversation (the one the facts were extracted from)."""
    conv = db.get(Conversation, conversation_id)
    if conv is None:
        return None
    stmt = (select(Message.id).where(Message.conversation_id == conversation_id, Message.role == "user")
            .order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
    return db.scalars(stmt).first()


def save_facts(user_id: str, conversation_id: str, facts: list[str]) -> list[str]:
    """Store facts that aren't already remembered (re-checked here); returns the ones added."""
    added: list[str] = []
    with session_scope() as db:
        user = db.get(User, user_id)
        if user is None or not is_enabled(user):
            return []
        existing = list_memories(db, user_id)
        if len(existing) >= MAX_AUTO_MEMORIES:
            return []
        seen = {normalise(m.content) for m in existing}
        source_id = _source_message_id(db, conversation_id)
        for fact in facts:
            key = normalise(fact)
            if key and key not in seen:
                seen.add(key)
                add(db, user_id, fact, source_id)
                added.append(fact)
    return added
