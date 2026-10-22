"""Hybrid retrieval: dense (Qdrant) + BM25 → Reciprocal Rank Fusion → cross-encoder rerank."""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import Chunk, Document
from app.rag import embeddings, store

log = logging.getLogger("sphura.rag.retriever")

DENSE_K = 30
LEXICAL_K = 30
RRF_K = 60
RERANK_POOL = 20
RERANK_WEIGHT = 0.75
TABLE_FOCUS_MIN_ROWS = 8
MAX_LEXICAL_CANDIDATES = 20_000
_CACHE_SIZE = 16

_TOKEN_RE = re.compile(r"[\wऀ-ॿ]+")
STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers
him his how i if in into is it its itself just me more most my no nor not of off on once only or other our ours
out over own same she should so some such than that the their them then there these they this those through to
too under until up very was we were what when where which while who whom why will with would you your yours
""".split())


@dataclass
class RetrievedChunk:
    doc_id: str
    filename: str
    page: int | None
    chunk_index: int
    text: str
    score: float
    section: str | None
    chunk_id: str = ""
    page_end: int | None = None


@dataclass
class _Row:
    id: str
    doc_id: str
    chunk_index: int
    text: str
    section: str | None
    page_start: int | None
    page_end: int | None


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens without English stopwords; light plural folding."""
    out = []
    for tok in _TOKEN_RE.findall(text.lower()):
        for part in tok.split("_"):
            if not part or part in STOPWORDS:
                continue
            if len(part) > 3 and part.endswith("s") and not part.endswith("ss"):
                part = part[:-1]
            out.append(part)
    return out


class _LexicalIndex:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows
        corpus = [tokenize(f"{r.section or ''} {r.text}") for r in rows]
        self.bm25 = BM25Okapi([doc or ["∅"] for doc in corpus]) if rows else None

    def top(self, query: str, k: int) -> dict[str, float]:
        """Chunk id → BM25 score for the k best matches, best first."""
        tokens = tokenize(query)
        if not self.bm25 or not tokens:
            return {}
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return {self.rows[i].id: float(scores[i]) for i in ranked if scores[i] > 0}


_cache: OrderedDict[tuple, _LexicalIndex] = OrderedDict()
_cache_lock = threading.Lock()


def invalidate_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _candidate_docs(user_id: str, doc_ids: list[str] | None) -> dict[str, tuple[str, str]]:
    """Ready documents the user owns → {doc_id: (filename, ingest_id)}. Ownership is enforced here."""
    with session_scope() as db:
        stmt = select(Document.id, Document.filename, Document.meta).where(
            Document.user_id == user_id, Document.status == "ready")
        if doc_ids:
            stmt = stmt.where(Document.id.in_(doc_ids))
        return {d: (name, str((meta or {}).get("ingestId", ""))) for d, name, meta in db.execute(stmt)}


def _load_rows(doc_ids: list[str], limit: int | None = None, chunk_ids: list[str] | None = None) -> list[_Row]:
    with session_scope() as db:
        stmt = select(Chunk.id, Chunk.document_id, Chunk.chunk_index, Chunk.text, Chunk.section,
                      Chunk.page_start, Chunk.page_end).where(Chunk.document_id.in_(doc_ids))
        if chunk_ids is not None:
            stmt = stmt.where(Chunk.id.in_(chunk_ids))
        stmt = stmt.order_by(Chunk.document_id, Chunk.chunk_index)
        if limit:
            stmt = stmt.limit(limit)
        return [_Row(*row) for row in db.execute(stmt)]


def _lexical_index(docs: dict[str, tuple[str, str]]) -> _LexicalIndex:
    key = tuple(sorted((d, ingest) for d, (_, ingest) in docs.items()))
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    rows = _load_rows(list(docs), limit=MAX_LEXICAL_CANDIDATES + 1)
    if len(rows) > MAX_LEXICAL_CANDIDATES:
        log.warning("BM25 candidates capped at %d chunks (%d documents)", MAX_LEXICAL_CANDIDATES, len(docs))
        rows = rows[:MAX_LEXICAL_CANDIDATES]
    index = _LexicalIndex(rows)
    with _cache_lock:
        _cache[key] = index
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return index


def rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion: score(d) = Σ 1 / (k + rank_i(d))."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return fused


