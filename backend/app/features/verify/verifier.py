"""Score an answer's claims against its sources with an NLI model and build the CONTRACT `Verification`.

The rules, kept simple enough to explain in one breath:

* A sentence with citations ``[n]`` is checked against the cited sources only. Each source text is cut into
  overlapping windows; the windows sharing the most content words with the claim are scored by the NLI
  cross-encoder (premise = window, hypothesis = the sentence without markdown/citations). The claim's score is
  the highest entailment probability over windows and cited sources:
  ``supported`` ≥ 0.65 · ``partial`` ≥ 0.35 · ``unsupported`` otherwise. Citing a source that does not exist
  is ``unsupported`` (a fabricated citation).
* A sentence without citations is ``uncited`` and does not affect the score — unless the answer has sources
  and the sentence states a specific fact (a figure, year, date, percentage or amount — not a lone "Step 1").
  Such a claim is checked against the best-matching sources of the whole answer and gets a normal verdict, so
  an unsupported, uncited number counts against the answer.
* Workspace code files are not evidence: an NLI model trained on prose rejects correct claims about code, so
  sentences citing only code files are left out (and an answer sourced only from code isn't verified at all).
* Figures are checked as figures: an NLI model reads "₹21,695.58" in a computed table poorly, so a sentence
  whose significant numbers all appear in its cited sources (rounding, lakh / crore and thousands separators
  allowed) scores NUMERIC_SUPPORT, and one with at least half of them NUMERIC_PARTIAL; the claim keeps the
  higher of that and its NLI score.
* ``score = (supported + 0.5·partial) / checkable`` with ``checkable = supported + partial + unsupported``.
  Label: grounded ≥ 0.85 · mostly grounded ≥ 0.65 · partially grounded ≥ 0.4 · ungrounded, and
  "not checkable" when nothing is checkable.

Windows are ~100 words with 50% overlap rather than ~350-word blocks: DeBERTa's cost grows quadratically with
length (measured on a laptop CPU: ~35 ms per 120-word pair vs ~190 ms per 350-word pair). Scoring the
best-overlapping window of each claim first (round 0), then extra windows/sources only while a time budget lasts,
keeps a 40-sentence answer around 1-2 s while giving the model a focused premise.
"""
from __future__ import annotations

import re
import time
from collections.abc import Collection, Mapping, Sequence
from typing import Any, Literal, Protocol

from app.features.verify.claims import MAX_CLAIMS, Claim, extract_claims
from app.features.verify.nli import MODEL_NAME
from app.schemas import CamelModel

SUPPORTED_AT = 0.65
PARTIAL_AT = 0.35
GROUNDED_AT, MOSTLY_AT, PARTIALLY_AT = 0.85, 0.65, 0.4

WINDOW_WORDS = 100
WINDOW_STRIDE = 50
SOURCES_PER_CLAIM = 3      # cited sources checked per sentence
WINDOWS_PER_SOURCE = 2     # best-overlapping windows scored per cited source
UNCITED_SOURCES = 2        # sources tried for an uncited specific fact
MAX_PAIRS = 64             # NLI pairs per answer at most
TIME_BUDGET_S = 1.5        # extra windows/sources (rounds 1-2) are only scored while within this budget
SCORE_CHUNK = 16
NUMERIC_SUPPORT = 0.9      # every significant figure of the claim is in its sources
NUMERIC_PARTIAL = 0.5      # at least half of them are

Verdict = Literal["supported", "partial", "unsupported", "uncited"]
Label = Literal["grounded", "mostly grounded", "partially grounded", "ungrounded", "not checkable"]


class ScorerRequired(ValueError):
    """Some claims need the NLI model but no scorer was given."""


class Scorer(Protocol):
    name: str

    def entailment(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        """P(entailment) for each (premise, hypothesis) pair."""
        ...


class VerifiedSentenceOut(CamelModel):
    text: str
    start: int
    end: int
    source_indexes: list[int]
    verdict: Verdict
    score: float


class VerificationOut(CamelModel):
    score: float
    label: Label
    supported: int
    partial: int
    unsupported: int
    uncited: int
    model: str
    sentences: list[VerifiedSentenceOut]


_STOP = frozenset(
    "the and but for with from into onto this that these those its are was were been being than then there their"
    " they them which who whom whose what when where how also can could may might will would should has have had"
    " not does did such more most other some any each all both over under about after before between while only"
    " very just like through during per via".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")
_NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|l\b|crores?|cr\b|k\b|%)?", re.I)
_SCALE = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "l": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7, "k": 1e3}


def verdict_for(probability: float) -> Verdict:
    if probability >= SUPPORTED_AT:
        return "supported"
    if probability >= PARTIAL_AT:
        return "partial"
    return "unsupported"


