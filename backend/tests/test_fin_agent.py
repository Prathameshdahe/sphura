"""The LangGraph finance agent with the mock model and fakes: routing per persona, guardrails, tool loop,
fail-over, GPU flag, model continuity, lifecycle warm-up and the /api/agent/graph export. No network."""
from __future__ import annotations

import asyncio
import json
import sys
import types
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app.agent import classify as classify_mod
from app.agent import lifecycle, models
from app.agent.guard import ADVICE_DISCLAIMER, REFUSAL, redact
import app.agent.nodes.draft as draft_node
from app.agent.run import AgentRun
from app.api import chat as chat_api
from app.features.market import service as market_service
from app.llm import local, registry
from app.llm.catalog import decorate, default_model_id, local_label
from app.llm.types import LLMError
from app.schemas import ModelInfo
from app.tools import web
from tests.test_core_chat import first, names, send
from tests.test_w2_finance import BALANCE, BANK, add_doc

MOCK = "mock:sphura-mock"
GROQ_BIG, GROQ_SMALL = "groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"


@pytest.fixture(autouse=True)
def keyword_router(monkeypatch, tmp_path):
    monkeypatch.setattr(classify_mod, "ROUTER_PATH", tmp_path / "missing-router.joblib")


@pytest.fixture
def no_rag(monkeypatch):
    async def fake_search_documents(user_id, query, doc_ids, k=8):
        return []

    fake = types.ModuleType("app.rag.service")
    fake.search_documents = fake_search_documents
    monkeypatch.setitem(sys.modules, "app.rag.service", fake)


@pytest.fixture
def fake_market(monkeypatch):
    calls = {"quote": [], "news": [], "history": []}

    async def get_quote(symbol):
        calls["quote"].append(symbol)
        return {"symbol": symbol, "name": "Tata Consultancy Services", "price": 4123.45, "currency": "INR",
                "change": 12.3, "changePercent": 0.3, "dayHigh": 4150.0, "dayLow": 4100.0, "previousClose": 4111.15,
                "asOf": "2026-10-22T10:00:00Z", "source": "yfinance", "delayed": True, "cached": False}

    async def get_history(symbol, period="1mo"):
        calls["history"].append((symbol, period))
        return {"symbol": symbol, "period": period, "points": [{"date": "2026-09-22", "close": 4000.0},
                                                               {"date": "2026-10-22", "close": 4123.45}],
                "source": "yfinance", "asOf": "2026-10-22T10:00:00Z", "cached": False}

    async def finance_news(query):
        calls["news"].append(query)
        return {"items": [{"title": "HDFC Bank profit surges 20%", "url": "https://www.livemint.com/hdfc",
                           "domain": "livemint.com", "snippet": "Strong quarter.", "publishedAt": None,
                           "sentiment": {"label": "positive", "score": 0.9}}], "cached": False,
                "sentimentModel": "lexicon"}

    monkeypatch.setattr(market_service, "get_quote", get_quote)
    monkeypatch.setattr(market_service, "get_history", get_history)
    monkeypatch.setattr(market_service, "finance_news", finance_news)
    return calls


# ── a scripted LangChain chat model (replaces app.agent.models.chat_model in a test) ──
class ScriptedChatModel(BaseChatModel):
    """Plays `script` turn by turn: a str streams as text, a list of (name, args) streams tool calls,
    an Exception is raised before the first token."""

    script: list[Any]
    seen: list[list[BaseMessage]]
    bound: list[Any] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.bound.append([t.name for t in tools])
        return self.bind(tools=list(tools), **kwargs)

    def _generate(self, messages, stop=None, run_manager: CallbackManagerForLLMRun | None = None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="A title"))])

    async def _astream(self, messages, stop=None, run_manager: AsyncCallbackManagerForLLMRun | None = None,
                       **kwargs) -> AsyncIterator[ChatGenerationChunk]:
        self.seen.append(list(messages))
        step = self.script.pop(0) if self.script else "No script left."
        if isinstance(step, float):  # a pause before the first token (cold local model)
            await asyncio.sleep(step)
            step = self.script.pop(0) if self.script else "No script left."
        if isinstance(step, Exception):
            raise step
        chunks: list[AIMessageChunk] = []
        if isinstance(step, str):
            chunks = [AIMessageChunk(content=piece) for piece in step.split("|")]
        else:
            chunks = [AIMessageChunk(content="", tool_call_chunks=[
                ToolCallChunk(name=name, args=json.dumps(args), id=f"call_{i}", index=i)
                for i, (name, args) in enumerate(step)])]
        for message in chunks:
            chunk = ChatGenerationChunk(message=message)
            if run_manager is not None:
                await run_manager.on_llm_new_token(chunk.text, chunk=chunk)
            yield chunk


@pytest.fixture
def scripted(monkeypatch):
    """`scripted(script, per_model=None)` installs a scripted model; returns the model for inspection."""
    state: dict[str, Any] = {}

    def install(script: list[Any], per_model: dict[str, list[Any]] | None = None) -> ScriptedChatModel:
        model = ScriptedChatModel(script=list(script), seen=[], bound=[])
        state["models"] = {}

        def factory(resolved, **kwargs):
            if per_model and resolved.id in per_model:
                return state["models"].setdefault(resolved.id, ScriptedChatModel(script=list(per_model[resolved.id]),
                                                                                  seen=[], bound=[]))
            return model

        monkeypatch.setattr(draft_node, "chat_model", factory)
        return model

    return install


