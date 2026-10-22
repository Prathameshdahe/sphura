"""Deterministic offline model ("mock:sphura-mock") so the agent loop can be tested without keys."""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.llm.types import LLMChunk, ToolCall

MOCK_NAME = "sphura-mock"
_HAS_SOURCES = re.compile(r"^\[1\] ", re.M)


def _text(message: dict[str, Any]) -> str:
    content = message.get("content") or ""
    if isinstance(content, list):  # multimodal parts
        content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def _last_user(messages: list[dict[str, Any]]) -> tuple[str, str]:
    """(question typed by the user, full last user message including any context block)."""
    full = next((_text(m) for m in reversed(messages) if m.get("role") == "user"), "")
    return full.split("\n\n---\n", 1)[0].strip(), full


def _answer(messages: list[dict[str, Any]]) -> str:
    question, full = _last_user(messages)
    earlier = sum(1 for m in messages if m.get("role") in ("user", "assistant")) - 1
    short = question if len(question) <= 120 else question[:117] + "..."
    lines = [
        "## Sphura mock answer",
        "",
        f"You asked: *{short}*",
        "",
        f"- Earlier messages in this conversation: {earlier}",
        "- This reply comes from the offline mock model, so it is fully deterministic.",
    ]
    if _HAS_SOURCES.search(full):
        lines += ["", "According to the provided sources, the first result supports this answer [1]."]
    lines += ["", "| Check | Result |", "|---|---|", "| Streaming | ok |", "| Markdown | ok |"]
    return "\n".join(lines)


async def stream(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> AsyncIterator[LLMChunk]:
    question, full = _last_user(messages)
    tool_names = {t.get("function", {}).get("name") for t in tools or []}
    if "web_search" in tool_names and "search" in question.lower() and not _HAS_SOURCES.search(full):
        yield LLMChunk(kind="tool_call_started")
        args = json.dumps({"query": question[:100]})
        yield LLMChunk(kind="tool_calls", tool_calls=[ToolCall(id="call_mock_1", name="web_search", arguments=args)])
        yield LLMChunk(kind="finish", finish_reason="tool_calls")
        return
    answer = _answer(messages)
    for piece in re.findall(r"\S+\s*|\s+", answer):
        await asyncio.sleep(0)
        yield LLMChunk(kind="text", text=piece)
    yield LLMChunk(kind="finish", finish_reason="stop")
    prompt_chars = sum(len(_text(m)) for m in messages)
    yield LLMChunk(kind="usage", usage={"promptTokens": prompt_chars // 4, "completionTokens": len(answer) // 4})


def complete(messages: list[dict[str, Any]], json_mode: bool = False) -> str:
    system = " ".join(_text(m) for m in messages if m.get("role") == "system").lower()
    question, _ = _last_user(messages)
    if json_mode:
        return json.dumps({"result": "mock"})
    if "title" in system:
        words = re.sub(r"[^\w\s'-]", " ", question).split()[:6]
        return " ".join(words).capitalize() or "Mock conversation"
    if "search query" in system:
        return question.splitlines()[-1] if question else "mock query"
    return "Mock completion."
