"""Verified answers: sentence splitting, verdict rules (stubbed NLI), the chat plugin and POST /api/verify."""
from __future__ import annotations

import asyncio
import uuid

import pytest

from app.agent.run import AgentRun, Turn
from app.db.base import session_scope
from app.db.models import Conversation, Message
from app.features.verify import claims as claims_mod
from app.features.verify import nli, verifier
from app.features.verify.claims import extract_claims, parse_citations, split_sentences
from app.features.verify.plugin import plugin as verify_plugin
from app.llm import registry
from app.tools import web
from tests.conftest import parse_sse


class StubScorer:
    """Entailment from the first rule whose key appears in the hypothesis (default 0.0); records every call."""

    name = "stub-nli (test)"

    def __init__(self, rules: dict[str, float] | None = None) -> None:
        self.rules = rules or {}
        self.calls: list[list[tuple[str, str]]] = []

    def entailment(self, pairs):
        self.calls.append(list(pairs))
        return [next((p for key, p in self.rules.items() if key in hyp), 0.0) for _, hyp in pairs]

    @property
    def pairs(self) -> list[tuple[str, str]]:
        return [p for call in self.calls for p in call]


def send(client, user, **body):
    payload = {"content": "", "webSearch": False, "docIds": [], "mode": "chat", "effort": "fast", **body}
    r = client.post("/api/chat", json=payload, headers=user["headers"])
    assert r.status_code == 200, r.text
    return parse_sse(r.text)


def first(events, name):
    return next(d for e, d in events if e == name)


@pytest.fixture
def fake_web(monkeypatch):
    async def fake_search(query, max_results=6):
        return web.SearchResults([
            web.WebResult(title="Attention Is All You Need", url="https://arxiv.org/abs/1706.03762",
                          snippet="The Transformer relies entirely on attention.", domain="arxiv.org", score=0.9),
            web.WebResult(title="Transformer (deep learning)", url="https://en.wikipedia.org/wiki/Transformer",
                          snippet="A transformer is a deep learning architecture.", domain="en.wikipedia.org"),
        ], provider="fake")

    async def fake_read(url, max_chars=12000):
        return web.PageContent(url=url, title="Page", text="Full page text about multi-head attention. " * 20)

    monkeypatch.setattr(web, "web_search", fake_search)
    monkeypatch.setattr(web, "read_page", fake_read)


@pytest.fixture
def stub_scorer(monkeypatch):
    scorer = StubScorer({"first result supports": 0.9})
    monkeypatch.setattr(nli, "_scorer", scorer)
    return scorer


@pytest.fixture
def no_model(monkeypatch):
    monkeypatch.setattr(nli, "_scorer", None)
    monkeypatch.setattr(nli, "_failed_at", None)


# ── sentence splitting ───────────────────────────────────────────────────────
SAMPLE = """## Overview

The Transformer was introduced in 2017 by Vaswani et al. at Google [1]. It relies entirely on attention, e.g. \
self-attention, instead of recurrence.[2] Dr. Smith agrees.

- **Speed**: Groq runs open models very fast [1, 3].
- Short one.
1. Numbered claim about BERT and GPT models [2-3].
> A quoted claim that is fairly long [4].

```python
x = "This is code. It must be skipped entirely."
```

| Model | Params |
|---|---|
| GPT-2 has many parameters in total | 1.5B |

---
What is attention, really?
Final remark without any citation here.
"""