# ── routing per persona (keyword classifier) ────────────────────────────────
def test_explain_question_goes_straight_to_the_model(client, user):
    _, events = send(client, user, content="what is a SIP?")
    done = first(events, "done")["message"]
    assert done["meta"]["router"]["label"] == "explain"
    assert [s["name"] for s in done["steps"]] == ["router"]
    assert [d["phase"] for e, d in events if e == "status"] == ["thinking", "composing"]
    assert "## Sphura mock answer" in done["content"] and done["sources"] == []


def test_out_of_scope_refuses_without_calling_the_model(client, user, monkeypatch):
    async def never(*args, **kwargs):
        raise AssertionError("the model must not be called for an off-topic question")
        yield  # pragma: no cover

    monkeypatch.setattr(registry, "chat_stream", never)
    for question in ("write a Python script that sorts a list", "recipe for biryani", "who won the match yesterday?"):
        _, events = send(client, user, content=question)
        seq = names(events)
        assert seq[0] == "start" and seq[-1] == "done" and seq.count("delta") == 1
        done = first(events, "done")["message"]
        assert done["content"] == REFUSAL and done["status"] == "complete"
        assert done["meta"]["router"]["label"] == "out_of_scope"
        assert [s["name"] for s in done["steps"]] == ["router"] and done["sources"] == []
        assert first(events, "title")["title"]  # fallback title, no LLM either


def test_advice_request_gets_education_plus_disclaimer(client, user):
    _, events = send(client, user, content="should I buy Reliance?")
    done = first(events, "done")["message"]
    assert done["meta"]["router"]["label"] == "advice"
    assert done["content"].rstrip().endswith(ADVICE_DISCLAIMER)
    assert done["content"] == "".join(d["text"] for e, d in events if e == "delta")


def test_spending_branch_cites_computed_figures(client, user, no_rag):
    bank = add_doc(user["user"]["id"], BANK)
    _, events = send(client, user, content="where did my money go last month?", docIds=[bank])
    done = first(events, "done")["message"]
    assert done["meta"]["router"] == {"label": "spending", "confidence": 1.0, "autoSearch": False}
    assert done["meta"]["analytics"] == {"docIds": [bank]} and done["meta"]["finance"] == {"docIds": [bank]}
    phases = [d["label"] for e, d in events if e == "status"]
    assert "Crunching your statements" in phases
    step = next(s for s in done["steps"] if s["name"] == "finance_analyze")
    assert step["status"] == "done" and step["detail"].startswith("Bank statement · 6 months")
    src = done["sources"][0]
    assert src["type"] == "doc" and src["docId"] == bank and src["title"] == "bank_statement_demo.csv — Computed analysis"
    assert src["snippet"].startswith("Computed financial analysis of bank_statement_demo.csv")
    assert "[1]" in done["content"]


def test_spending_without_attachment_uses_every_ready_statement(client, user, no_rag):
    add_doc(user["user"]["id"], BALANCE)
    _, events = send(client, user, content="is my liquidity healthy?")
    done = first(events, "done")["message"]
    assert done["meta"]["router"]["label"] == "spending"
    step = next(s for s in done["steps"] if s["name"] == "finance_analyze")
    assert "current ratio 3.02" in step["detail"]


def test_market_branch_fetches_quote_and_news(client, user, fake_market):
    _, events = send(client, user, content="TCS share price today")
    done = first(events, "done")["message"]
    assert done["meta"]["router"]["label"] == "market" and done["meta"]["market"] == {"symbols": ["TCS.NS"]}
    assert fake_market["quote"] == ["TCS.NS"] and fake_market["news"] == []  # a price question: no news search
    assert any(e == "status" and d == {"phase": "searching", "label": "Fetching market data"} for e, d in events)
    assert [s["name"] for s in done["steps"]] == ["router", "get_quote"]
    quote = done["steps"][1]
    assert quote["status"] == "done" and quote["detail"] == "4,123.45 INR (+0.30%)"
    assert [s["type"] for s in done["sources"]] == ["web"]
    assert done["sources"][0]["domain"] == "finance.yahoo.com" and "4,123.45 INR" in done["sources"][0]["snippet"]
    assert "[1]" in done["content"]

    _, events = send(client, user, content="news about HDFC Bank")
    done = first(events, "done")["message"]
    assert done["meta"]["market"] == {"symbols": ["HDFCBANK.NS"]}
    assert fake_market["quote"][-1] == "HDFCBANK.NS" and fake_market["news"] == ["HDFC Bank"]
    assert [s["name"] for s in done["steps"]] == ["router", "get_quote", "finance_news"]
    assert done["steps"][2]["detail"] == "1 headline"
    news = done["sources"][1]
    assert news["type"] == "web" and news["domain"] == "livemint.com" and news["snippet"].startswith("[positive 0.90]")


def test_web_toggle_forces_the_market_branch(client, user, fake_market):
    _, events = send(client, user, content="what is happening with Indian banks", webSearch=True)
    done = first(events, "done")["message"]
    assert done["meta"]["router"] == {"label": "market", "confidence": 1.0, "autoSearch": True}
    assert fake_market["news"] and not fake_market["quote"]


def test_market_errors_degrade_to_notes(client, user, monkeypatch):
    async def down(symbol):
        raise market_service.MarketError("No market data found for TCS.NS (unknown symbol or market closed)")

    async def no_news(query):
        raise market_service.MarketError("Web search is unavailable right now")

    monkeypatch.setattr(market_service, "get_quote", down)
    monkeypatch.setattr(market_service, "finance_news", no_news)
    _, events = send(client, user, content="news about TCS")
    done = first(events, "done")["message"]
    assert done["status"] == "complete"
    assert [(s["name"], s["status"]) for s in done["steps"]] == [("router", "done"), ("get_quote", "error"),
                                                                 ("finance_news", "error")]


