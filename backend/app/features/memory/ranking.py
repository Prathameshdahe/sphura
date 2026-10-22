"""Embedding helpers for memory (bge-small via app.rag.embeddings): relevance ranking and near-duplicate checks.

Every function degrades gracefully: without the embedding model, ranking falls back to recency and duplicate
detection to normalised-text matching.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from collections.abc import Sequence

log = logging.getLogger("sphura.memory")

DUPLICATE_AT = 0.9
_CACHE_MAX = 4096
_cache: dict[str, list[float]] = {}
_cache_lock = threading.Lock()
_NON_WORD = re.compile(r"[^\w\s]+")
_LEADING_SUBJECT = re.compile(r"^(?:the user|user)(?:'s|s)?\s+")


def normalise(text: str) -> str:
    """Lower-case words only, without a leading "The user" (so "Prefers X" == "The user prefers X.")."""
    text = " ".join(_NON_WORD.sub(" ", text.lower()).split())
    text = _LEADING_SUBJECT.sub("", text)
    return re.sub(r"^(?:i am|i m|im)\s+", "is ", text)


def embed_passages(texts: Sequence[str]) -> list[list[float]] | None:
    """Vectors for `texts` (cached per text), or None when the embedding model is unavailable."""
    try:
        from app.rag.embeddings import embed_passages as _embed

        missing = list(dict.fromkeys(t for t in texts if t not in _cache))
        if missing:
            vectors = _embed(missing)
            with _cache_lock:
                if len(_cache) + len(missing) > _CACHE_MAX:
                    _cache.clear()
                _cache.update(zip(missing, vectors))
        return [_cache[t] if t in _cache else _embed([t])[0] for t in texts]
    except Exception as exc:  # noqa: BLE001
        log.info("memory embeddings unavailable: %s", exc)
        return None


def embed_query(text: str) -> list[float] | None:
    try:
        from app.rag.embeddings import embed_query as _embed_query

        return _embed_query(text)
    except Exception as exc:  # noqa: BLE001
        log.info("memory query embedding unavailable: %s", exc)
        return None


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def rank(question: str, items: list[tuple[str, str]], limit: int) -> list[tuple[str, str]]:
    """The `limit` (id, content) items most similar to the question; `items` newest first → recency fallback."""
    if len(items) <= limit:
        return list(items)
    query = embed_query(question)
    vectors = embed_passages([content for _, content in items]) if query is not None else None
    if query is None or vectors is None:
        return list(items[:limit])
    order = sorted(range(len(items)), key=lambda i: (-cosine(query, vectors[i]), i))
    return [items[i] for i in order[:limit]]


def novel(facts: Sequence[str], existing: Sequence[str]) -> list[str]:
    """Facts that aren't a normalised-text match or a cosine ≥ 0.9 near-duplicate of existing (or earlier) ones."""
    seen = {normalise(e) for e in existing}
    candidates: list[str] = []
    for fact in facts:
        key = normalise(fact)
        if key and key not in seen:
            seen.add(key)
            candidates.append(fact)
    if not candidates:
        return []
    vectors = embed_passages([*existing, *candidates])
    if vectors is None:
        return candidates
    kept: list[str] = []
    kept_vectors = list(vectors[: len(existing)])
    for fact, vector in zip(candidates, vectors[len(existing):]):
        if any(cosine(vector, other) >= DUPLICATE_AT for other in kept_vectors):
            continue
        kept.append(fact)
        kept_vectors.append(vector)
    return kept
