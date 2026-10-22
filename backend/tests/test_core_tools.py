from __future__ import annotations

import asyncio
import json

import httpx2
import openai
import pytest

from app.agent import prompts
from app.agent.sources import SourceRegistry
from app.llm import mock
from app.llm.errors import map_error
from app.llm.think import ThinkFilter
from app.tools import web


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost:8000/api/health",
    "http://[::1]/",
    "http://10.0.0.5/admin",
    "http://192.168.1.1/",
    "http://[::ffff:127.0.0.1]/",
    "file:///etc/passwd",
    "ftp://example.com/file",
    "http://user:pw@example.com/",
])
def test_read_page_ssrf_guard_refuses(url):
    page = run(web.read_page(url))
    assert not page.ok and page.error
    assert page.text == ""


def test_check_url_allows_public_ip_literal():
    assert run(web.check_url("https://93.184.215.14/")) is None
    assert run(web.check_url("http://100.64.0.1/")) is not None  # carrier-grade NAT is not public


def test_web_search_never_raises_on_empty_query():
    res = run(web.web_search("   "))
    assert list(res) == [] and res.error


def test_source_registry_dedupes_and_renders_within_budget():
    reg = SourceRegistry()
    assert reg.add_web("https://www.Example.com/a/", "A", "alpha snippet", "example.com") == 1
    assert reg.add_web("https://example.com/a", "A again", "dup", "example.com") == 1
    assert reg.add_web("https://other.org/b", "B", "beta", "other.org") == 2
    v = reg.version
    assert reg.add_page("https://example.com/a", "A", "long page text " * 500, "example.com") == 1
    assert reg.version == v  # only the model-side context grew; the client-visible source is unchanged
    assert "long page text long page text" in reg.render(4000)

    class Chunk:
        doc_id, filename, page, chunk_index, text, score, section = "d1", "notes.pdf", 2, 7, "chunk text", 0.5, None

    assert reg.add_doc(Chunk()) == 3 and reg.add_doc(Chunk()) == 3
    srcs = reg.sources()
    assert [s["index"] for s in srcs] == [1, 2, 3]
    assert srcs[2]["type"] == "doc" and srcs[2]["docId"] == "d1" and srcs[2]["page"] == 2
    assert all(len(s["snippet"]) <= 401 for s in srcs)
    block = reg.render(2000)
    assert block.startswith("[1] A — example.com") and "[3] notes.pdf (page 2)" in block
    assert len(block) < 2600
    assert reg.url_for(2) == "https://other.org/b" and reg.url_for(9) is None


def test_history_trim_and_citation_stripping():
    history = [{"role": "user", "content": "old " * 400}, {"role": "assistant", "content": "answer [1][2] ok [3, 4]."},
               {"role": "user", "content": "recent question"}, {"role": "assistant", "content": "see [link](x) [5]"}]
    kept = prompts.trim_history(history, 100)
    assert [m["content"] for m in kept] == ["recent question", "see [link](x)"]
    full = prompts.trim_history(history, 10_000)
    assert full[1]["content"] == "answer ok."
    merged = prompts.normalise_turns([{"role": "system", "content": "s"}, {"role": "user", "content": "a"},
                                      {"role": "user", "content": "b"}])
    assert merged == [{"role": "system", "content": "s"}, {"role": "user", "content": "a\n\nb"}]


def test_titles():
    assert prompts.fallback_title("what is the **capital** of France and why") == "What is the capital of France…"
    assert prompts.clean_title('Title: "Capital of France."\nextra') == "Capital of France"
    assert prompts.clean_title("") == ""


def test_system_prompt_modes():
    finance = prompts.system_prompt("finance", True, [])
    assert "financial analyst" in finance and "not personalised investment advice" in finance and "[1]" in finance
    chat = prompts.system_prompt("chat", False, [])
    assert "Sphura" in chat and "Sources:" not in chat
    assert "web_search" in prompts.system_prompt("research", False, ["web_search", "read_page"])


def test_think_filter_handles_split_tags():
    f = ThinkFilter()
    out = "".join(f.feed(p) for p in ["<thi", "nk>secret plan</th", "ink>\nHello", " <b>wor", "ld</b> a < b"])
    assert out + f.flush() == "Hello <b>world</b> a < b"


def test_mock_model_tool_call_then_answer():
    async def collect(messages, tools):
        return [c async for c in mock.stream(messages, tools)]

    tools = [{"type": "function", "function": {"name": "web_search"}}]
    chunks = run(collect([{"role": "user", "content": "search for cats"}], tools))
    calls = [c for c in chunks if c.kind == "tool_calls"][0].tool_calls
    assert calls[0].name == "web_search" and json.loads(calls[0].arguments) == {"query": "search for cats"}

    with_sources = "search for cats\n\n---\nContext\n\nSources:\n[1] Cats — cats.org (https://cats.org)\nmeow"
    chunks = run(collect([{"role": "user", "content": with_sources}], tools))
    text = "".join(c.text for c in chunks if c.kind == "text")
    assert "[1]" in text and not any(c.kind == "tool_calls" for c in chunks)


def _status_error(cls, status: int, message: str):
    request = httpx2.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx2.Response(status, request=request)
    return cls(message, response=response, body={"error": {"message": message}})


def test_provider_errors_become_short_messages():
    e = map_error(_status_error(openai.AuthenticationError, 401, "Invalid API Key"), "groq", "m")
    assert e.kind == "auth" and "GROQ_API_KEY" in e.message
    e = map_error(_status_error(openai.RateLimitError, 429, "Rate limit reached"), "groq", "m")
    assert e.kind == "rate_limit" and e.retryable_elsewhere
    e = map_error(_status_error(openai.NotFoundError, 404, "model not found"), "ollama", "qwen2.5:7b")
    assert e.kind == "not_found" and "ollama pull qwen2.5:7b" in e.message
    e = map_error(_status_error(openai.BadRequestError, 400, "gemma does not support tools"), "ollama", "gemma")
    assert e.kind == "tools"
    conn = openai.APIConnectionError(request=httpx2.Request("POST", "http://localhost:11434/v1/chat/completions"))
    e = map_error(conn, "ollama", "qwen2.5:7b")
    assert e.kind == "connection" and "isn't running" in e.message