# ── guardrails ───────────────────────────────────────────────────────────────
def test_guard_in_redacts_a_card_number_before_the_model_sees_it(client, user, monkeypatch):
    seen: list[list[dict]] = []
    real = registry.chat_stream

    async def spy(model, messages, *args, **kwargs):
        seen.append(messages)
        async for chunk in real(model, messages, *args, **kwargs):
            yield chunk

    monkeypatch.setattr(registry, "chat_stream", spy)
    question = "My card 4111 1111 1111 1111 and PAN ABCDE1234F were used; how do I budget for the EMI?"
    _, events = send(client, user, content=question)
    done = first(events, "done")["message"]
    assert done["status"] == "complete" and done["meta"]["redacted"] == ["card", "pan"]
    guard = next(s for s in done["steps"] if s["name"] == "guard_in")
    assert guard["status"] == "done" and "card number" in guard["detail"]
    flat = json.dumps(seen)
    assert "4111" not in flat and "ABCDE1234F" not in flat and "[card number redacted]" in flat
    assert first(events, "start")["userMessage"]["content"] == question  # the user's own message is kept


def test_redaction_patterns():
    clean, kinds = redact("card 4111-1111-1111-1111, aadhaar 2345 6789 0123, account 9876543210, pin 4321")
    assert "4111" not in clean and "6789" not in clean and "9876543210" not in clean and "4321" not in clean
    assert set(kinds) == {"card", "aadhaar", "account"}
    assert redact("EMI of 21,696 on 25,00,000 at 8.5%") == ("EMI of 21,696 on 25,00,000 at 8.5%", [])
    assert redact("my salary is 85000 and rent 22000") == ("my salary is 85000 and rent 22000", [])


# ── draft ⇄ tools loop, fail-over ───────────────────────────────────────────
def test_tool_loop_runs_emi_and_cites_the_result(client, user, scripted):
    model = scripted([[("emi", {"principal": 2500000, "annual_rate_pct": 8.5, "months": 240})],
                      "Your EMI would be about ₹21,696 per month [1]."])
    _, events = send(client, user, content="EMI for 25 lakh home loan at 8.5% for 20 years")
    done = first(events, "done")["message"]
    assert done["status"] == "complete" and done["content"] == "Your EMI would be about ₹21,696 per month [1]."
    assert done["meta"]["router"]["label"] == "explain"
    emi_step = next(s for s in done["steps"] if s["name"] == "emi")
    assert emi_step["status"] == "done" and emi_step["label"] == "Calculating the EMI" and "emi: 21695" in emi_step["detail"]
    src = done["sources"][0]
    assert src["type"] == "doc" and src["filename"] == "Sphura calculators" and "emi: 21695" in src["snippet"]
    assert any(e == "status" and d == {"phase": "analyzing", "label": "Calculating"} for e, d in events)
    # round 2 saw the tool result as a tool message; tools were bound both rounds (balanced = 3 rounds)
    assert len(model.seen) == 2 and model.seen[1][-1].type == "tool" and "21695" in model.seen[1][-1].content
    assert model.bound and "emi" in model.bound[0] and "search_documents" not in model.bound[0]


def test_tool_preamble_is_held_back_and_effort_caps_rounds(client, user, scripted):
    model = scripted(["Let me calculate that.", [("sip_future_value", {"monthly": 5000, "annual_return_pct": 12,
                                                                        "years": 10})],
                      "Final: ₹11.6 lakh [1]."])
    model.script = [[("sip_future_value", {"monthly": 5000, "annual_return_pct": 12, "years": 10})], "Done [1]."]
    _, events = send(client, user, content="what will a 5000 SIP at 12% give in 10 years", effort="fast")
    done = first(events, "done")["message"]
    # fast = 1 tool round: the second draft is made without tools and must answer (see the round-budget test)
    assert done["content"] == "Done [1]."
    assert [s["name"] for s in done["steps"]].count("sip_future_value") == 1
    assert len(model.bound) == 1 and len(model.seen) == 2


def test_fail_over_from_groq_to_another_model_before_the_first_token(client, user, scripted, monkeypatch):
    monkeypatch.setattr(registry.settings, "groq_api_key", "test-key")
    scripted([], per_model={GROQ_BIG: [LLMError("Groq rate limit reached for openai/gpt-oss-120b.", "rate_limit")],
                            GROQ_SMALL: ["Answered by the 20B model."]})
    _, events = send(client, user, content="explain the old vs new tax regime briefly", model=GROQ_BIG)
    done = first(events, "done")["message"]
    assert done["status"] == "complete" and done["content"] == "Answered by the 20B model."
    assert done["model"] == GROQ_SMALL and done["meta"]["fallbackFrom"] == GROQ_BIG
    switch = next(s for s in done["steps"] if s["name"] == "switch_model")
    assert switch["status"] == "done" and "rate limit" in switch["detail"].lower()
    assert first(events, "start")["model"] == GROQ_BIG


def test_a_cloud_timeout_fails_over_but_a_local_one_does_not(client, user, scripted, monkeypatch):
    """An overloaded cloud model (Gemini 504 after a minute) is abandoned; a local model that is still loading is not."""
    monkeypatch.setattr(registry.settings, "groq_api_key", "test-key")
    scripted([], per_model={GROQ_BIG: [LLMError("Groq took too long to respond.", "timeout")],
                            GROQ_SMALL: ["Answer from the fallback."]})
    _, events = send(client, user, content="explain SIP", model=GROQ_BIG)
    assert first(events, "done")["message"]["content"] == "Answer from the fallback."
    assert models.can_fail_over(LLMError("slow", "timeout"), "gemini")
    assert not models.can_fail_over(LLMError("slow", "timeout"), "ollama")


