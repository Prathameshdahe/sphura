"""Plugin-style wrapper around the finance router (kept for callers of the pre-LangGraph plugin API).

`route(text)` classifies one message with the trained router and says whether the turn should take the
**market** branch (`auto_search`): the finance graph fetches quotes / finance news for market questions, which
replaces the old "auto web search" behaviour. The LangGraph classify node (app/agent/classify.py) calls the
artifact directly; this module only adds the bounded thread pool and the timeout for callers outside the graph.
Every routed turn can record meta.router = {label, confidence, autoSearch}.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from dataclasses import dataclass

from app.features.router import model

log = logging.getLogger("sphura.router")

AUTO_SEARCH_LABELS = {"market"}
AUTO_SEARCH_THRESHOLD = 0.6
PREDICT_TIMEOUT_S = 15.0  # first call may load the embedding model
MAX_PENDING = 2           # predictions in flight; more means the model is cold (loading/downloading)

# Own small pool: a prediction stuck behind a cold embedding model must not pile up threads in the default
# executor every turn — that pool also serves the DB/RAG work of every other request.
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PENDING, thread_name_prefix="sphura-router")
_pending: set[concurrent.futures.Future] = set()


@dataclass
class Route:
    label: str
    confidence: float
    auto_search: bool
    probabilities: dict[str, float]

    def meta(self) -> dict:
        return {"label": self.label, "confidence": self.confidence, "autoSearch": self.auto_search}


def _submit(text: str) -> concurrent.futures.Future | None:
    """Start a prediction, or None when MAX_PENDING are still running (the turn then skips routing at once)."""
    if len(_pending) >= MAX_PENDING:
        return None
    future = _pool.submit(model.predict, text)
    _pending.add(future)
    future.add_done_callback(_pending.discard)
    return future


async def route(text: str) -> Route | None:
    """Classify one message off the event loop; None when the router is unavailable, busy or times out."""
    if not model.available():
        return None
    future = _submit(text)
    if future is None:
        log.info("router skipped: earlier predictions are still waiting for the embedding model")
        return None
    try:
        # shield: a timed-out wait leaves the prediction running (it can't be interrupted) and counted in _pending
        pred = await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), PREDICT_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — routing is an optimisation, never a failure
        log.info("router skipped: %s", exc)
        return None
    if pred is None:
        return None
    auto = pred.label in AUTO_SEARCH_LABELS and pred.confidence >= AUTO_SEARCH_THRESHOLD
    log.info("router: %s %.2f (%.0f ms) market=%s", pred.label, pred.confidence, pred.latency_ms, auto)
    return Route(pred.label, pred.confidence, auto, pred.probabilities)
