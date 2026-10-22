"""All tables. Shared by every backend module — add new tables here (create_all runs on startup)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.db.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SafeText(TypeDecorator):
    """TEXT that drops NUL characters on write. PostgreSQL text/varchar can't store U+0000 (psycopg raises and the
    request 500s) while SQLite can — and pasted chat input, file text and model output may all contain one."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return value.replace("\x00", "") if isinstance(value, str) and "\x00" in value else value


class SafeString(SafeText):
    """VARCHAR(n) counterpart of SafeText."""

    impl = String


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(SafeString(120))
    password_hash: Mapped[str] = mapped_column(String(100))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(SafeString(200), default="New chat")
    mode: Mapped[str] = mapped_column(String(20), default="chat")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(SafeText, default="")
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="complete")  # complete | stopped | error
    error: Mapped[str | None] = mapped_column(SafeText, nullable=True)
    sources: Mapped[list] = mapped_column(JSON, default=list)      # list[Source] (camelCase dicts)
    steps: Mapped[list] = mapped_column(JSON, default=list)        # list[ToolStep]
    attachments: Mapped[list] = mapped_column(JSON, default=list)  # list[AttachmentRef]
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(SafeString(300))
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | processing | ready | error
    error: Mapped[str | None] = mapped_column(SafeText, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(SafeText)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(SafeString(300), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Memory(Base):
    """Long-term memory facts about a user (wave 2)."""

    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(SafeText)
    source_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Feedback(Base):
    """Thumbs up/down + arena votes — doubles as an evaluation dataset (wave 2)."""

    __tablename__ = "feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))  # "thumb" | "arena"
    value: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Workspace(Base):
    """An uploaded folder/zip the agent can explore with list/grep/read tools (wave 2)."""

    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(SafeString(200))
    root_path: Mapped[str] = mapped_column(String(500))
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # e.g. {"languages": {"py": 12}}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArenaBattle(Base):
    """Model arena: one prompt answered by two anonymous models, then voted (wave 2)."""

    __tablename__ = "arena_battles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    prompt: Mapped[str] = mapped_column(SafeText)
    model_a: Mapped[str] = mapped_column(String(200))
    model_b: Mapped[str] = mapped_column(String(200))
    answer_a: Mapped[str] = mapped_column(SafeText, default="")
    answer_b: Mapped[str] = mapped_column(SafeText, default="")
    winner: Mapped[str | None] = mapped_column(String(12), nullable=True)  # a | b | tie | both_bad
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    voted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
