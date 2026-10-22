"""Model Lab: the trained finance classifiers, the sphura-fin-1.7b fine-tune report, the RAG benchmark and
answer-verification statistics (docs/FINANCE_PLAN.md section 8).

  GET  /api/ml/report        → ModelLabReport {models: ModelCard[], finetune: FinetuneReport|null, ragEval, generatedAt}
  POST /api/ml/train/{key}   → ModelCard (admin; retrains one classifier in a worker thread)
  GET  /api/ml/verification  → VerificationStats over the current user's answers
Cards are read from backend/ml/artifacts/<model>/report.json (the deployed model) or report_sklearn.json (the
in-app fallback) — never invented: a missing artifact simply leaves the model out of the list.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.config import BACKEND_DIR, settings
from app.db.base import get_db
from app.db.models import Conversation, Message, User
from app.features.router import model as router_model

log = logging.getLogger("sphura.ml")
router = APIRouter(prefix="/ml", tags=["ml"])

ARTIFACT_DIR = BACKEND_DIR / "ml" / "artifacts"
MODEL_KEYS = ("categoriser", "sentiment", "router")
ARTIFACT_SUBDIR = {"categoriser": "categoriser", "sentiment": "sentiment", "router": "fin_router"}
TRAINERS = {"categoriser": "train_categoriser", "sentiment": "train_sentiment", "router": "train_router"}
CARD_FIELDS = ("key", "name", "task", "model", "trainedAt", "dataset", "metrics", "baseline", "labels", "perClass",
               "confusion", "extras", "ablation")
BUCKETS = ["0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
_jobs = {key: threading.Lock() for key in MODEL_KEYS}

if not settings.sphura_enable_mock:  # tests load models on demand; a real server warms the router at startup
    threading.Thread(target=router_model.warmup, name="sphura-router-warmup", daemon=True).start()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def model_card(key: str, artifact_dir: Path | None = None) -> dict[str, Any] | None:
    """The ModelCard of one classifier (deployed report.json, else the sklearn fallback's), or None."""
    base = (artifact_dir or ARTIFACT_DIR) / ARTIFACT_SUBDIR[key]
    for name in ("report.json", "report_sklearn.json"):
        data = _read_json(base / name)
        if data and isinstance(data.get("metrics"), dict) and data.get("labels"):
            card = {field: data.get(field) for field in CARD_FIELDS if field in data}
            card["key"] = key
            return card
    return None


def finetune_report(artifact_dir: Path | None = None) -> dict[str, Any] | None:
    data = _read_json((artifact_dir or ARTIFACT_DIR) / "finetune" / "report.json")
    return data if data and "available" in data else None


def rag_eval_report(artifact_dir: Path | None = None) -> dict[str, Any]:
    data = _read_json((artifact_dir or ARTIFACT_DIR) / "rag_eval.json")
    return data if data and data.get("available") else {"available": False}


def build_report(artifact_dir: Path | None = None) -> dict[str, Any]:
    cards = [model_card(key, artifact_dir) for key in MODEL_KEYS]
    return {"models": [c for c in cards if c], "finetune": finetune_report(artifact_dir),
            "ragEval": rag_eval_report(artifact_dir), "generatedAt": _now()}


def _ml_module(name: str) -> Any:
    """The offline scripts in backend/ml (not shipped in every deployment)."""
    try:
        return importlib.import_module(f"ml.{name}")
    except ModuleNotFoundError as exc:
        log.warning("ml.%s unavailable: %s", name, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The ML training scripts are not available in this deployment") from None


async def _run_job(key: str, fn: Any) -> dict[str, Any]:
    lock = _jobs[key]
    if not lock.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, "This job is already running — try again in a minute")

    def job() -> dict[str, Any]:
        try:
            return fn()
        finally:
            lock.release()  # in the worker: a dropped request must not free the lock while the job still runs

    try:
        return await asyncio.to_thread(job)
    except Exception as exc:  # noqa: BLE001
        log.exception("%s job failed", key)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"The job failed: {type(exc).__name__}") from None


# ── Model Lab report ─────────────────────────────────────────────────────────
@router.get("/report")
def report(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return build_report()


@router.post("/train/{key}")
async def train(key: str, _admin: User = Depends(require_admin)) -> dict[str, Any]:
    """Retrain one classifier in a worker thread. For the categoriser and sentiment models this refits the
    in-app sklearn rung (the DistilBERT rung needs the GPU training venv); the returned card is the one it wrote."""
    if key not in MODEL_KEYS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown model '{key}'; expected one of {', '.join(MODEL_KEYS)}")
    trainer = _ml_module(TRAINERS[key])
    card = await _run_job(key, lambda: trainer.train(write=True, log=log.info))
    return {field: card.get(field) for field in CARD_FIELDS if field in card} | {"key": key}


# ── verification statistics ──────────────────────────────────────────────────
def verification_stats(metas: list[Any]) -> dict[str, Any]:
    """Aggregate Message.meta["verification"] dicts: counts per label, mean score and a 5-bucket histogram.

    "not checkable" answers are counted in `answers`/`labelCounts` but excluded from the score statistics.
    """
    answers, scores = 0, []
    labels: dict[str, int] = {}
    histogram = [0] * len(BUCKETS)
    for meta in metas:
        v = meta.get("verification") if isinstance(meta, dict) else None
        if not isinstance(v, dict):
            continue
        answers += 1
        label = str(v.get("label") or "unknown")
        labels[label] = labels.get(label, 0) + 1
        score = v.get("score")
        if label == "not checkable" or isinstance(score, bool) or not isinstance(score, (int, float)):
            continue
        score = min(1.0, max(0.0, float(score)))
        scores.append(score)
        histogram[min(int(score * len(BUCKETS)), len(BUCKETS) - 1)] += 1
    return {
        "answers": answers,
        "avgScore": round(sum(scores) / len(scores), 4) if scores else None,
        "labelCounts": labels,
        "histogram": [{"bucket": b, "count": c} for b, c in zip(BUCKETS, histogram)],
    }


@router.get("/verification")
def verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = (select(Message.meta).join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.user_id == user.id, Message.role == "assistant", Message.meta.is_not(None)))
    return verification_stats(list(db.scalars(stmt)))