def test_provider_error_mapping():
    import httpx

    assert models.to_llm_error(LLMError("x", "auth"), "groq", "m").kind == "auth"
    err = models.to_llm_error(httpx.ConnectError("refused"), "ollama", "qwen3.5:4b")
    assert err.kind == "connection" and "isn't running" in err.message

    class Status(Exception):
        def __init__(self, code, msg):
            super().__init__(msg)
            self.status_code = code

    assert models.to_llm_error(Status(429, "Rate limit"), "groq", "m").kind == "rate_limit"
    assert models.to_llm_error(Status(401, "bad key"), "gemini", "m").kind == "auth"
    assert models.to_llm_error(Status(503, "overloaded"), "gemini", "m").kind == "server"
    assert models.to_llm_error(Status(404, "model not found"), "ollama", "x").kind == "not_found"
    assert models.to_llm_error(httpx.ReadTimeout("slow"), "ollama", "x").kind == "timeout"
    assert not models.can_fail_over(LLMError("slow", "timeout"), "ollama") and models.can_fail_over(LLMError("x", "server"))


# ── model choice: continuity, GPU flag, labels ───────────────────────────────
def _info(model_id: str, available: bool = True, provider: str | None = None) -> ModelInfo:
    provider = provider or model_id.split(":", 1)[0]
    return ModelInfo(id=model_id, provider=provider, label=model_id, description="", available=available)


def test_conversation_keeps_the_previous_turns_model(monkeypatch):
    monkeypatch.setattr(registry.settings, "default_model", "")
    infos = [_info("groq:openai/gpt-oss-20b"), _info("ollama:qwen3.5:4b"), _info(MOCK)]
    monkeypatch.setattr(chat_api, "list_models", lambda: infos)
    monkeypatch.setattr(chat_api, "resolve_model", lambda mid: mid)
    assert chat_api._choose_model("ollama:qwen3.5:4b") == "ollama:qwen3.5:4b"
    assert chat_api._choose_model("ollama:gone:1b") == "groq:openai/gpt-oss-20b"  # unavailable → default order
    assert chat_api._choose_model(None) == "groq:openai/gpt-oss-20b"


def test_default_order_and_local_labels(monkeypatch):
    monkeypatch.setattr(registry.settings, "default_model", "")
    infos = [_info("ollama:nemotron-3-nano:4b"), _info("ollama:qwen3.5:4b"), _info(MOCK), _info("ollama:sphura-fin-1.7b")]
    assert default_model_id(infos) == "ollama:qwen3.5:4b"  # the fine-tuned model has no tool template
    assert default_model_id([_info("ollama:sphura-fin-1.7b"), _info("ollama:nemotron-3-nano:4b")]) == "ollama:nemotron-3-nano:4b"
    assert default_model_id([_info("ollama:nemotron-3-nano:4b"), _info(MOCK)]) == "ollama:nemotron-3-nano:4b"
    assert default_model_id([_info("gemini:x"), _info("groq:y", available=False)]) == "gemini:x"
    labelled = {m.id: (m.label, m.is_default) for m in decorate(infos)}
    assert labelled["ollama:qwen3.5:4b"] == ("Qwen 3.5 4B (local)", True)
    assert labelled["ollama:nemotron-3-nano:4b"] == ("NVIDIA Nemotron 3 Nano 4B (local)", False)
    assert labelled["ollama:sphura-fin-1.7b"] == ("Sphura Fin 1.7B (fine-tuned)", False)
    assert local_label("sphura-fin-1.7b:q4")[0] == "Sphura Fin 1.7B (fine-tuned)"


def test_models_endpoint_marks_the_mock_default_here(client, user):
    models_out = client.get("/api/models", headers=user["headers"]).json()
    assert [m["id"] for m in models_out if m["isDefault"]] == [MOCK]


def test_gpu_busy_flag_swaps_a_local_model_for_the_mock(client, user, monkeypatch, tmp_path):
    flag = tmp_path / "GPU_BUSY"
    flag.write_text("training", encoding="utf-8")
    monkeypatch.setattr(models, "GPU_BUSY_FLAG", flag)
    _, events = send(client, user, content="what is an ETF?", model="ollama:qwen3.5:4b")
    assert first(events, "start")["model"] == MOCK and names(events)[-1] == "done"
    monkeypatch.setattr(registry.settings, "sphura_enable_mock", False)
    r, _ = send(client, user, content="what is an ETF?", model="ollama:qwen3.5:4b")
    assert r.status_code == 503 and "busy" in r.json()["detail"]


