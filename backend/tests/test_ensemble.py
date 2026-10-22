"""One best model per provider + Sphura Ensemble, computed charts, P&L detection and the TTS provider chain."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import app.agent.nodes.classify as classify_node
import app.agent.nodes.draft as draft_node
import app.agent.nodes.ensemble as ensemble_node
from app.agent import charts, lifecycle
from app.features.finance.report import analyze_file, summary_markdown
from app.features.voice import service as voice
from app.llm import registry
from app.llm.catalog import ENSEMBLE_ID
from tests.test_core_chat import first, send
from tests.test_fin_agent import ScriptedChatModel
from tests.test_w2_finance import BANK, REPO, add_doc

GROQ = "groq:openai/gpt-oss-120b"
NVIDIA = "nvidia:nvidia/nemotron-3.5-super-vl-120b-a12b"
LIGHTNING = "nvidia:nvidia/nemotron-3.5-lightning-30b-a3b"
DEEPSEEK = "nvidia:deepseek-ai/deepseek-v4.1-flash"
COMPANY = REPO / "samples" / "test_workbooks" / "company_financials_fy26.xlsx"


@pytest.fixture
def cloud_keys(monkeypatch):
    monkeypatch.setattr(registry.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(registry.settings, "nvidia_api_key", "test-key")


@pytest.fixture
def curated(monkeypatch, cloud_keys):
    monkeypatch.setattr(registry.settings, "curated_models", True)


# ── catalog ──────────────────────────────────────────────────────────────────
def test_curated_picker_lists_the_ensemble_and_one_model_per_provider(curated):
    models = registry.list_models()
    ids = [m.id for m in models]
    assert ids[:3] == [ENSEMBLE_ID, GROQ, NVIDIA]
    assert [m.provider for m in models[:4]] == ["ensemble", "groq", "nvidia", "ollama"]
    assert models[0].available and models[0].label == "Sphura Ensemble"
    assert not models[3].available  # Ollama is unreachable in tests: shown as a hint, not as a member
    assert registry.ensemble_members() == [GROQ, NVIDIA]


def test_the_ensemble_resolves_to_its_lead_with_the_members_attached(curated):
    m = registry.resolve_model(ENSEMBLE_ID)
    assert m.id == ENSEMBLE_ID and (m.provider, m.name) == ("groq", "openai/gpt-oss-120b")
    assert m.extra == {"ensemble": [GROQ, NVIDIA], "lead": GROQ}


def test_nvidia_failures_try_lightning_then_deepseek(curated):
    assert registry.fallback_models(NVIDIA, "rate_limit")[:2] == [LIGHTNING, GROQ]
    chain = registry.fallback_models(NVIDIA, "server")
    assert chain.index(LIGHTNING) < chain.index(DEEPSEEK)
    assert registry.fallback_models(GROQ, "server")[-2:] == [LIGHTNING, DEEPSEEK]


# ── an ensemble turn ─────────────────────────────────────────────────────────
def test_an_ensemble_turn_streams_only_the_merged_answer(client, user, curated, monkeypatch):
    async def no_llm_classify(run, question):
        return None

    monkeypatch.setattr(classify_node, "_llm_classify", no_llm_classify)
    lead = ScriptedChatModel(script=["Lead| draft.", "Merged| final| answer."], seen=[], bound=[])
    member = ScriptedChatModel(script=["Member| answer."], seen=[], bound=[])

    def factory(resolved, **kwargs):
        return lead if resolved.id == ENSEMBLE_ID else member

    monkeypatch.setattr(draft_node, "chat_model", factory)
    monkeypatch.setattr(ensemble_node, "chat_model", factory)
    _, events = send(client, user, content="explain what an EMI is", model=ENSEMBLE_ID)
    done = first(events, "done")["message"]
    deltas = "".join(d["text"] for e, d in events if e == "delta")
    assert done["status"] == "complete" and done["content"] == "Merged final answer."
    assert deltas == done["content"]  # the lead's own draft never reached the client
    names = [s["name"] for s in done["steps"]]
    assert "ensemble" in names and names.count("ensemble_member") == 2 and "ensemble_merge" in names
    meta = done["meta"]["ensemble"]
    assert meta["lead"] == GROQ and [m["id"] for m in meta["members"]] == [GROQ, NVIDIA]
    merge_prompt = lead.seen[-1][-1].content
    assert "### Candidate 1\nLead draft." in merge_prompt and "### Candidate 2\nMember answer." in merge_prompt


def test_a_single_usable_candidate_is_sent_without_a_merge(client, user, curated, monkeypatch):
    async def no_llm_classify(run, question):
        return None

    async def member_fails(run, model_id, question):
        return {"id": model_id, "label": model_id, "ok": False, "ms": 1, "text": "", "error": "down"}

    monkeypatch.setattr(classify_node, "_llm_classify", no_llm_classify)
    monkeypatch.setattr(ensemble_node, "_ask", member_fails)
    lead = ScriptedChatModel(script=["Only the lead answered."], seen=[], bound=[])
    monkeypatch.setattr(draft_node, "chat_model", lambda resolved, **kw: lead)
    _, events = send(client, user, content="explain what an EMI is", model=ENSEMBLE_ID)
    done = first(events, "done")["message"]
    assert done["content"] == "Only the lead answered."
    assert "".join(d["text"] for e, d in events if e == "delta") == done["content"]
    assert "ensemble_merge" not in [s["name"] for s in done["steps"]]


def test_a_cold_local_member_is_skipped_not_waited_for(monkeypatch):
    monkeypatch.setattr(lifecycle, "is_warm", lambda name: False)
    monkeypatch.setattr(ensemble_node, "gpu_busy", lambda: False)

    class Run:
        turn = type("T", (), {"effort": "balanced"})()
        steps: list = []

        def step_start(self, name, label):
            self.steps.append({"name": name, "label": label})
            return len(self.steps) - 1

        def step_end(self, i, status, detail):
            self.steps[i].update(status=status, detail=detail)

    run = Run()
    out = asyncio.run(ensemble_node._ask(run, "ollama:qwen3.5:4b", "q"))
    assert out["ok"] is False and out["error"] == "cold" and "loading" in run.steps[0]["detail"]


# ── charts ───────────────────────────────────────────────────────────────────
def test_a_spending_answer_ends_with_computed_charts(client, user):
    bank = add_doc(user["user"]["id"], BANK)
    _, events = send(client, user, content="where did my money go last month?", docIds=[bank])
    done = first(events, "done")["message"]
    blocks = [json.loads(b.split("\n", 1)[1].rsplit("```", 1)[0]) for b in done["content"].split("```chart")[1:]]
    assert [c["type"] for c in blocks] == ["pie", "bar"]
    pie = blocks[0]
    assert pie["title"] == "Spending by category" and pie["unit"] == "₹" and len(pie["labels"]) == len(pie["series"][0]["data"])
    assert blocks[1]["labels"][-1] == "Sep 2026" and [s["name"] for s in blocks[1]["series"]] == ["In", "Out"]
    assert "".join(d["text"] for e, d in events if e == "delta") == done["content"]


def test_citation_clean_up_leaves_chart_data_alone():
    from app.agent.nodes.verify import drop_phantom_citations
    from app.agent.prompts import strip_citations

    chart = '```chart\n{"type":"bar","labels":["a","b"],"series":[{"name":"x","data":[120,340]}]}\n```'
    answer = f"Fixed [1] and [7].\n\n{chart}\n\nDone [2]."
    assert drop_phantom_citations(answer, 1) == f"Fixed [1] and.\n\n{chart}\n\nDone."
    assert strip_citations(answer) == f"Fixed and.\n\n{chart}\n\nDone."


def test_wide_bracket_citations_are_normalised_and_periods_parsed():
    from app.agent.nodes.market import _period
    from app.agent.nodes.verify import normalise_citations

    assert normalise_citations("Up 11% 【3】, then down 【1†L2-L5】.") == "Up 11% [3], then down [1]."
    assert [_period(q) for q in ("last 3 months", "past month", "6 months", "this year")] == ["3mo", "1mo", "6mo", "1y"]


def test_chart_helpers():
    spec = {"type": "bar", "title": "T", "unit": "₹", "labels": ["a", "b"], "series": [{"name": "x", "data": [1, 2]}]}
    block = charts.charts_block([spec, spec, spec])
    assert block.count("```chart") == charts.MAX_PER_ANSWER and charts.has_chart(block)
    history = {"symbol": "TCS.NS", "period": "1y",
               "points": [{"date": f"2026-01-{d:02d}", "close": 100.0 + d} for d in range(1, 29)] * 5}
    line = charts.history_chart(history)
    assert line["type"] == "line" and line["unit"] == "₹" and len(line["labels"]) <= charts.MAX_POINTS + 1


# ── profit and loss ──────────────────────────────────────────────────────────
def test_a_workbook_with_a_pnl_sheet_gets_margins_growth_and_roe():
    r = analyze_file(COMPANY, COMPANY.name, "d1")
    pnl = r["profitLoss"]
    assert r["kind"] == "balance_sheet" and r["amountUnit"] == "crore"
    assert (pnl["revenue"], pnl["netProfit"], pnl["period"]) == (4215.6, 271.95, "FY 2025-26")
    assert pnl["netMargin"] == pytest.approx(271.95 / 4215.6, abs=1e-4)
    assert pnl["revenueGrowth"] == pytest.approx(4215.6 / 3870.25 - 1, abs=1e-4)
    assert pnl["ebitda"] == pytest.approx(363.55 + 61.75 + 128.4)
    assert pnl["returnOnEquity"] == pytest.approx(271.95 / 1966.35, abs=1e-4)
    assert r["insights"][0].startswith("Revenue ₹4,216 crore, up 8.9%")
    assert "Profit and loss (FY 2025-26)" in summary_markdown(r)
    pnl_chart = charts.report_charts(r)[0]
    assert pnl_chart["title"] == "Profit and loss" and pnl_chart["unit"] == "₹ crore" and len(pnl_chart["series"]) == 2


def test_a_pnl_only_file_is_read_as_a_profit_and_loss_statement(tmp_path: Path):
    csv = tmp_path / "pl.csv"
    csv.write_text("Particulars,FY 2025-26,FY 2024-25\nSales,1200000,1000000\nPurchases,700000,620000\n"
                   "Salaries,180000,170000\nRent,120000,120000\nNet profit,200000,90000\n", encoding="utf-8")
    r = analyze_file(csv, csv.name, "d2")
    pnl = r["profitLoss"]
    assert r["kind"] == "table" and pnl["revenue"] == 1200000 and pnl["netProfit"] == 200000
    assert pnl["profitGrowth"] == pytest.approx(200000 / 90000 - 1, abs=1e-4)
    assert summary_markdown(r).startswith("Computed financial analysis of pl.csv (profit and loss statement")


# ── text to speech ───────────────────────────────────────────────────────────
@pytest.fixture
def fresh_voice(monkeypatch):
    monkeypatch.setattr(voice, "_skip_until", {})
    monkeypatch.setattr(voice, "_cache", voice.OrderedDict())


def test_retry_hints_are_read():
    assert voice._retry_after("Please retry in 9h23m9.35s.") == 9 * 3600
    assert voice._retry_after("'retryDelay': '33789s'") == 33789
    assert voice._retry_after("try later") == 0


def test_tts_uses_orpheus_then_gemini_and_caches(monkeypatch, fresh_voice):
    monkeypatch.setattr(voice.settings, "groq_api_key", "k")
    monkeypatch.setattr(voice.settings, "gemini_api_key", "k")
    calls = []

    async def orpheus(text, v):
        calls.append("orpheus")
        voice._skip("orpheus", "terms not accepted")
        raise voice.VoiceError("refused")

    async def gemini(text, v):
        calls.append("gemini")
        return b"RIFF-wav"

    monkeypatch.setattr(voice, "_speak_orpheus", orpheus)
    monkeypatch.setattr(voice, "_speak_gemini", gemini)
    assert asyncio.run(voice.speak("Hello there.")) == b"RIFF-wav"
    assert asyncio.run(voice.speak("Hello there.")) == b"RIFF-wav"  # cached
    assert asyncio.run(voice.speak("Second sentence.")) == b"RIFF-wav"  # Orpheus is skipped now
    assert calls == ["orpheus", "gemini", "gemini"] and voice.tts_provider() == "gemini"


def test_when_every_tts_provider_refuses_the_browser_voice_takes_over(client, user, monkeypatch, fresh_voice):
    monkeypatch.setattr(voice.settings, "groq_api_key", "k")
    monkeypatch.setattr(voice.settings, "gemini_api_key", "")

    async def orpheus(text, v):
        voice._skip("orpheus", "terms not accepted")
        raise voice.VoiceError("refused")

    monkeypatch.setattr(voice, "_speak_orpheus", orpheus)
    assert client.get("/api/voice/status", headers=user["headers"]).json() == {
        "stt": True, "tts": True, "ttsProvider": "orpheus"}
    r = client.post("/api/voice/speak", json={"text": "Hello."}, headers=user["headers"])
    assert r.status_code == 503  # not 502: the client switches to speechSynthesis
    assert client.get("/api/voice/status", headers=user["headers"]).json()["tts"] is False