def test_splitter_offsets_are_exact_and_skip_code_tables_headings():
    found = split_sentences(SAMPLE)
    for c in found:
        assert SAMPLE[c.start:c.end] == c.text
    assert [c.text for c in found] == [
        "The Transformer was introduced in 2017 by Vaswani et al. at Google [1].",
        "It relies entirely on attention, e.g. self-attention, instead of recurrence.[2]",
        "**Speed**: Groq runs open models very fast [1, 3].",
        "Numbered claim about BERT and GPT models [2-3].",
        "A quoted claim that is fairly long [4].",
        "Final remark without any citation here.",
    ]
    assert [c.source_indexes for c in found] == [[1], [2], [1, 3], [2, 3], [4], []]
    assert found[2].hypothesis == "Speed: Groq runs open models very fast."
    assert found[0].specific and not found[1].specific and not found[3].specific  # [2-3] is a citation
    intro, code = split_sentences("Here are the 3 main options to consider:\nInstall it with `pip install x==1.2` today.")
    assert not intro.specific and not code.specific
    step, option, version, share = split_sentences(  # the reference-list entry is not a claim
        "Step 1 usually takes a couple of minutes. Option 2 is better for most beginners. Use Python 3.9 or "
        "later for this. About 5% of users see the error.\n[1] Attention Is All You Need — arxiv.org\n"
        "- [2] The Illustrated Transformer — jalammar.github.io\n")
    assert not step.specific and not option.specific and version.specific and share.specific


def test_splitter_handles_crlf_unicode_and_inline_citation_groups():
    content = "Ünïcode prefix — the café opened in 1999 [1][2].\r\nNext line states another fact here [3]. Tail"
    found = split_sentences(content)
    for c in found:
        assert content[c.start:c.end] == c.text
    assert [c.source_indexes for c in found] == [[1, 2], [3]]
    assert parse_citations("a [1, 3] b [2–4] c [3]") == [1, 3, 2, 4]


def test_extract_claims_caps_and_prefers_cited_sentences():
    content = " ".join(f"Plain statement number word {w} here." for w in ("one", "two", "three")) + " " + " ".join(
        f"Cited statement about topic {i} here [1]." for i in range(45))
    picked = extract_claims(content, limit=40)
    assert len(picked) == 40 and all(c.source_indexes for c in picked)
    assert [c.start for c in picked] == sorted(c.start for c in picked)


# ── verdicts ─────────────────────────────────────────────────────────────────
def test_verdict_and_label_thresholds():
    assert verifier.verdict_for(0.65) == "supported" and verifier.verdict_for(0.6499) == "partial"
    assert verifier.verdict_for(0.35) == "partial" and verifier.verdict_for(0.3499) == "unsupported"
    assert verifier.label_for(0.85, 3) == "grounded" and verifier.label_for(0.8499, 3) == "mostly grounded"
    assert verifier.label_for(0.65, 3) == "mostly grounded" and verifier.label_for(0.4, 3) == "partially grounded"
    assert verifier.label_for(0.39, 3) == "ungrounded" and verifier.label_for(1.0, 0) == "not checkable"


def test_verify_scores_each_claim_with_stub_scorer():
    content = ("The tower stands in Paris today [1]. The tower is near Lyon city [1]. "
               "The tower is located in Rome [2]. Overall this is a nice general remark. "
               "It opened to visitors in 1889. This sentence cites a missing source [9].")
    contexts = {1: "The tower is a landmark in Paris, close to Lyon by train.", 2: "Rome has many towers."}
    scorer = StubScorer({"Paris": 0.9, "Lyon": 0.5, "Rome": 0.1, "1889": 0.2})
    v = verifier.verify(content, contexts, scorer)

    assert set(v) == {"score", "label", "supported", "partial", "unsupported", "uncited", "model", "sentences"}
    assert [s["verdict"] for s in v["sentences"]] == [
        "supported", "partial", "unsupported", "uncited", "unsupported", "unsupported"]
    assert [s["score"] for s in v["sentences"]] == [0.9, 0.5, 0.1, 0.0, 0.2, 0.0]
    assert [s["sourceIndexes"] for s in v["sentences"]] == [[1], [1], [2], [], [], [9]]
    assert (v["supported"], v["partial"], v["unsupported"], v["uncited"]) == (1, 1, 3, 1)
    assert v["score"] == pytest.approx(1.5 / 5) and v["label"] == "ungrounded"
    assert v["model"] == "stub-nli (test)"
    for s in v["sentences"]:
        assert content[s["start"]:s["end"]] == s["text"] and set(s) == {
            "text", "start", "end", "sourceIndexes", "verdict", "score"}
    # cited claims are only checked against the cited source; markdown/citations never reach the model
    premises = {hyp: premise for premise, hyp in scorer.pairs}
    assert premises["The tower is located in Rome."] == contexts[2]
    assert all("[" not in hyp for _, hyp in scorer.pairs)
    assert verifier.summary(v) == "1 of 5 claims supported, 1 partly"


