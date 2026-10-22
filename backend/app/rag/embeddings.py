"""fastembed models (dense embedder + cross-encoder reranker) as lazy, thread-safe singletons."""
from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time
from pathlib import Path

from app.core.config import BACKEND_DIR, settings

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

log = logging.getLogger("sphura.rag.embeddings")

# Shared across dev runs and tests (not under DATA_DIR, which tests point at a temp folder).
MODEL_CACHE = Path(os.environ.get("FASTEMBED_CACHE_PATH") or BACKEND_DIR / "data" / "models")
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
EMBED_BATCH = 32

_lock = threading.Lock()
_embedder = None
_reranker = None
_reranker_failed = False
_dim: int | None = None


class EmbeddingUnavailable(RuntimeError):
    """The embedding model could not be loaded; the message is shown to the user."""


def _load_embedder():
    global _embedder
    with _lock:
        if _embedder is None:
            from fastembed import TextEmbedding

            started = time.perf_counter()
            MODEL_CACHE.mkdir(parents=True, exist_ok=True)
            try:
                _embedder = TextEmbedding(settings.embedding_model, cache_dir=str(MODEL_CACHE))
            except Exception as exc:  # noqa: BLE001 — usually a first run without internet
                log.warning("embedding model %s failed to load: %s", settings.embedding_model, exc)
                raise EmbeddingUnavailable("The embedding model could not be loaded — the first run needs "
                                           "internet access to download it") from exc
            log.info("embedding model %s loaded in %.0f ms", settings.embedding_model,
                     (time.perf_counter() - started) * 1000)
        return _embedder


def dimension() -> int:
    """Vector size, from fastembed's model table when possible (no model load), else by probing."""
    global _dim
    if _dim is None:
        from fastembed import TextEmbedding

        known = {m["model"].lower(): m.get("dim") for m in TextEmbedding.list_supported_models()}
        _dim = known.get(settings.embedding_model.lower()) or len(embed_passages(["dimension probe"])[0])
    return int(_dim)


def _query_text(query: str) -> str:
    name = settings.embedding_model.lower()
    return BGE_QUERY_PREFIX + query if "bge" in name and "-en" in name else query


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed document chunks (CPU-bound; call from a worker thread)."""
    if not texts:
        return []
    model = _load_embedder()
    return [vec.tolist() for vec in model.passage_embed(texts, batch_size=EMBED_BATCH)]


def embed_query(query: str) -> list[float]:
    model = _load_embedder()
    return next(iter(model.query_embed(_query_text(query)))).tolist()


async def aembed_query(query: str) -> list[float]:
    return await asyncio.to_thread(embed_query, query)


def _load_reranker():
    global _reranker, _reranker_failed
    if not settings.reranker_enabled or _reranker_failed:
        return None
    with _lock:
        if _reranker is None and not _reranker_failed:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                started = time.perf_counter()
                MODEL_CACHE.mkdir(parents=True, exist_ok=True)
                _reranker = TextCrossEncoder(settings.reranker_model, cache_dir=str(MODEL_CACHE))
                log.info("reranker %s loaded in %.0f ms", settings.reranker_model,
                         (time.perf_counter() - started) * 1000)
            except Exception as exc:  # noqa: BLE001 — reranking is an optional quality boost
                _reranker_failed = True
                log.warning("reranker unavailable (%s); using fusion scores only", exc)
        return _reranker


def rerank(query: str, documents: list[str]) -> list[float] | None:
    """Cross-encoder relevance in [0, 1] (sigmoid of the logit), or None when unavailable."""
    model = _load_reranker()
    if model is None or not documents:
        return None
    try:
        logits = list(model.rerank(query, documents, batch_size=32))
    except Exception as exc:  # noqa: BLE001
        log.warning("rerank failed: %s", exc)
        return None
    return [1.0 / (1.0 + math.exp(-float(x))) for x in logits]


def warmup() -> None:
    """Load both models (used at startup in a background thread so the first query is fast)."""
    _load_embedder()
    _load_reranker()
