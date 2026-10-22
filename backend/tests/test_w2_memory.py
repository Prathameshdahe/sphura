"""Long-term memory: API CRUD + settings, recall injection (stubbed embeddings), extraction, dedupe, secrets."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid

import pytest

from app.agent.run import AgentRun, Turn
from app.features.memory import extract, ranking
from app.features.memory import plugin as memory_plugin_mod
from app.features.memory.plugin import RECALL_HEADER
from app.features.memory.plugin import plugin as memory_plugin
from app.llm import registry
from app.llm.types import ResolvedModel
from app.schemas import ModelInfo
from app.tools import web
from tests.conftest import parse_sse

CLOUD = ResolvedModel("groq:test-model", "groq", "test-model",
                      ModelInfo(id="groq:test-model", provider="groq", label="Test", description="test",
                                available=True), 8000)
SYNONYMS = {"likes": "prefers", "short": "concise", "brief": "concise"}


_VOCAB: dict[str, int] = {}


def _vector(text: str) -> list[float]:
    """Bag-of-words over a growing vocabulary (collision-free, deterministic); synonyms share a dimension."""
    vec = [0.0] * 512
    for word in re.findall(r"[a-z]+", text.lower()):
        word = SYNONYMS.get(word, word)
        if word not in {"the", "a", "is", "to", "i", "do", "how", "use", "should"}:
            vec[_VOCAB.setdefault(word, len(_VOCAB) % 512)] += 1.0
    return vec


@pytest.fixture
def fake_embeddings(monkeypatch):
    calls = {"passages": 0, "query": 0}

    def passages(texts):
        calls["passages"] += 1
        return [_vector(t) for t in texts]

    def query(text):
        calls["query"] += 1
        return _vector(text)

    monkeypatch.setattr(ranking, "embed_passages", passages)
    monkeypatch.setattr(ranking, "embed_query", query)
    return calls


@pytest.fixture
def fake_llm(monkeypatch):
    """registry.complete returning `state["reply"]` (after `state["delay"]` s); calls are recorded."""
    state: dict = {"reply": json.dumps({"facts": []}), "delay": 0.0, "calls": []}

    async def complete(model, messages, temperature=0.2, json_mode=False, timeout=30.0):
        state["calls"].append({"model": model, "messages": messages, "json_mode": json_mode})
        if state["delay"]:
            await asyncio.sleep(state["delay"])
        return state["reply"]

    monkeypatch.setattr(registry, "complete", complete)
    return state


def make_run(user: dict, question: str, model: ResolvedModel | None = None, conversation_id: str | None = None):
    events: list = []
    turn = Turn(user_id=user["user"]["id"], conversation_id=conversation_id or str(uuid.uuid4()), is_new=False,
                question=question, history=[], doc_ids=[], web_search=False, mode="chat", effort="fast",
                model=model or registry.resolve_model("mock:sphura-mock"))
    return AgentRun(turn, lambda e, d: events.append((e, d))), events


async def _turn(run: AgentRun) -> None:
    await memory_plugin.before_answer(run)
    run.content = "An answer."
    await memory_plugin.after_answer(run)


def remember(client, user, content: str) -> dict:
    r = client.post("/api/memory", json={"content": content}, headers=user["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def items(client, user) -> list[dict]:
    return client.get("/api/memory", headers=user["headers"]).json()["items"]


# ── API ──────────────────────────────────────────────────────────────────────
def test_memory_crud_settings_and_ownership(client, user, other_user):
    h = user["headers"]
    assert client.get("/api/memory", headers=h).json() == {"enabled": True, "items": []}
    assert client.get("/api/memory").status_code == 401

    first = remember(client, user, "Prefers concise answers")
    assert set(first) == {"id", "content", "createdAt", "sourceMessageId"}
    assert first["createdAt"].endswith("Z") and first["sourceMessageId"] is None
    assert remember(client, user, "  prefers   CONCISE answers. ")["id"] == first["id"]  # duplicate → same item
    second = remember(client, user, "Is a final-year computer science student")
    assert [i["id"] for i in items(client, user)] == [second["id"], first["id"]]  # newest first

    r = client.post("/api/memory", json={"content": "My password is hunter2"}, headers=h)
    assert r.status_code == 400 and isinstance(r.json()["detail"], str)
    r = client.post("/api/memory", json={"content": ""}, headers=h)
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    project = remember(client, user, "Is building a credit card fraud detection model")  # a topic, not a secret
    assert client.delete(f"/api/memory/{project['id']}", headers=h).status_code == 204

    assert client.get("/api/memory", headers=other_user["headers"]).json()["items"] == []
    r = client.delete(f"/api/memory/{first['id']}", headers=other_user["headers"])
    assert r.status_code == 404 and r.json() == {"detail": "Memory not found"}
    assert client.delete(f"/api/memory/{first['id']}", headers=h).status_code == 204
    assert [i["id"] for i in items(client, user)] == [second["id"]]

    r = client.put("/api/memory/settings", json={"enabled": False}, headers=h)
    assert r.status_code == 200 and r.json() == {"enabled": False}
    assert client.get("/api/memory", headers=h).json()["enabled"] is False
    assert client.put("/api/memory/settings", json={"enabled": True}, headers=h).json() == {"enabled": True}

    remember(client, other_user, "Likes chess")
    assert client.delete("/api/memory", headers=h).status_code == 204
    assert items(client, user) == [] and len(items(client, other_user)) == 1


# ── recall ───────────────────────────────────────────────────────────────────
@pytest.fixture
def offline_web(monkeypatch):
    async def no_results(query, max_results=6):
        return web.SearchResults([], provider="fake")

    async def no_page(url, max_chars=12000):
        return web.PageContent(url=url, title="", text="")

    monkeypatch.setattr(web, "web_search", no_results)
    monkeypatch.setattr(web, "read_page", no_page)


def test_chat_recalls_memories_into_the_prompt(client, user, monkeypatch, offline_web):
    remember(client, user, "Prefers concise answers")
    remember(client, user, "Codes mostly in Python")
    seen: list[str] = []
    real_stream = registry.chat_stream

    async def spy_stream(model, messages, *args, **kwargs):
        seen.append(messages[0]["content"])
        async for chunk in real_stream(model, messages, *args, **kwargs):
            yield chunk

    monkeypatch.setattr(registry, "chat_stream", spy_stream)
    r = client.post("/api/chat", json={"content": "Explain decorators", "webSearch": False, "docIds": [],
                                       "mode": "chat", "effort": "fast"}, headers=user["headers"])
    events = parse_sse(r.text)
    steps = [d for e, d in events if e == "step" and d["name"] == "memory_recall"]
    assert steps[-1]["status"] == "done" and steps[-1]["detail"] == "2 memories"
    done = next(d for e, d in events if e == "done")["message"]
    assert done["meta"]["memoryUsed"] == 2 and "memoriesAdded" not in done["meta"]
    assert RECALL_HEADER in seen[0] and "- Codes mostly in Python" in seen[0]

    client.put("/api/memory/settings", json={"enabled": False}, headers=user["headers"])
    seen.clear()
    r = client.post("/api/chat", json={"content": "Explain decorators", "webSearch": False, "docIds": [],
                                       "mode": "chat", "effort": "fast"}, headers=user["headers"])
    events = parse_sse(r.text)
    assert not [d for e, d in events if e == "step" and d["name"] == "memory_recall"]
    assert "memoryUsed" not in (next(d for e, d in events if e == "done")["message"]["meta"] or {})
    assert RECALL_HEADER not in seen[0]


def test_recall_ranks_by_similarity_when_there_are_many(client, user, fake_embeddings):
    facts = ["Codes mostly in Python", "Prefers concise answers", "Is a final-year student", "Loves cricket",
             "Drinks coffee every morning", "Uses Linux at home", "Plays music on weekends",
             "Wants to travel to Japan", "Likes pizza", "Plays chess online"]
    for fact in facts:  # oldest first
        remember(client, user, fact)
    run, events = make_run(user, "How do I write a python decorator?")
    asyncio.run(memory_plugin.before_answer(run))

    block = run.extra_system[0].split("\n")
    assert block[0] == RECALL_HEADER and len(block) == 9
    assert block[1] == "- Codes mostly in Python"           # most similar first
    assert "- Prefers concise answers" not in block and "- Is a final-year student" not in block  # oldest ties
    assert run.meta_extra["memoryUsed"] == 8 and fake_embeddings["query"] == 1
    step = [d for e, d in events if e == "step"][-1]
    assert step["name"] == "memory_recall" and step["detail"] == "8 memories"


def test_recall_falls_back_to_recency_without_embeddings(client, user, monkeypatch):
    for i in range(10):
        remember(client, user, f"Fact number {i} about the user")
    monkeypatch.setattr(ranking, "embed_query", lambda text: None)
    run, _ = make_run(user, "anything")
    asyncio.run(memory_plugin.before_answer(run))
    block = run.extra_system[0].split("\n")[1:]
    assert block == [f"- Fact number {i} about the user" for i in range(9, 1, -1)]


# ── extraction ───────────────────────────────────────────────────────────────
def test_extraction_saves_new_facts_dedupes_and_filters_secrets(client, user, fake_llm, fake_embeddings):
    r = client.post("/api/chat", json={"content": "I prefer concise answers", "webSearch": False, "docIds": [],
                                       "mode": "chat", "effort": "fast"}, headers=user["headers"])
    events = parse_sse(r.text)
    start = next(d for e, d in events if e == "start")
    conv_id, user_msg_id = start["conversationId"], start["userMessage"]["id"]
    assert not [c for c in fake_llm["calls"] if c["json_mode"]]  # the mock model uses rules, never a JSON call
    done = next(d for e, d in events if e == "done")["message"]
    assert done["meta"]["memoriesAdded"] == ["Prefers concise answers"]
    fake_llm["calls"].clear()
    assert remember(client, user, "Prefers concise answers.")["sourceMessageId"] == user_msg_id  # duplicate

    fake_llm["reply"] = "```json\n" + json.dumps({"facts": [
        "Prefers concise answers", "Password is hunter2", "Is building a chatbot called Sphura", "Is a student",
    ]}) + "\n```"
    run, _ = make_run(user, "I prefer concise answers and I'm building a chatbot called Sphura. "
                            "My password is hunter2.", CLOUD, conv_id)
    asyncio.run(_turn(run))
    call = fake_llm["calls"][0]
    assert call["json_mode"] is True and call["messages"][0]["role"] == "system"
    assert run.meta_extra["memoriesAdded"] == ["Is building a chatbot called Sphura"]
    saved = items(client, user)
    assert [i["content"] for i in saved] == ["Is building a chatbot called Sphura", "Prefers concise answers"]
    assert saved[0]["sourceMessageId"] == user_msg_id
    assert not any("hunter2" in i["content"] for i in saved)

    # near-duplicate (cosine ≥ 0.9 on embeddings) and text duplicate → nothing new
    fake_llm["reply"] = json.dumps({"facts": ["Likes short answers", "is building a chatbot called sphura!"]})
    run, _ = make_run(user, "I like short answers, and I am building a chatbot called Sphura", CLOUD, conv_id)
    asyncio.run(_turn(run))
    assert "memoriesAdded" not in run.meta_extra and len(items(client, user)) == 2


def test_extraction_skips_and_falls_back_to_rules(client, user, fake_llm, monkeypatch):
    monkeypatch.setattr(ranking, "embed_passages", lambda texts: None)  # text-only dedupe
    fake_llm["reply"] = json.dumps({"facts": ["Is a data scientist"]})
    run, _ = make_run(user, "What is a transformer?", CLOUD)  # no first-person statement
    asyncio.run(_turn(run))
    client.put("/api/memory/settings", json={"enabled": False}, headers=user["headers"])
    run, _ = make_run(user, "I am a data scientist", CLOUD)
    asyncio.run(_turn(run))
    assert "memoriesAdded" not in run.meta_extra and fake_llm["calls"] == [] and items(client, user) == []

    # the LLM answered, but not with JSON → the rule-based fallback still finds the fact
    client.put("/api/memory/settings", json={"enabled": True}, headers=user["headers"])
    fake_llm["reply"] = "not json at all"
    run, _ = make_run(user, "I am a data scientist", CLOUD)
    asyncio.run(_turn(run))
    assert len(fake_llm["calls"]) == 1 and run.meta_extra["memoriesAdded"] == ["Is a data scientist"]

    # a valid empty list is trusted (no rule fallback)
    fake_llm["reply"] = json.dumps({"facts": []})
    run, _ = make_run(user, "I live in Pune", CLOUD)
    asyncio.run(_turn(run))
    assert "memoriesAdded" not in run.meta_extra

    # offline/local models (the mock here) never make the JSON call: rules only
    fake_llm["calls"].clear()
    run, _ = make_run(user, "My name is arjun. I mostly code in Python, what about you?")
    asyncio.run(_turn(run))
    assert fake_llm["calls"] == [] and run.meta_extra["memoriesAdded"] == ["Name is Arjun", "Codes in Python"]
    contents = [i["content"] for i in items(client, user)]
    assert set(contents[:2]) == {"Name is Arjun", "Codes in Python"} and contents[2:] == ["Is a data scientist"]


@pytest.mark.parametrize(("message", "facts"), [
    ("I'm a final-year CSE student and I'm building a diabetes prediction model",
     ["Is a final-year CSE student", "Is building a diabetes prediction model"]),
    ("Hey! I’m a second-year B.Tech student at VIT.", ["Is a second-year B.Tech student at VIT"]),
    ("I am working on my final year project on NLP, can you help me with the dataset?",
     ["Is working on their final year project on NLP"]),
    ("I prefer concise answers. My password is hunter2.", ["Prefers concise answers"]),
    ("I work as a backend developer at Infosys", ["Works as a backend developer at Infosys"]),
    ("I study at IIT Bombay and I live in Pune", ["Studies at IIT Bombay", "Lives in Pune"]),
    ("I want to become a data scientist", ["Wants to become a data scientist"]),
    ("I'm building a credit card fraud detection model", ["Is building a credit card fraud detection model"]),
    ("I was diagnosed with asthma and I'm a teacher", ["Is a teacher"]),
    ("What is my name?", []), ("I'm a bit confused about attention", []), ("I like this answer", []),
    ("Explain transformers like I'm a 5 year old", []), ("If I am a student, what discounts can I get?", []),
    ("I'm not a student", []), ("I live at 221B Baker Street", []), ("I use it for work", []),
    ('Translate "I am a doctor" into French', []), ("Correct this sentence: I am a engineer", []),
    ("> I am a lawyer and I live in Delhi", []), ("Summarise this:\n```\nI am a robot.\n```", []),
    ("I prefer the first option", []), ("I am learning a lot from you", []), ("I'm working on it", []),
])
def test_rule_based_extraction(message, facts):
    assert extract.rule_facts(message) == facts


def test_slow_ranking_falls_back_to_recency(client, user, monkeypatch):
    for i in range(10):
        remember(client, user, f"Fact number {i} about the user")
    monkeypatch.setattr(memory_plugin_mod, "RANK_TIMEOUT_S", 0.05)
    monkeypatch.setattr(ranking, "rank", lambda question, items, limit: time.sleep(0.5) or items[::-1][:limit])
    run, _ = make_run(user, "anything")

    async def scenario() -> float:
        started = time.perf_counter()
        await memory_plugin.before_answer(run)
        return time.perf_counter() - started

    assert asyncio.run(scenario()) < 0.45
    assert run.extra_system[0].split("\n")[1:] == [f"- Fact number {i} about the user" for i in range(9, 1, -1)]
    assert run.meta_extra["memoryUsed"] == 8


def test_slow_extraction_never_delays_done_and_is_saved_later(client, user, fake_llm, monkeypatch):
    monkeypatch.setattr(memory_plugin_mod, "SAVE_WAIT_S", 0.05)
    monkeypatch.setattr(ranking, "embed_passages", lambda texts: None)  # text-only dedupe
    fake_llm.update(delay=0.3, reply=json.dumps({"facts": ["Is learning Rust"]}))

    async def scenario() -> float:
        run, _ = make_run(user, "I am learning Rust these days", CLOUD)
        await memory_plugin.before_answer(run)
        run.content = "An answer."
        started = time.perf_counter()
        await memory_plugin.after_answer(run)
        elapsed = time.perf_counter() - started
        assert "memoriesAdded" not in run.meta_extra
        await asyncio.sleep(0.8)
        return elapsed

    assert asyncio.run(scenario()) < 0.25
    assert [i["content"] for i in items(client, user)] == ["Is learning Rust"]


# ── filters ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "My password is hunter2", "API key sk-abcdefghijklmnop1234", "Card 4111 1111 1111 1111",
    "Email me at someone@example.com", "Bank account number is 001234567", "Phone +91 98765 43210",
    "Token " + "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789",  # split so secret scanners don't flag a fake token
])
def test_secrets_are_detected(text):
    assert extract.is_secret(text) and extract.is_sensitive(text)


def test_sensitive_filter_keeps_ordinary_facts():
    assert extract.is_sensitive("Was diagnosed with asthma") and not extract.is_secret("Was diagnosed with asthma")
    for fine in ("Prefers concise answers", "Is building a diabetes prediction model", "Is in the 2023-2024 batch",
                 "Uses Python 3.13 and PyTorch", "Is building a credit card fraud detection model",
                 "Is building a health insurance cost predictor", "Is working on a mental health chatbot",
                 "Is building a diabetes diagnosis model", "Is building an OTP verification system",
                 "Likes to pin important tabs", "Uses sklearn-pipelines for preprocessing", "Uses UPI for payments"):
        assert not extract.is_sensitive(fine), fine
    for secret in ("PIN is 4321", "Credit card number is on file", "Card ends in 42", "UPI ID is rahul@okaxis",
                   "SSN: 123-45-6789", "Key AKIAABCDEFGHIJKLMNOP"):
        assert extract.is_secret(secret), secret
    for health in ("Has diabetes", "Blood group is O+", "Was prescribed antidepressants", "Is pregnant"):
        assert extract.is_sensitive(health) and not extract.is_secret(health), health
    assert extract.clean_facts({"facts": ["prefers dark mode", "Bank account number is 12345678901",
                                          "What is AI?", "x", "Prefers dark mode", "Takes medication daily"]}) == [
        "Prefers dark mode"]
    assert extract.clean_facts(["Is a teacher", {"fact": "Lives in Pune"}, "Likes tea"]) == [
        "Is a teacher", "Lives in Pune"]
    assert extract.clean_facts("garbage") == [] and extract.parse_json("nope") is None
    assert extract.worth_extracting("I'm a student") and not extract.worth_extracting("What is attention?")