def test_uncited_specific_fact_supported_by_any_source_counts_as_supported():
    v = verifier.verify("The bridge opened to traffic in 1932.", {1: "Opened in 1932, the bridge..."},
                        StubScorer({"1932": 0.8}))
    assert v["sentences"][0]["verdict"] == "supported" and v["sentences"][0]["sourceIndexes"] == []
    assert v["label"] == "grounded" and v["score"] == 1.0


def test_no_sources_is_not_checkable_without_a_scorer():
    v = verifier.verify("Some general remark about models. It was released in 2020.", {}, None)
    assert v["label"] == "not checkable" and v["score"] == 0.0 and v["uncited"] == 2
    assert v["model"] == nli.MODEL_NAME
    assert verifier.summary(v) == "No checkable claims"
    with pytest.raises(verifier.ScorerRequired):
        verifier.verify("A cited claim about models here [1].", {1: "text"}, None)


def test_windows_select_the_evidence_and_respect_the_pair_budget():
    filler = " ".join(f"filler{i}" for i in range(500))
    context = filler + " The Hubble telescope launched aboard Discovery in April 1990."
    wins = verifier.windows(context)
    assert all(len(w.split()) <= verifier.WINDOW_WORDS for w in wins)
    assert wins[-1].endswith("April 1990.") and wins[0].split()[verifier.WINDOW_STRIDE] == wins[1].split()[0]

    scorer = StubScorer({"Hubble": 0.95})
    v = verifier.verify("The Hubble telescope launched aboard Discovery in 1990 [1].", {1: context}, scorer)
    assert v["sentences"][0]["verdict"] == "supported"
    assert "launched aboard Discovery" in scorer.pairs[0][0]  # the best-overlapping window goes first

    many = " ".join(f"Claim {i} says the Hubble telescope launched in 1990 [1, 2, 3]." for i in range(60))
    scorer = StubScorer()
    v = verifier.verify(many, {1: context, 2: context + " more", 3: "x " + context}, scorer)
    assert len(v["sentences"]) == claims_mod.MAX_CLAIMS
    assert 0 < len(scorer.pairs) <= verifier.MAX_PAIRS


def test_workspace_code_sources_are_not_evidence():
    content = ("The `load_settings` function creates the data directory [1]. "
               "The Transformer was introduced in 2017 by Google researchers [2]. "
               "Both points are explained in the docs [1, 2]. It has 330 config options in total.")
    contexts = {1: "def load_settings():\n    s.data_dir.mkdir(parents=True)", 2: "Transformers (2017, Google)."}
    scorer = StubScorer({"Transformer": 0.9, "Both": 0.8, "330": 0.1})
    v = verifier.verify(content, contexts, scorer, skip_sources={1})
    assert [s["text"] for s in v["sentences"]] == [
        "The Transformer was introduced in 2017 by Google researchers [2].",
        "Both points are explained in the docs [1, 2].", "It has 330 config options in total."]
    assert [s["verdict"] for s in v["sentences"]] == ["supported", "supported", "unsupported"]
    assert all(premise == contexts[2] for premise, _ in scorer.pairs)  # code is never a premise

    sources = [{"index": 1, "type": "doc", "docId": "ws-1", "snippet": "def f(): ..."},
               {"index": 2, "type": "doc", "docId": "doc-9", "snippet": "text"},
               {"index": 3, "type": "web", "url": "https://x.dev", "snippet": "web"}]
    assert verifier.code_sources(sources, "ws-1") == {1} and verifier.code_sources(sources, None) == set()


class _FileChunk:
    def __init__(self, doc_id: str, filename: str, text: str) -> None:
        self.doc_id, self.filename, self.text = doc_id, filename, text
        self.page, self.chunk_index, self.score, self.section = 1, hash(filename) % 1000, None, None