# ── lifecycle: warm-up keeps the preferred local model loaded ───────────────
def test_warm_up_posts_keep_alive_for_the_preferred_model(monkeypatch, tmp_path):
    posted: list[tuple[str, dict]] = []

    class FakeClient:
        async def post(self, url, json):
            posted.append((url, json))

            class R:
                def raise_for_status(self):
                    return None

            return R()

        async def aclose(self):
            return None

    monkeypatch.setattr(local, "discover", lambda provider: local.LocalStatus(
        reachable=True, models=["nemotron-3-nano:4b", "qwen3.5:4b"]))
    monkeypatch.setattr(models, "GPU_BUSY_FLAG", tmp_path / "GPU_BUSY")
    assert asyncio.run(lifecycle.warm_up_once(FakeClient())) == "qwen3.5:4b"
    assert posted == [(f"{models.native_ollama_base()}/api/generate",
                       {"model": "qwen3.5:4b", "prompt": "Hi", "stream": False, "think": False, "keep_alive": "45m",
                        "options": {"num_ctx": models.LOCAL_NUM_CTX, "num_predict": 1}})]
    assert lifecycle.warm_model() == "qwen3.5:4b"

    (tmp_path / "GPU_BUSY").write_text("1", encoding="utf-8")
    posted.clear()
    assert asyncio.run(lifecycle.warm_up_once(FakeClient())) is None and posted == []
    # a training job appeared: the warmed model is unloaded (keep_alive 0) so the GPU is free for it
    assert asyncio.run(lifecycle.release_local(FakeClient())) == ["qwen3.5:4b"]
    assert posted == [(f"{models.native_ollama_base()}/api/generate", {"model": "qwen3.5:4b", "keep_alive": 0})]
    assert lifecycle.warm_model() is None and asyncio.run(lifecycle.release_local(FakeClient())) == []


def test_warm_up_is_silent_without_ollama(monkeypatch):
    monkeypatch.setattr(local, "discover", lambda provider: local.LocalStatus(reachable=False))
    assert asyncio.run(lifecycle.warm_up_once()) is None


# ── graph export ─────────────────────────────────────────────────────────────
def test_agent_graph_export(client, user):
    assert client.get("/api/agent/graph").status_code == 401
    g = client.get("/api/agent/graph", headers=user["headers"]).json()
    assert set(g) == {"mermaid", "nodes", "edges"}
    ids = [n["id"] for n in g["nodes"]]
    assert ids == ["__start__", "guard_in", "classify", "analytics", "retrieve", "market", "draft", "tools",
                   "verify", "finalize", "ensemble", "refuse", "__end__"]
    assert all(set(n) == {"id", "label"} and n["label"] for n in g["nodes"])
    edges = {(e["source"], e["target"]) for e in g["edges"]}
    assert {("__start__", "guard_in"), ("guard_in", "classify"), ("classify", "analytics"), ("classify", "retrieve"),
            ("classify", "market"), ("classify", "draft"), ("classify", "refuse"), ("analytics", "draft"),
            ("retrieve", "draft"), ("market", "draft"), ("draft", "tools"), ("tools", "draft"), ("draft", "verify"),
            ("verify", "finalize"), ("finalize", "__end__"), ("refuse", "__end__"), ("draft", "ensemble"),
            ("ensemble", "verify")} <= edges
    assert all(set(e) == {"source", "target", "label"} for e in g["edges"])
    assert g["mermaid"].startswith("---") and "guard_in" in g["mermaid"] and "draft" in g["mermaid"]


def test_checkpointer_file_and_state_per_conversation(client, user):
    from app.core.config import settings

    assert (settings.data_dir / "graph.db").exists()
    _, events = send(client, user, content="what is an index fund?")
    cid = first(events, "start")["conversationId"]
    saver = lifecycle.checkpointer()
    assert saver is not None

    async def latest():
        return await saver.aget({"configurable": {"thread_id": cid}})

    # the checkpoint belongs to the TestClient's loop; read it through the app's portal
    checkpoint = client.portal.call(latest)
    assert checkpoint is not None and checkpoint["channel_values"]["intent"] == "explain"
    assert checkpoint["channel_values"]["draft"].startswith("## Sphura mock answer")


def test_agent_crash_still_ends_with_error_event(client, user, monkeypatch):
    async def boom(self):
        raise RuntimeError("bug")

    monkeypatch.setattr(AgentRun, "run", boom)
    _, events = send(client, user, content="anything about money")
    assert names(events)[0] == "start" and names(events)[-1] == "error"
    assert first(events, "error")["message"] == chat_api.GENERIC_ERROR


def test_unused_fixture_guard(fake_market, no_rag):
    """Keeps the shared fixtures importable even when a persona test is skipped."""
    assert fake_market["quote"] == [] and uuid.uuid4()
    assert web.domain_of("https://www.livemint.com/x") == "livemint.com"


# ── routing: every persona question (docs/FINANCE_PLAN.md section 6) through the graph ──
PERSONAS = [
    ("bank", ["where did my money go last month?", "any subscriptions I forgot?",
              "how much can I save if I cut dining by half?"], ["spending"] * 3),
    (None, ["I earn 12 LPA, which tax regime is better?", "EMI for 25 lakh home loan at 8.5% for 20 years",
            "how does 80C work?"], ["explain"] * 3),
    ("balance", ["is my liquidity healthy?", "current ratio and what it means", "what should I watch?"],
     ["spending"] * 3),
    (None, ["what is a SIP?", "TCS share price today", "news about HDFC Bank", "should I buy Reliance?"],
     ["explain", "market", "market", "advice"]),
    (None, ["write a Python script that sorts a list", "recipe for biryani", "who won the match yesterday?"],
     ["out_of_scope"] * 3),
]


@pytest.mark.parametrize("upload,questions,expected", PERSONAS, ids=["asha", "rahul", "meera", "vikram", "offtopic"])
def test_persona_questions_take_the_right_branch(client, user, no_rag, fake_market, upload, questions, expected):
    doc_ids = [add_doc(user["user"]["id"], BANK if upload == "bank" else BALANCE)] if upload else []
    conversation_id = None
    for question, intent in zip(questions, expected):
        _, events = send(client, user, content=question, docIds=doc_ids, conversationId=conversation_id)
        conversation_id = first(events, "start")["conversationId"]
        done = first(events, "done")["message"]
        assert done["meta"]["router"]["label"] == intent, question
        step_names = [s["name"] for s in done["steps"]]
        if intent == "spending":
            assert "finance_analyze" in step_names and done["sources"][0]["docId"] == doc_ids[0]
        if intent == "out_of_scope":
            assert done["content"] == REFUSAL and step_names == ["router"]
        if intent == "advice":
            assert done["content"].rstrip().endswith(ADVICE_DISCLAIMER)


