"""The trained finance intent router at inference time: lazy, thread-safe, reloads when the artifact changes.

Labels: spending / documents / market / explain / advice / out_of_scope (the LangGraph branches). Features are
the production embedding model's passage vectors (bge-small, 384-d, L2-normalised); the classifier is a
scikit-learn LogisticRegression trained by `ml/train_router.py`, which imports `embed_texts` from here so train
and serve featurise text identically. The graph's classify node (app/agent/classify.py) reads the same
artifact; this module is the plugin-style API (`predict(text) -> Prediction`) kept for the Model Lab and tests.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import BACKEND_DIR, settings

log = logging.getLogger("sphura.router")

ARTIFACT_DIR = BACKEND_DIR / "ml" / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "fin_router.joblib"
REPORT_PATH = ARTIFACT_DIR / "fin_router" / "report.json"
CONFUSION_PATH = ARTIFACT_DIR / "fin_router" / "confusion.png"
LABELS = ("spending", "documents", "market", "explain", "advice", "out_of_scope")

_lock = threading.Lock()
_bundle: dict[str, Any] | None = None
_bundle_mtime: float | None = None


@dataclass
class Prediction:
    label: str
    confidence: float
    probabilities: dict[str, float]
    latency_ms: float


def embed_texts(texts: list[str]) -> np.ndarray:
    """(n, d) float32 matrix of L2-normalised passage embeddings (CPU-bound: call from a worker thread)."""
    from app.rag import embeddings

    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    matrix = np.asarray(embeddings.embed_passages([" ".join(t.split()) for t in texts]), dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.maximum(norms, 1e-12)


def available() -> bool:
    return MODEL_PATH.exists()


def load() -> dict[str, Any] | None:
    """The artifact bundle ({model, labels, …}), or None when it has not been trained. Reloads on change."""
    global _bundle, _bundle_mtime
    try:
        mtime = MODEL_PATH.stat().st_mtime
    except OSError:
        return None
    if _bundle is not None and _bundle_mtime == mtime:
        return _bundle
    with _lock:
        if _bundle is None or _bundle_mtime != mtime:
            import joblib

            try:
                bundle = joblib.load(MODEL_PATH)
            except Exception as exc:  # noqa: BLE001 — a corrupt/incompatible artifact must not break chat
                log.warning("router artifact could not be loaded: %s", exc)
                return None
            trained_on = bundle.get("embedding_model") if isinstance(bundle, dict) else None
            if trained_on != settings.embedding_model:  # other features → meaningless (or crashing) predictions
                log.warning("router artifact was trained on %s but EMBEDDING_MODEL is %s; retrain it "
                            "(python -m ml.train_router)", trained_on, settings.embedding_model)
                return None
            _bundle, _bundle_mtime = bundle, mtime
            log.info("finance router loaded (%s, trained %s)", bundle.get("model_name"), bundle.get("trained_at"))
        return _bundle


def reload() -> None:
    """Forget the cached model (after retraining)."""
    global _bundle, _bundle_mtime
    with _lock:
        _bundle, _bundle_mtime = None, None


def predict(text: str) -> Prediction | None:
    """Classify one message; None when no trained model is available (blocking — use a worker thread)."""
    bundle = load()
    text = " ".join((text or "").split())[:2000]
    if bundle is None or not text:
        return None
    started = time.perf_counter()
    vector = embed_texts([text])
    probs = bundle["model"].predict_proba(vector)[0]
    classes = [str(c) for c in bundle["model"].classes_]
    probabilities = {c: round(float(p), 4) for c, p in zip(classes, probs)}
    best = int(np.argmax(probs))
    return Prediction(label=classes[best], confidence=round(float(probs[best]), 4), probabilities=probabilities,
                      latency_ms=round((time.perf_counter() - started) * 1000, 1))


def warmup() -> None:
    """Load the classifier and the embedding model so the first chat turn is fast."""
    try:
        if load() is not None:
            embed_texts(["warm up"])
    except Exception as exc:  # noqa: BLE001
        log.info("router warmup skipped: %s", exc)