def test_plugin_skips_answers_sourced_only_from_workspace_code(user, stub_scorer):
    events: list = []
    turn = Turn(user_id=user["user"]["id"], conversation_id=str(uuid.uuid4()), is_new=False, question="Explain",
                history=[], doc_ids=[], web_search=False, mode="chat", effort="fast",
                model=registry.resolve_model("mock:sphura-mock"), workspace_id="ws-1")
    run = AgentRun(turn, lambda e, d: events.append((e, d)))
    run.registry.add_doc(_FileChunk("ws-1", "app/config.py", "def load_settings():\n    return Settings()"))
    run.content = "The first result supports that `load_settings` returns the settings object [1]."
    asyncio.run(verify_plugin.after_answer(run))
    assert events == [] and run.meta_extra == {} and not stub_scorer.calls

    run.registry.add_web("https://example.com", "Example", "The first result supports this answer.", "example.com")
    run.content += " According to the docs, the first result supports this answer [2]."
    asyncio.run(verify_plugin.after_answer(run))
    verification = run.meta_extra["verification"]
    assert [s["sourceIndexes"] for s in verification["sentences"]] == [[2]]
    assert verification["supported"] == 1 and ("verification", {"verification": verification}) in events


def test_nli_label_mapping_reads_config():
    assert nli._label_indexes({"id2label": {"0": "contradiction", "1": "entailment", "2": "neutral"}}) == {
        "contradiction": 0, "entailment": 1, "neutral": 2}
    assert nli._label_indexes({"id2label": {"0": "ENTAILMENT", "1": "NEUTRAL", "2": "CONTRADICTION"}}) == {
        "entailment": 0, "neutral": 1, "contradiction": 2}
    with pytest.raises(ValueError):
        nli._label_indexes({"id2label": {"0": "LABEL_0"}})


def test_model_never_downloads_under_pytest(no_model):
    assert not nli.on_disk() and not nli.downloads_allowed() and not nli.can_load()
    assert nli.get(0.1) is None
    assert asyncio.run(nli.aget(0.1)) is None


# ── chat plugin ──────────────────────────────────────────────────────────────
def test_plugin_emits_verification_before_done(client, user, fake_web, stub_scorer):
    events = send(client, user, content="What is a transformer?", webSearch=True)
    seq = [e for e, _ in events]
    assert "verification" in seq
    last_delta = max(i for i, e in enumerate(seq) if e == "delta")
    assert last_delta < seq.index("verification") < seq.index("done")
    assert seq.count("verification") == 1

    verification = first(events, "verification")["verification"]
    by_text = {s["text"]: s for s in verification["sentences"]}
    cited = by_text["According to the provided sources, the first result supports this answer [1]."]
    assert cited["verdict"] == "supported" and cited["sourceIndexes"] == [1] and cited["score"] == 0.9
    assert verification["model"] == "stub-nli (test)" and verification["supported"] == 1

    steps = [d for e, d in events if e == "step" and d["name"] == "verify"]
    assert steps[0]["status"] == "running" and steps[-1]["status"] == "done"
    assert steps[-1]["detail"] == verifier.summary(verification)
    analyzing = [i for i, (e, d) in enumerate(events)
                 if e == "status" and d == {"phase": "analyzing", "label": "Checking claims against sources"}]
    assert analyzing and analyzing[0] > last_delta

    done = first(events, "done")["message"]
    assert done["meta"]["verification"] == verification
    content = done["content"]
    for s in verification["sentences"]:
        assert content[s["start"]:s["end"]] == s["text"]

    cid = first(events, "start")["conversationId"]
    saved = client.get(f"/api/conversations/{cid}", headers=user["headers"]).json()["messages"][-1]
    assert saved["meta"]["verification"] == verification


def test_plugin_is_silent_without_model_or_sources(client, user, fake_web, no_model):
    events = send(client, user, content="What is a transformer?", webSearch=True)
    assert "verification" not in [e for e, _ in events]
    assert not [d for e, d in events if e == "step" and d["name"] == "verify"]
    assert "verification" not in (first(events, "done")["message"]["meta"] or {})