def _fake_router(monkeypatch, label: str, confidence: float):
    monkeypatch.setattr(classify_mod, "router_predict",
                        lambda text: classify_mod.Classification(label, confidence, "router"))


def test_off_topic_is_refused_even_with_the_web_toggle_or_attachments(monkeypatch):
    _fake_router(monkeypatch, "out_of_scope", 0.99)
    for kwargs in ({"web_search": True}, {"attached": ["bank.csv"]}, {"follow_up": True}):
        assert classify_mod.classify("recipe for biryani", **kwargs).intent == "out_of_scope"
    # without the router (artifact missing) the keyword classifier alone still refuses clear off-topic text
    monkeypatch.setattr(classify_mod, "router_predict", lambda text: None)
    assert classify_mod.classify("who won the match?", web_search=True).intent == "out_of_scope"
    assert classify_mod.classify("what is happening with Indian banks", web_search=True).intent == "market"


def test_a_follow_up_is_not_refused_on_the_router_alone(monkeypatch):
    _fake_router(monkeypatch, "out_of_scope", 0.97)
    assert classify_mod.classify("what should I watch?").intent == "out_of_scope"           # first message
    assert classify_mod.classify("what should I watch?", follow_up=True).intent == "spending"  # keywords decide


def test_a_strong_market_or_advice_prediction_beats_the_attachment_rule(monkeypatch):
    _fake_router(monkeypatch, "market", 0.98)
    assert classify_mod.classify("TCS share price today", attached=["bank.csv"]).intent == "market"
    _fake_router(monkeypatch, "explain", 0.98)
    assert classify_mod.classify("current ratio and what it means", attached=["bs.csv"]).intent == "spending"
    _fake_router(monkeypatch, "market", 0.7)
    assert classify_mod.classify("anything", attached=["policy.pdf"]).intent == "documents"


def test_trained_router_routes_the_persona_questions(monkeypatch):
    """With the training engineer's artifact (skipped when it or its embedding model is unavailable)."""
    real = classify_mod.BACKEND_DIR / "ml" / "artifacts" / "fin_router.joblib"
    if not real.exists():
        pytest.skip("trained router artifact not present")
    monkeypatch.setattr(classify_mod, "ROUTER_PATH", real)
    if classify_mod.router_predict("what is a SIP?") is None:
        pytest.skip("trained router could not run here (embedding model unavailable)")
    for upload, questions, expected in PERSONAS:
        attached = ["statement.csv"] if upload else []
        for i, (question, intent) in enumerate(zip(questions, expected)):
            got = classify_mod.classify(question, attached=attached, follow_up=i > 0)
            assert got.intent == intent, (question, got)


def test_refusal_makes_no_model_call_even_with_a_cloud_model(client, user, monkeypatch):
    monkeypatch.setattr(registry.settings, "groq_api_key", "test-key")

    async def never_complete(*args, **kwargs):
        raise AssertionError("no LLM call for an off-topic message")

    def never_model(*args, **kwargs):
        raise AssertionError("no chat model for an off-topic message")

    monkeypatch.setattr(registry, "complete", never_complete)
    monkeypatch.setattr(draft_node, "chat_model", never_model)
    monkeypatch.setattr(models, "chat_model", never_model)
    _, events = send(client, user, content="I prefer concise answers. Write a Python script that sorts a list.",
                     model=GROQ_BIG)
    done = first(events, "done")["message"]
    assert done["content"] == REFUSAL and done["status"] == "complete" and done["model"] == GROQ_BIG
    assert done["meta"]["memoriesAdded"] == ["Prefers concise answers"]  # rule-based memory still works


# ── local models: continuity after a fail-over, warm model first, loading labels ──
def test_conversation_stays_on_the_model_it_failed_over_to(monkeypatch):
    monkeypatch.setattr(chat_api, "list_models",
                        lambda: [_info("ollama:qwen3.5:4b"), _info("ollama:nemotron-3-nano:4b")])
    monkeypatch.setattr(chat_api, "resolve_model", lambda mid: types.SimpleNamespace(id=mid))
    qwen = types.SimpleNamespace(id="ollama:qwen3.5:4b")

    def prepared(last_model, last_requested):
        return chat_api._Prepared("c", False, {}, "q", [], [], last_model, last_requested)

    kept = chat_api._keep_conversation_model(qwen, prepared("ollama:nemotron-3-nano:4b", "ollama:qwen3.5:4b"))
    assert kept.id == "ollama:nemotron-3-nano:4b"   # same picker choice as last turn → no 3 GB reload
    assert chat_api._keep_conversation_model(qwen, prepared("ollama:nemotron-3-nano:4b", None)) is qwen
    assert chat_api._keep_conversation_model(qwen, prepared("groq:x", "ollama:qwen3.5:4b")) is qwen  # gone


