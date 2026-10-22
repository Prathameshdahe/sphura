"""Cross-module regressions: the draft prompt on a small budget, Postgres-safe writes, zip bombs in office
uploads and DuckDuckGo's flaky "No results"."""
from __future__ import annotations

import asyncio
import json
import uuid

import pandas as pd
import pytest

from app.agent import prompts
from app.agent.nodes.draft import build_messages
from app.agent.run import AgentRun, Turn
from app.agent.tools import tools_for
from app.db.models import SafeString, SafeText
from app.features.finance.report import analyze_file
from app.features.memory.plugin import fit_budget, recall_block
from app.llm.types import ResolvedModel
from app.rag import formats
from app.rag.blocks import ParseError
from app.rag.parsers import parse_file
from app.schemas import ModelInfo
from app.tools import web
from tests.conftest import parse_sse

GROQ_LIKE = ResolvedModel("groq:small", "groq", "small",
                          ModelInfo(id="groq:small", provider="groq", label="Small", description="test",
                                    available=True, supports_tools=True), 3800)


# ── prompt budget: memory + analytics + many sources + every tool on a ~4k-token model ──
def test_draft_prompt_fits_a_small_budget():
    turn = Turn(user_id="u", conversation_id="c", is_new=False, question="Where does my money go each month? " * 3,
                history=[{"role": "user", "content": "hi " * 200}, {"role": "assistant", "content": "ok " * 400}],
                doc_ids=[], web_search=True, mode="chat", effort="balanced", model=GROQ_LIKE)
    run = AgentRun(turn, lambda e, d: None)
    run.intent = "spending"
    for i in range(12):
        run.registry.add_page(f"https://ex{i}.com/a", f"Title {i}", "word " * 2000, f"ex{i}.com")
    budget = GROQ_LIKE.prompt_budget
    run.extra_system.append(recall_block(fit_budget(["m" * 480] * 8, budget)))
    run.extra_system.append("Finance analytics: " + "f" * 560)
    tools = tools_for("spending", with_documents=True)
    messages = build_messages(run, {"question": turn.question, "messages": []}, tools)
    text = sum(prompts.estimate_tokens(m.content) for m in messages)
    schemas = prompts.estimate_tokens(json.dumps([t.args_schema.model_json_schema() for t in tools]))
    assert text + schemas <= budget
    assert messages[0].type == "system" and messages[-1].type == "human"


def test_memory_recall_is_capped_by_the_model_budget():
    long = ["m" * 480] * 8
    small = fit_budget(long, 3800)
    assert 1 <= len(small) < 8 and sum(len(c) + 3 for c in small) <= 3800 * 4 * 0.08
    assert fit_budget(long, 40_000) == long                       # big cloud budgets keep all eight
    assert fit_budget(["short fact"] * 8, 3800) == ["short fact"] * 8  # typical short facts all fit
    assert fit_budget([], 3800) == []


# ── Postgres-safe writes ─────────────────────────────────────────────────────
def test_text_columns_drop_nul_characters():
    assert SafeText().process_bind_param("a\x00b\x00", None) == "ab"
    assert SafeString(10).process_bind_param("plain", None) == "plain"
    assert SafeText().process_bind_param(None, None) is None


def test_chat_with_a_nul_character_is_saved_without_it(client, user):
    r = client.post("/api/chat", headers=user["headers"], json={
        "content": "hello\x00 world", "webSearch": False, "docIds": [], "mode": "chat", "effort": "fast"})
    assert r.status_code == 200
    events = parse_sse(r.text)
    conv_id = events[0][1]["conversationId"]
    detail = client.get(f"/api/conversations/{conv_id}", headers=user["headers"]).json()
    assert detail["messages"][0]["content"] == "hello world"
    assert "\x00" not in detail["conversation"]["title"]


def test_overlong_model_id_is_rejected_before_it_reaches_a_varchar_200(client, user):
    r = client.post("/api/chat", headers=user["headers"], json={
        "content": "hi", "model": "groq:" + "x" * 300, "webSearch": False, "docIds": [], "mode": "chat"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


# ── zip bombs in .docx / .xlsx ───────────────────────────────────────────────
def _xlsx(tmp_path):
    path = tmp_path / "book.xlsx"
    pd.DataFrame({"Date": ["2026-01-01", "2026-01-02"], "Amount": [10, -5]}).to_excel(path, index=False)
    return path


def test_zip_packages_that_expand_too_far_are_refused(tmp_path, monkeypatch):
    path = _xlsx(tmp_path)
    assert not formats.zip_too_large(path)
    assert parse_file(path, "book.xlsx").blocks  # a normal workbook still parses
    monkeypatch.setattr(formats, "MAX_ZIP_EXPANDED_BYTES", 100)
    assert formats.zip_too_large(path)
    with pytest.raises(ParseError, match="expands"):
        parse_file(path, "book.xlsx")
    report = analyze_file(path, "book.xlsx", str(uuid.uuid4()))  # finance degrades to a warning, never a 500
    assert report["warnings"] and report["totals"] is None
    assert not formats.zip_too_large(tmp_path / "missing.xlsx")


# ── web search: DuckDuckGo's intermittent "No results" ───────────────────────
def test_duckduckgo_no_results_is_retried_once(monkeypatch):
    calls: list[str] = []

    def flaky(query, max_results):
        calls.append(query)
        if len(calls) == 1:
            raise RuntimeError("No results found.")
        return [{"title": "T", "href": "https://example.org/a", "body": "snippet"}]

    monkeypatch.setattr(web, "_ddg_sync", flaky)
    monkeypatch.setattr(web, "DDG_RETRY_DELAY_S", 0)
    monkeypatch.setattr(web.settings, "tavily_api_key", "")
    results = asyncio.run(web.web_search("ordinary query"))
    assert len(calls) == 2 and [r.url for r in results] == ["https://example.org/a"] and results.error is None

    def empty(query, max_results):
        calls.append(query)
        raise RuntimeError("No results found.")

    calls.clear()
    monkeypatch.setattr(web, "_ddg_sync", empty)
    results = asyncio.run(web.web_search("nothing at all"))
    assert len(calls) == web.DDG_ATTEMPTS and len(results) == 0 and results.error is None