def _search_sync(user_id: str, query: str, doc_ids: list[str] | None, k: int) -> list[RetrievedChunk]:
    t0 = time.perf_counter()
    docs = _candidate_docs(user_id, doc_ids)
    if not docs:
        return []
    allowed = list(docs)

    t1 = time.perf_counter()
    dense = {str(p.id): float(p.score) for p in store.search(embeddings.embed_query(query), user_id, allowed,
                                                             limit=DENSE_K)}
    t2 = time.perf_counter()
    index = _lexical_index(docs)
    lexical = index.top(query, LEXICAL_K)
    t3 = time.perf_counter()

    fused = rrf([list(dense), list(lexical)])
    pool = sorted(fused, key=fused.get, reverse=True)[:RERANK_POOL]  # type: ignore[arg-type]
    rows = {r.id: r for r in index.rows if r.id in fused}
    missing = [cid for cid in pool if cid not in rows]
    if missing:  # dense hits beyond a capped BM25 candidate set
        rows.update({r.id: r for r in _load_rows(allowed, chunk_ids=missing)})
    pool = [cid for cid in pool if cid in rows]

    scores = _final_scores(query, pool, rows, fused, _evidence(pool, dense, lexical))
    ranked = sorted(zip(pool, scores), key=lambda x: x[1], reverse=True)[:k]
    t4 = time.perf_counter()
    log.info("search: docs=%d dense=%d bm25=%d pool=%d -> %d | embed+dense %.0fms bm25 %.0fms rerank %.0fms total %.0fms",
             len(docs), len(dense), len(lexical), len(pool), len(ranked), (t2 - t1) * 1000,
             (t3 - t2) * 1000, (t4 - t3) * 1000, (t4 - t0) * 1000)
    return [_to_result(rows[cid], docs[rows[cid].doc_id][0], score) for cid, score in ranked]


def _evidence(pool: list[str], dense: dict[str, float], lexical: dict[str, float]) -> list[float]:
    """Score-aware retrieval evidence in [0, 1]: mean of min-max dense cosine and max-scaled BM25.

    RRF keeps only ranks, so a chunk that wins BM25 by a mile and loses dense by a hair ties with the reverse;
    this term restores the margins.
    """
    lo, hi = (min(dense.values()), max(dense.values())) if dense else (0.0, 0.0)
    top_bm25 = max(lexical.values(), default=0.0)
    out = []
    for cid in pool:
        d = ((dense[cid] - lo) / (hi - lo) if hi - lo > 1e-9 else 1.0) if cid in dense else 0.0
        b = lexical.get(cid, 0.0) / top_bm25 if top_bm25 > 0 else 0.0
        out.append(0.5 * d + 0.5 * b)
    return out


def _final_scores(query: str, pool: list[str], rows: dict[str, _Row], fused: dict[str, float],
                  evidence: list[float]) -> list[float]:
    """0.75 × cross-encoder relevance (or normalised RRF without a reranker) + 0.25 × retrieval evidence.

    The cross-encoder decides on prose; when it is unsure (markdown table rows, where MS-MARCO scores
    everything near 0) the retrieval evidence still separates the exact match from the rest.
    """
    terms = set(tokenize(query))
    relevance = embeddings.rerank(query, [_rerank_text(rows[c], terms) for c in pool])
    if relevance is None:
        relevance = [fused[c] / (2.0 / (RRF_K + 1)) for c in pool]  # 1.0 = rank 1 in both retrievers
    return [RERANK_WEIGHT * r + (1 - RERANK_WEIGHT) * e for r, e in zip(relevance, evidence)]


def focus_tables(text: str, terms: set[str], min_rows: int = TABLE_FOCUS_MIN_ROWS) -> str:
    """Query-focused view of long markdown tables: header + rows sharing a query term (prose untouched).

    A cross-encoder reading 40 rows of a CSV sees mostly noise and scores everything ≈ 0; showing it the
    header and the matching row lets it judge the row that actually answers the question.
    """
    lines = text.split("\n")
    body = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")]
    if len(body) <= min_rows:
        return text
    keep, matched, prev = [], 0, -2
    for i, line in enumerate(lines):
        is_row = line.lstrip().startswith("|")
        is_head = is_row and prev != i - 1  # first row of a table block
        is_sep = is_row and set(line.replace("|", "").strip()) <= set("-: ") and line.strip("| ")
        if not is_row or is_head or is_sep:
            keep.append(line)
        elif terms & set(tokenize(line)):
            keep.append(line)
            matched += 1
        if is_row:
            prev = i
    if not matched:  # nothing specific: show the first rows so the model still sees real data
        return "\n".join(lines[: body[0] + min_rows] + lines[body[-1] + 1:])
    return "\n".join(keep)


def _rerank_text(row: _Row, terms: set[str]) -> str:
    text = focus_tables(row.text, terms)
    return f"{row.section}\n{text}" if row.section else text


def _to_result(row: _Row, filename: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(doc_id=row.doc_id, filename=filename, page=row.page_start, chunk_index=row.chunk_index,
                          text=row.text, score=round(float(score), 4), section=row.section, chunk_id=row.id,
                          page_end=row.page_end)


async def search_documents(user_id: str, query: str, doc_ids: list[str] | None = None,
                           k: int = 8) -> list[RetrievedChunk]:
    """Top-k chunks from the user's ready documents (restricted to `doc_ids` when non-empty)."""
    if not query or not query.strip():
        return []
    return await asyncio.to_thread(_search_sync, user_id, query.strip(), doc_ids, max(1, k))