def label_for(score: float, checkable: int) -> Label:
    if checkable == 0:
        return "not checkable"
    if score >= GROUNDED_AT:
        return "grounded"
    if score >= MOSTLY_AT:
        return "mostly grounded"
    if score >= PARTIALLY_AT:
        return "partially grounded"
    return "ungrounded"


def windows(text: str, size: int = WINDOW_WORDS, stride: int = WINDOW_STRIDE) -> list[str]:
    """Overlapping word windows covering the whole text (the last one is aligned to the end)."""
    words = text.split()
    if len(words) <= size:
        return [" ".join(words)] if words else []
    out, start = [], 0
    while True:
        start = min(start, len(words) - size)
        out.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            return out
        start += stride


def _terms(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if (len(t) > 2 or t.isdigit()) and t not in _STOP}


def _overlap(claim_terms: set[str], window_terms: set[str]) -> float:
    """Share of the claim's content words found in the window (numbers count double)."""
    if not claim_terms:
        return 0.0
    weight = sum(2 if t.isdigit() else 1 for t in claim_terms)
    return sum(2 if t.isdigit() else 1 for t in claim_terms & window_terms) / weight


def _numbers(text: str) -> list[float]:
    """Numbers in a text with lakh / crore / k applied ("₹25 lakh" → 2,500,000; "8.5%" → 8.5)."""
    out = []
    for raw, unit in _NUMBER.findall(text):
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        out.append(value * _SCALE.get((unit or "").lower(), 1.0))
    return out


def _significant(value: float) -> bool:
    """A figure worth checking: not a list number or a lone small count."""
    return value >= 10 or value != int(value)


def _matches(claim: float, source: list[float]) -> bool:
    return any(abs(s - claim) <= max(0.51, abs(claim) * 0.005) for s in source)


def numeric_support(hypothesis: str, texts: Sequence[str]) -> float | None:
    """NUMERIC_SUPPORT / NUMERIC_PARTIAL / 0.0 by how many of the claim's figures occur in the texts, or None
    when the claim has no significant figure (then only the NLI score counts)."""
    figures = [v for v in _numbers(hypothesis) if _significant(v)]
    if not figures or not texts:
        return None
    pool = [v for t in texts for v in _numbers(t)]
    found = sum(_matches(v, pool) for v in figures)
    if found == len(figures):
        return NUMERIC_SUPPORT
    return NUMERIC_PARTIAL if found * 2 >= len(figures) else 0.0


class _Evidence:
    """Windows of every source, tokenised once per answer."""

    def __init__(self, contexts: Mapping[int, str]) -> None:
        self.windows: dict[int, list[tuple[str, set[str]]]] = {}
        for index, text in contexts.items():
            wins = windows(text or "")
            if wins:
                self.windows[index] = [(w, _terms(w)) for w in wins]

    def ranked(self, claim_terms: set[str], index: int) -> list[tuple[float, str]]:
        scored = [(_overlap(claim_terms, terms), -i, w) for i, (w, terms) in enumerate(self.windows.get(index, []))]
        scored.sort(reverse=True)
        return [(s, w) for s, _, w in scored]


def _plan(claims: list[Claim], evidence: _Evidence, known: set[int]) -> list[list[tuple[int, int, str]]]:
    """Candidate (claim, source, premise) pairs grouped into priority rounds (round 0 = one per claim)."""
    rounds: list[list[tuple[int, int, str]]] = [[], [], []]
    for ci, claim in enumerate(claims):
        terms = _terms(claim.hypothesis)
        if claim.source_indexes:
            cited = [i for i in claim.source_indexes if i in evidence.windows][:SOURCES_PER_CLAIM]
            per_source = sorted(((evidence.ranked(terms, i), i) for i in cited),
                                key=lambda item: item[0][0][0], reverse=True)
            for rank, (ranked, index) in enumerate(per_source):
                rounds[0 if rank == 0 else 1].append((ci, index, ranked[0][1]))
                for _, premise in ranked[1:WINDOWS_PER_SOURCE]:
                    rounds[2].append((ci, index, premise))
        elif claim.specific and known:
            best = sorted(((evidence.ranked(terms, i)[0], i) for i in evidence.windows),
                          key=lambda item: item[0][0], reverse=True)[:UNCITED_SOURCES]
            for rank, ((_, premise), index) in enumerate(best):
                rounds[0 if rank == 0 else 1].append((ci, index, premise))
    return rounds