def test_failed_over_answer_is_kept_for_the_next_turn(client, user, scripted, monkeypatch):
    monkeypatch.setattr(registry.settings, "groq_api_key", "test-key")
    scripted([], per_model={GROQ_BIG: [LLMError("Groq rate limit reached.", "rate_limit")],
                            GROQ_SMALL: ["First answer.", "Second answer."]})
    _, events = send(client, user, content="explain SIP briefly", model=GROQ_BIG)
    cid = first(events, "start")["conversationId"]
    assert first(events, "done")["message"]["model"] == GROQ_SMALL
    _, events = send(client, user, content="and what is an EMI?", model=GROQ_BIG, conversationId=cid)
    assert first(events, "start")["model"] == GROQ_SMALL
    done = first(events, "done")["message"]
    assert done["content"] == "Second answer." and done["meta"]["modelKept"] == {"requested": GROQ_BIG}
    # the user picks another model: that choice wins
    _, events = send(client, user, content="and an FD?", model=MOCK, conversationId=cid)
    assert first(events, "start")["model"] == MOCK


def test_fail_over_prefers_the_warm_local_model(monkeypatch, tmp_path):
    monkeypatch.setattr(models, "GPU_BUSY_FLAG", tmp_path / "GPU_BUSY")
    monkeypatch.setattr(registry, "fallback_models", lambda current, kind: [
        "ollama:nemotron-3-nano:4b", "gemini:gemini-3.8-flash", "ollama:qwen3.5:4b", "ollama:sphura-fin-1.7b"])
    monkeypatch.setattr(lifecycle, "_warm", {})
    assert models.fallback_candidates("groq:x", "rate_limit") == [
        "gemini:gemini-3.8-flash", "ollama:qwen3.5:4b", "ollama:nemotron-3-nano:4b", "ollama:sphura-fin-1.7b"]
    lifecycle.mark_warm("nemotron-3-nano:4b")
    assert models.fallback_candidates("groq:x", "rate_limit")[1] == "ollama:nemotron-3-nano:4b"
    (tmp_path / "GPU_BUSY").write_text("1", encoding="utf-8")
    assert models.fallback_candidates("groq:x", "rate_limit") == ["gemini:gemini-3.8-flash"]


def test_cold_local_model_shows_loading_labels_and_is_never_failed_over(client, user, scripted, monkeypatch,
                                                                        tmp_path):
    monkeypatch.setattr(models, "GPU_BUSY_FLAG", tmp_path / "GPU_BUSY")
    monkeypatch.setattr(lifecycle, "_warm", {})
    monkeypatch.setattr(draft_node, "SLOW_NOTICE_S", 0.05)
    scripted([0.3, "Answer from the local model."])
    _, events = send(client, user, content="explain SIP", model="ollama:qwen3.5:4b")
    labels = [d["label"] for e, d in events if e == "status"]
    assert labels.index(draft_node.LOADING) < labels.index(draft_node.SLOW_LABEL) < labels.index(draft_node.WRITING)
    done = first(events, "done")["message"]
    assert done["model"] == "ollama:qwen3.5:4b" and done["content"] == "Answer from the local model."
    assert lifecycle.is_warm("qwen3.5:4b")   # it answered, so the next turn says "Writing the answer"
    scripted(["Warm answer."])
    _, events = send(client, user, content="explain EMI", model="ollama:qwen3.5:4b")
    labels = [d["label"] for e, d in events if e == "status"]
    assert draft_node.LOADING not in labels and draft_node.WRITING in labels


def test_warm_up_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("SPHURA_OLLAMA_WARMUP", "0")
    assert not lifecycle.warm_up_enabled()
    monkeypatch.setenv("SPHURA_OLLAMA_WARMUP", "1")
    assert lifecycle.warm_up_enabled()


def test_warm_up_target_and_preload_switch(monkeypatch):
    installed = ["nemotron-3-nano:4b", "qwen3.5:4b"]
    monkeypatch.setattr(lifecycle, "_warm", {})
    monkeypatch.setattr(registry.settings, "default_model", "ollama:nemotron-3-nano:4b")
    assert lifecycle.warm_target(installed) == "nemotron-3-nano:4b"   # the configured default is kept resident
    monkeypatch.setattr(registry.settings, "default_model", "groq:openai/gpt-oss-20b")
    assert lifecycle.warm_target(installed) == "qwen3.5:4b"
    assert lifecycle.warm_target(installed + ["sphura-fin-1.7b:latest"]) == "qwen3.5:4b"
    monkeypatch.setattr(lifecycle, "_warm", {"nemotron-3-nano:4b": 1.0})
    assert lifecycle.warm_target(installed) == "nemotron-3-nano:4b"   # the model in use stays resident
    assert not lifecycle.preload_enabled()  # never inside the test runner


# ── review fixes: no tool loop past the round budget, deep effort on a non-thinking model, guardrails ──
def test_tool_calls_after_the_round_budget_end_the_loop(client, user, scripted):
    """A model that keeps asking for tools once none are offered must not loop to the recursion limit."""
    call = [("emi", {"principal": 100000, "annual_rate_pct": 9, "months": 12})]
    model = scripted([call, call, call, call])
    _, events = send(client, user, content="EMI on 1 lakh at 9% for a year", effort="fast")
    assert len(model.seen) == 2 and model.bound == [[t.name for t in draft_node.tools_for("explain", False)]]
    assert [d["name"] for e, d in events if e == "step" and d["status"] == "running"].count("emi") == 1
    assert names(events)[-1] == "error"
    assert first(events, "error")["message"].startswith("The model returned an empty answer")


def test_deep_effort_retries_without_thinking_when_the_model_cannot_think(client, user, monkeypatch):
    class NoThinking(Exception):
        status_code = 400

    asked: list[Any] = []

    def factory(resolved, **kwargs):
        asked.append(kwargs.get("reasoning"))
        step = NoThinking('"sphura-fin-1.7b" does not support thinking') if kwargs.get("reasoning") else "Deep answer."
        return ScriptedChatModel(script=[step], seen=[], bound=[])

    monkeypatch.setattr(draft_node, "chat_model", factory)
    _, events = send(client, user, content="What is an EMI?", effort="deep")
    assert asked == [True, False]
    done = first(events, "done")["message"]
    assert done["content"] == "Deep answer." and done["status"] == "complete"


