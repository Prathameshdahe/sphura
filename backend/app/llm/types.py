"""Small value types shared by the LLM layer and its callers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.schemas import ModelInfo

ChunkKind = Literal["text", "tool_call_started", "tool_calls", "finish", "usage"]
ErrorKind = Literal[
    "auth", "rate_limit", "too_large", "connection", "timeout", "not_found",
    "bad_request", "tools", "server", "unavailable", "unknown",
]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as produced by the model


@dataclass
class LLMChunk:
    """One streamed item: a text delta, the assembled tool calls, a finish reason or usage."""

    kind: ChunkKind
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


@dataclass
class ResolvedModel:
    id: str             # "groq:openai/gpt-oss-120b"
    provider: str       # "groq"
    name: str           # "openai/gpt-oss-120b"
    info: ModelInfo
    prompt_budget: int  # tokens we allow ourselves to send (free tiers / small local contexts)
    reasoning: bool = False  # accepts `reasoning_effort`
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def supports_tools(self) -> bool:
        return self.info.supports_tools

    @property
    def label(self) -> str:
        return self.info.label


class LLMError(Exception):
    """A provider failure carrying a short, human-readable message."""

    def __init__(self, message: str, kind: ErrorKind = "unknown", status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status = status

    @property
    def retryable_elsewhere(self) -> bool:
        """True when another model could plausibly succeed."""
        return self.kind in {"auth", "rate_limit", "too_large", "connection", "timeout", "not_found", "server",
                             "unavailable"}