def _score(scorer: Scorer, pairs: list[tuple[str, str]], rounds: list[list[int]]) -> dict[int, float]:
    """Entailment per pair id. Round 0 (one pair per claim) always runs; later rounds only within the time budget."""
    deadline = time.perf_counter() + TIME_BUDGET_S
    out: dict[int, float] = {}
    for r, ids in enumerate(rounds):
        for start in range(0, len(ids), SCORE_CHUNK):
            if r > 0 and time.perf_counter() > deadline:
                return out
            chunk = ids[start:start + SCORE_CHUNK]
            out.update(zip(chunk, (float(p) for p in scorer.entailment([pairs[i] for i in chunk]))))
    return out


def verify(content: str, contexts: Mapping[int, str], scorer: Scorer | None,
           max_claims: int = MAX_CLAIMS, skip_sources: Collection[int] = ()) -> dict[str, Any]:
    """Build the Verification for `content` given {source index: source text}. CPU-bound: run in a thread.

    `skip_sources` are sources an NLI model can't judge (workspace code files): sentences citing only them are
    left out, and they are never used as evidence for other sentences."""
    skip = set(skip_sources)
    contexts = {i: text for i, text in contexts.items() if i not in skip}
    claims = extract_claims(content, max_claims, skip)
    evidence = _Evidence(contexts)
    known = set(contexts)
    rounds = _plan(claims, evidence, known)

    pairs: list[tuple[str, str]] = []
    pair_ids: dict[tuple[str, str], int] = {}
    new_in_round: list[list[int]] = []
    claim_pairs: dict[int, list[int]] = {}
    for round_ in rounds:
        fresh: list[int] = []
        for ci, _index, premise in round_:
            key = (premise, claims[ci].hypothesis)
            if key not in pair_ids:
                if len(pairs) >= MAX_PAIRS:
                    continue
                pair_ids[key] = len(pairs)
                pairs.append(key)
                fresh.append(pair_ids[key])
            claim_pairs.setdefault(ci, []).append(pair_ids[key])
        new_in_round.append(fresh)

    if pairs and scorer is None:
        raise ScorerRequired("an NLI scorer is required to check these claims")
    probabilities = _score(scorer, pairs, new_in_round) if pairs and scorer is not None else {}

    sentences: list[VerifiedSentenceOut] = []
    counts = {"supported": 0, "partial": 0, "unsupported": 0, "uncited": 0}
    for ci, claim in enumerate(claims):
        scored = [probabilities[i] for i in claim_pairs.get(ci, []) if i in probabilities]
        if claim.source_indexes:
            texts = [contexts[i] for i in claim.source_indexes if i in contexts]
        else:
            texts = list(contexts.values()) if claim.specific else []
        numeric = numeric_support(claim.hypothesis, texts)
        if numeric is not None:
            scored.append(numeric)
        if scored:
            probability = max(scored)
            verdict: Verdict = verdict_for(probability)
        elif claim.source_indexes:
            probability, verdict = 0.0, "unsupported"  # cites a source that doesn't exist (or has no text)
        else:
            probability, verdict = 0.0, "uncited"
        counts[verdict] += 1
        sentences.append(VerifiedSentenceOut(
            text=claim.text, start=claim.start, end=claim.end, source_indexes=claim.source_indexes,
            verdict=verdict, score=round(min(1.0, max(0.0, probability)), 3),
        ))

    checkable = counts["supported"] + counts["partial"] + counts["unsupported"]
    score = (counts["supported"] + 0.5 * counts["partial"]) / checkable if checkable else 0.0
    return VerificationOut(
        score=round(score, 3), label=label_for(score, checkable), model=scorer.name if scorer else MODEL_NAME,
        sentences=sentences, **counts,
    ).dump()


def summary(verification: Mapping[str, Any]) -> str:
    """Step detail, e.g. "9 of 11 claims supported"."""
    checkable = sum(int(verification.get(k, 0)) for k in ("supported", "partial", "unsupported"))
    if not checkable:
        return "No checkable claims"
    text = f"{verification.get('supported', 0)} of {checkable} claim{'' if checkable == 1 else 's'} supported"
    partial = int(verification.get("partial", 0))
    return text + (f", {partial} partly" if partial else "")


def contexts_from_sources(sources: Sequence[Mapping[str, Any]]) -> dict[int, str]:
    """{index: snippet} from stored Source dicts (used when re-verifying a saved message)."""
    out: dict[int, str] = {}
    for source in sources or []:
        if not isinstance(source, Mapping):
            continue
        index = source.get("index")
        if isinstance(index, int) and not isinstance(index, bool):
            out[index] = str(source.get("snippet") or "")
    return out


def code_sources(sources: Sequence[Mapping[str, Any]], workspace_id: str | None) -> set[int]:
    """Indexes of workspace file sources (type "doc" whose docId is the workspace): code, not checkable prose."""
    if not workspace_id:
        return set()
    return {s["index"] for s in sources or [] if isinstance(s, Mapping) and isinstance(s.get("index"), int)
            and s.get("docId") == workspace_id}
