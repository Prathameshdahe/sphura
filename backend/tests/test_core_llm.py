"""The real OpenAI-compatible path (openai SDK) against a fake HTTP transport: no network, no keys."""
from __future__ import annotations

import asyncio
import json

import httpx2
import pytest
from openai import AsyncOpenAI

from app.llm import registry
from app.llm.types import LLMError


def _chunk(delta: dict | None = None, finish: str | None = None, usage: dict | None = None) -> dict:
    choices = [] if delta is None else [{"index": 0, "delta": delta, "finish_reason": finish}]
    out = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": "m", "choices": choices}
    if usage:
        out["usage"] = usage
    return out


STREAM = [
    _chunk({"role": "assistant", "content": "<think>plan"}),
    _chunk({"content": "</think>Hel"}),
    _chunk({"content": "lo"}),
    _chunk({"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                            "function": {"name": "web_search", "arguments": "{\"que"}}]}),
    _chunk({"tool_calls": [{"index": 0, "function": {"arguments": "ry\": \"x\"}"}}]}),
    _chunk({}, finish="tool_calls"),
    _chunk(None, usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}),
]


@pytest.fixture
def fake_provider(monkeypatch):
    seen: dict = {}
    state = {"status": 200}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        if state["status"] != 200:
            return httpx2.Response(state["status"], json={"error": {"message": "Rate limit reached for model"}})
        if seen["body"].get("stream"):
            sse = "".join(f"data: {json.dumps(c)}\n\n" for c in STREAM) + "data: [DONE]\n\n"
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())
        return httpx2.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 1, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "<think>x</think>\"Neat Title.\""}}],
        })

    def fake_client(provider: str) -> AsyncOpenAI:
        return AsyncOpenAI(api_key="k", base_url=registry._base(provider), max_retries=0,
                           http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))

    monkeypatch.setattr(registry.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(registry, "_client", fake_client)
    return seen, state


def test_stream_assembles_tool_calls_strips_think_and_reports_usage(fake_provider):
    seen, _ = fake_provider

    async def collect():
        tools = [{"type": "function", "function": {"name": "web_search", "parameters": {"type": "object"}}}]
        return [c async for c in registry.chat_stream("groq:openai/gpt-oss-120b", [{"role": "user", "content": "hi"}],
                                                      tools=tools, reasoning_effort="low")]

    chunks = asyncio.run(collect())
    assert "".join(c.text for c in chunks if c.kind == "text") == "Hello"
    kinds = [c.kind for c in chunks]
    assert kinds.index("tool_call_started") < kinds.index("tool_calls") < kinds.index("finish")
    call = next(c for c in chunks if c.kind == "tool_calls").tool_calls[0]
    assert (call.id, call.name, json.loads(call.arguments)) == ("call_1", "web_search", {"query": "x"})
    assert next(c for c in chunks if c.kind == "finish").finish_reason == "tool_calls"
    assert next(c for c in chunks if c.kind == "usage").usage == {"promptTokens": 10, "completionTokens": 5}

    body = seen["body"]
    assert seen["url"].startswith("https://api.groq.com/openai/v1/chat/completions")
    assert body["model"] == "openai/gpt-oss-120b" and body["stream"] is True
    assert body["tool_choice"] == "auto" and body["tools"][0]["function"]["name"] == "web_search"
    assert body["stream_options"] == {"include_usage": True} and body["reasoning_effort"] == "low"


def test_complete_and_rate_limit_mapping(fake_provider):
    seen, state = fake_provider
    text = asyncio.run(registry.complete("groq:qwen/qwen3.8-27b", [{"role": "user", "content": "x"}]))
    assert text == "\"Neat Title.\""
    assert "reasoning_effort" not in seen["body"]  # only sent to models that accept it

    state["status"] = 429
    with pytest.raises(LLMError) as err:
        asyncio.run(registry.complete("groq:openai/gpt-oss-20b", [{"role": "user", "content": "x"}]))
    assert err.value.kind == "rate_limit" and "rate limit" in err.value.message.lower()
