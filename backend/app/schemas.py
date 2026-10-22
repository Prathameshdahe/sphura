"""Pydantic mirrors of docs/CONTRACT.md. JSON is camelCase; Python attributes are snake_case."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel

ChatMode = Literal["chat", "research", "finance"]
Effort = Literal["fast", "balanced", "deep"]
Phase = Literal["thinking", "searching", "reading", "analyzing", "composing"]
Provider = Literal["gemini", "groq", "nvidia", "ollama", "lmstudio", "mock", "ensemble"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

    def dump(self) -> dict[str, Any]:
        """JSON-ready camelCase dict (use for SSE payloads and JSON columns)."""
        return self.model_dump(mode="json", by_alias=True)


# ── auth ──
class RegisterIn(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)


class LoginIn(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(CamelModel):
    id: str
    email: str
    name: str
    is_admin: bool
    created_at: datetime


# ── models ──
class ModelInfo(CamelModel):
    id: str
    provider: Provider
    label: str
    description: str
    available: bool
    reason: str | None = None
    supports_tools: bool = True
    supports_vision: bool = False
    is_default: bool = False


# ── conversations / messages ──
class ConversationSummary(CamelModel):
    id: str
    title: str
    mode: ChatMode = "chat"
    pinned: bool = False
    created_at: datetime
    updated_at: datetime


class ConversationPatch(CamelModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None


class Source(CamelModel):
    index: int
    type: Literal["web", "doc"]
    title: str
    url: str | None = None
    domain: str | None = None
    doc_id: str | None = None
    filename: str | None = None
    page: int | None = None
    snippet: str = ""
    score: float | None = None


class ToolStep(CamelModel):
    id: str
    name: str
    label: str
    status: Literal["running", "done", "error"] = "running"
    detail: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class AttachmentRef(CamelModel):
    doc_id: str
    filename: str
    mime_type: str
    size_bytes: int


class MessageOut(CamelModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    model: str | None = None
    status: Literal["complete", "stopped", "error"] = "complete"
    error: str | None = None
    sources: list[Source] = []
    steps: list[ToolStep] = []
    attachments: list[AttachmentRef] = []
    meta: dict[str, Any] | None = None


class ConversationDetail(CamelModel):
    conversation: ConversationSummary
    messages: list[MessageOut]


class ChatRequest(CamelModel):
    conversation_id: str | None = None
    content: str = Field(default="", max_length=100_000)
    model: str | None = Field(default=None, max_length=200)  # Message.model is VARCHAR(200)
    web_search: bool = False
    doc_ids: list[str] = Field(default_factory=list, max_length=50)
    mode: ChatMode = "chat"
    effort: Effort = "balanced"
    regenerate: bool = False
    edit_message_id: str | None = None
    workspace_id: str | None = None


# ── documents ──
class DocumentInfo(CamelModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    status: Literal["queued", "processing", "ready", "error"]
    error: str | None = None
    page_count: int | None = None
    chunk_count: int = 0
    ocr_used: bool = False
    conversation_id: str | None = None
    created_at: datetime


# ── health ──
class SearchHealth(CamelModel):
    tavily: bool
    duckduckgo: bool


class Health(CamelModel):
    ok: bool
    version: str
    providers: dict[str, bool]
    search: SearchHealth
    vector_store: Literal["qdrant", "qdrant-local"]
    embeddings: str
