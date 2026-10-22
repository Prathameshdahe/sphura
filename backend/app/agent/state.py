"""FinState: the LangGraph state of one chat turn (docs/FINANCE_PLAN.md section 3).

Everything here is JSON-friendly so the SQLite checkpointer can store it. Live, non-serialisable objects
(the model client, the stop event, the source registry) live in the `AgentRun` looked up by `run_id`.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

Intent = Literal["spending", "documents", "market", "explain", "advice", "out_of_scope"]
INTENTS: tuple[str, ...] = ("spending", "documents", "market", "explain", "advice", "out_of_scope")


class FinState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    run_id: str                 # key of the live AgentRun (the assistant message id)
    question: str               # the user's message after guard_in redaction
    redacted: list[str]         # kinds of identifiers guard_in removed ("card", "account", …)
    intent: str
    intent_confidence: float
    user_id: str
    conversation_id: str
    doc_ids: list[str]
    web_search: bool
    model_id: str
    effort: str
    analytics: dict[str, Any] | None
    retrieved: list[dict[str, Any]]
    market: dict[str, Any] | None
    sources: list[dict[str, Any]]   # CONTRACT Source dicts (cumulative)
    steps: list[dict[str, Any]]     # CONTRACT ToolStep dicts
    draft: str
    verification: dict[str, Any] | None
    refusal: str | None
    memory_used: int
    title: str | None
    tool_rounds: int                # draft ⇄ tools iterations so far