def test_plugin_skips_answers_without_sources(user, stub_scorer):
    events: list = []
    turn = Turn(user_id=user["user"]["id"], conversation_id=str(uuid.uuid4()), is_new=False, question="Hi there",
                history=[], doc_ids=[], web_search=False, mode="chat", effort="fast",
                model=registry.resolve_model("mock:sphura-mock"))
    run = AgentRun(turn, lambda e, d: events.append((e, d)))
    run.content = "A cited claim with no sources at all [1]."
    asyncio.run(verify_plugin.after_answer(run))
    assert events == [] and run.meta_extra == {} and not stub_scorer.calls


# ── POST /api/verify/{messageId} ─────────────────────────────────────────────
def test_verify_endpoint_recomputes_persists_and_checks_ownership(client, user, other_user, fake_web, stub_scorer):
    events = send(client, user, content="What is a transformer?", webSearch=True)
    start, done = first(events, "start"), first(events, "done")["message"]
    answer_id, user_msg_id = done["id"], start["userMessage"]["id"]

    assert client.post(f"/api/verify/{answer_id}", headers=other_user["headers"]).status_code == 404
    r = client.post(f"/api/verify/{uuid.uuid4()}", headers=user["headers"])
    assert r.status_code == 404 and r.json() == {"detail": "Message not found"}
    r = client.post(f"/api/verify/{user_msg_id}", headers=user["headers"])
    assert r.status_code == 400 and isinstance(r.json()["detail"], str)
    assert client.post(f"/api/verify/{answer_id}").status_code == 401

    stub_scorer.calls.clear()
    r = client.post(f"/api/verify/{answer_id}", headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["supported"] == 1 and body["label"] in {"mostly grounded", "partially grounded", "grounded"}
    # re-verification uses the stored snippets (≤ 400 chars), not the full pages
    assert {p for p, _ in stub_scorer.pairs} <= {s["snippet"] for s in done["sources"]}

    saved = client.get(f"/api/conversations/{start['conversationId']}", headers=user["headers"]).json()
    meta = saved["messages"][-1]["meta"]
    assert meta["verification"] == body and meta["model"] == done["meta"]["model"]


def _saved_answer(user_id: str, content: str) -> str:
    with session_scope() as db:
        conv = Conversation(user_id=user_id, title="t")
        db.add(conv)
        db.flush()
        msg = Message(conversation_id=conv.id, role="assistant", content=content, sources=[], steps=[],
                      attachments=[], meta={"model": "mock:sphura-mock"})
        db.add(msg)
        db.flush()
        return msg.id


def test_verify_endpoint_without_sources_or_model(client, user, fake_web, no_model):
    plain = _saved_answer(user["user"]["id"], "An answer without sources. It was released in 2020.")
    r = client.post(f"/api/verify/{plain}", headers=user["headers"])
    assert r.status_code == 200 and r.json()["label"] == "not checkable" and r.json()["uncited"] == 2

    sourced = first(send(client, user, content="What is a transformer?", webSearch=True), "done")["message"]
    r = client.post(f"/api/verify/{sourced['id']}", headers=user["headers"])
    assert r.status_code == 503 and isinstance(r.json()["detail"], str)


def test_figures_found_in_the_cited_source_count_as_support():
    from app.features.verify.verifier import NUMERIC_PARTIAL, NUMERIC_SUPPORT, numeric_support

    src = 'emi({"principal": 2500000, "annual_rate_pct": 8.5, "months": 240}) → emi: 21695.58; total: 5206939.4'
    assert numeric_support("Your EMI is ₹21,696 a month on a ₹25 lakh loan at 8.5%.", [src]) == NUMERIC_SUPPORT
    assert numeric_support("Your EMI is ₹21,696, or ₹99,999 with fees.", [src]) == NUMERIC_PARTIAL
    assert numeric_support("Your EMI is ₹31,000 a month.", [src]) == 0.0
    assert numeric_support("Step 1 is to compare the rates.", [src]) is None  # nothing numeric to check