def test_off_topic_follow_up_is_refused_but_contextual_follow_ups_are_not(monkeypatch):
    _fake_router(monkeypatch, "out_of_scope", 0.99)
    for text in ("tell me about shah rukh khan", "write a haiku about the sea", "who is the prime minister?"):
        assert classify_mod.classify(text, follow_up=True).intent == "out_of_scope", text
    for text in ("why?", "explain it more simply", "can you summarise that in a table", "and for 10 years?"):
        assert classify_mod.classify(text, follow_up=True).intent == "explain", text


def test_small_talk_gets_a_short_template():
    from app.agent.guard import GREETING, THANKS, refusal_text

    assert refusal_text("thanks!") == THANKS and refusal_text("got it") == THANKS
    assert refusal_text("how are you?") == GREETING and refusal_text("hello there") == GREETING
    assert refusal_text("ok now write me a poem please") == REFUSAL


def test_trained_router_refuses_an_off_topic_follow_up(client, user, monkeypatch):
    real = classify_mod.BACKEND_DIR / "ml" / "artifacts" / "fin_router.joblib"
    if not real.exists():
        pytest.skip("trained router artifact not present")
    monkeypatch.setattr(classify_mod, "ROUTER_PATH", real)
    if classify_mod.router_predict("what is a SIP?") is None:
        pytest.skip("trained router could not run here (embedding model unavailable)")

    def never_model(*args, **kwargs):
        raise AssertionError("no chat model for an off-topic follow-up")

    _, events = send(client, user, content="what is a SIP?")
    cid = first(events, "start")["conversationId"]
    monkeypatch.setattr(draft_node, "chat_model", never_model)
    _, events = send(client, user, content="tell me about shah rukh khan", conversationId=cid)
    assert first(events, "done")["message"]["content"] == REFUSAL


def test_no_model_or_busy_gpu_is_refused_before_the_message_is_saved(client, user, monkeypatch, tmp_path):
    flag = tmp_path / "GPU_BUSY"
    flag.write_text("training", encoding="utf-8")
    monkeypatch.setattr(models, "GPU_BUSY_FLAG", flag)
    monkeypatch.setattr(registry.settings, "sphura_enable_mock", False)
    before = client.get("/api/conversations", headers=user["headers"]).json()
    r, _ = send(client, user, content="what is an ETF?", model="ollama:qwen3.5:4b")
    assert r.status_code == 503
    monkeypatch.setattr(chat_api, "_choose_model", lambda last: (_ for _ in ()).throw(
        LLMError("No AI model is available yet.", "unavailable")))
    r, _ = send(client, user, content="what is an ETF?")
    assert r.status_code == 400 and r.json()["detail"] == "No AI model is available yet."
    assert client.get("/api/conversations", headers=user["headers"]).json() == before  # nothing half-created


def test_a_long_last_answer_keeps_the_previous_exchange():
    from app.agent import prompts

    history = [{"role": "user", "content": "EMI for 25 lakh at 8.5% for 20 years?"},
               {"role": "assistant", "content": "The EMI is ₹21,696 [1]. " + "Detail. " * 600}]
    kept = prompts.trim_history(history, 600)
    assert [m["role"] for m in kept] == ["user", "assistant"]
    assert kept[1]["content"].startswith("The EMI is ₹21,696.") and kept[1]["content"].endswith("…")
    assert sum(prompts.estimate_tokens(m["content"]) for m in kept) <= 600


def test_redaction_covers_lowercase_pan_short_accounts_and_pin_phrasing():
    assert redact("pan abcde1234f")[0] == "pan [pan redacted]"
    assert redact("a/c no. 50100123456789") == ("a/c no. [account number redacted]", ["account"])
    assert redact("my account 123456789") == ("my account [account number redacted]", ["account"])
    assert "4321" not in redact("my pin is 4321")[0] and "482913" not in redact("otp: 482913")[0]
    for safe in ("account balance 25000", "what is section 80C and 80CCD(1B)?", "explain form 26AS and ITR-2"):
        assert redact(safe) == (safe, [])


def test_reasoning_chunks_show_a_thinking_label_instead_of_loading(client, user, monkeypatch, tmp_path):
    monkeypatch.setattr(models, "GPU_BUSY_FLAG", tmp_path / "GPU_BUSY")
    monkeypatch.setattr(lifecycle, "_warm", {})
    monkeypatch.setattr(draft_node, "SLOW_NOTICE_S", 0.1)

    class Thinker(ScriptedChatModel):
        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            yield ChatGenerationChunk(message=AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Hm"}))
            await asyncio.sleep(0.3)  # longer than the slow notice: it must not claim the model is loading
            yield ChatGenerationChunk(message=AIMessageChunk(content="Thought-through answer."))

    monkeypatch.setattr(draft_node, "chat_model", lambda resolved, **kwargs: Thinker(script=[], seen=[], bound=[]))
    _, events = send(client, user, content="explain SIP", model="ollama:qwen3.5:4b", effort="deep")
    labels = [d["label"] for e, d in events if e == "status"]
    assert draft_node.THINKING in labels and draft_node.SLOW_LABEL not in labels
    assert labels.index(draft_node.THINKING) < labels.index(draft_node.WRITING)
    assert first(events, "done")["message"]["content"] == "Thought-through answer."
