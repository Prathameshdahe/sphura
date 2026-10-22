"""Financial sentiment model at inference time (backend/ml/artifacts/sentiment/).

Backends, first available wins (each fails soft):
  1. DistilBERT fine-tune exported to ONNX — `model_quantized.onnx` (int8) or `model.onnx` with `tokenizer.json`
     and `config.json` (id2label); run with onnxruntime + tokenizers, no torch needed.
  2. the TF-IDF + logistic-regression fallback — `sklearn.joblib` ({"pipeline", "labels"}).
Public API: `label(text) -> {"label", "score"}`, `label_many(texts)`, `predict(texts) -> [(label, score)]`
(the shape `app.features.market.sentiment` probes for), `available()`, `backend_name()`, `reset()`.
Labels are always "positive" | "neutral" | "negative"; score is the probability of the chosen label.
"""
from __future__ import annotations

import json
import logging
import math
import threading
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR

log = logging.getLogger("sphura.sentiment")

ARTIFACT_DIR = BACKEND_DIR / "ml" / "artifacts" / "sentiment"
LABELS = ("negative", "neutral", "positive")
MAX_TOKENS = 128
BATCH = 64

_lock = threading.Lock()
_backend: Any = None
_backend_name = "none"
_probed = False


def _canonical(label: str) -> str:
    label = str(label).lower()
    if label.startswith("pos") or label in ("bullish", "label_2"):
        return "positive"
    if label.startswith("neg") or label in ("bearish", "label_0"):
        return "negative"
    return "neutral"


def _onnx_backend() -> tuple[Any, str] | None:
    model = next((p for p in (ARTIFACT_DIR / "model_quantized.onnx", ARTIFACT_DIR / "model.onnx") if p.is_file()),
                 None)
    tokenizer_path, config_path = ARTIFACT_DIR / "tokenizer.json", ARTIFACT_DIR / "config.json"
    if model is None or not tokenizer_path.is_file() or not config_path.is_file():
        return None
    try:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        config = json.loads(config_path.read_text(encoding="utf-8"))
        id2label = {int(k): str(v) for k, v in (config.get("id2label") or {}).items()}
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(MAX_TOKENS)
        tokenizer.enable_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        names = {i.name for i in session.get_inputs()}

        def predict(texts: list[str]) -> list[tuple[str, float]]:
            out: list[tuple[str, float]] = []
            for start in range(0, len(texts), BATCH):
                enc = tokenizer.encode_batch(texts[start:start + BATCH])
                feeds: dict[str, Any] = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64)}
                if "attention_mask" in names:
                    feeds["attention_mask"] = np.array([e.attention_mask for e in enc], dtype=np.int64)
                for row in session.run(None, feeds)[0]:
                    top = max(row)
                    exp = [math.exp(x - top) for x in row]
                    best = max(range(len(row)), key=row.__getitem__)
                    out.append((_canonical(id2label.get(best, f"label_{best}")), exp[best] / sum(exp)))
            return out

        return predict, f"distilbert-finance-sentiment ({'int8' if 'quantized' in model.name else 'fp32'} ONNX)"
    except Exception as exc:  # noqa: BLE001
        log.warning("sentiment ONNX model could not be loaded (%s)", exc)
        return None


def _sklearn_backend() -> tuple[Any, str] | None:
    path = ARTIFACT_DIR / "sklearn.joblib"
    if not path.is_file():
        return None
    try:
        import joblib

        pipeline = joblib.load(path)["pipeline"]
        classes = [str(c) for c in pipeline.classes_]

        def predict(texts: list[str]) -> list[tuple[str, float]]:
            probs = pipeline.predict_proba(texts)
            return [(_canonical(classes[int(row.argmax())]), float(row.max())) for row in probs]

        return predict, "tf-idf + logistic regression"
    except Exception as exc:  # noqa: BLE001
        log.warning("sentiment sklearn model could not be loaded (%s)", exc)
        return None


def _preferred() -> str:
    """deploy.json names the rung that won on the held-out test ('onnx' or 'sklearn'); default onnx."""
    try:
        data = json.loads((ARTIFACT_DIR / "deploy.json").read_text(encoding="utf-8"))
        return "sklearn" if data.get("backend") == "sklearn" else "onnx"
    except (OSError, ValueError):
        return "onnx"


def _probe() -> None:
    global _backend, _backend_name, _probed
    with _lock:
        if _probed:
            return
        order = (_sklearn_backend, _onnx_backend) if _preferred() == "sklearn" else (_onnx_backend, _sklearn_backend)
        found = order[0]() or order[1]()
        if found is not None:
            _backend, _backend_name = found
        _probed = True
        log.info("sentiment backend: %s", _backend_name)


def reset() -> None:
    """Forget the loaded model (tests / after retraining)."""
    global _backend, _backend_name, _probed
    with _lock:
        _backend, _backend_name, _probed = None, "none", False


def available() -> bool:
    _probe()
    return _backend is not None


def backend_name() -> str:
    _probe()
    return _backend_name


def predict(texts: list[str]) -> list[tuple[str, float]]:
    """[(label, score)] per text. Raises LookupError when no trained model is present."""
    _probe()
    if _backend is None:
        raise LookupError("no sentiment model in " + str(ARTIFACT_DIR))
    if not texts:
        return []
    return [(lab, round(float(score), 4)) for lab, score in _backend([" ".join((t or "").split())[:1000] for t in texts])]


def label_many(texts: list[str]) -> list[dict[str, Any]]:
    return [{"label": lab, "score": score} for lab, score in predict(texts)]


def label(text: str) -> dict[str, Any]:
    """{label, score} for one headline or sentence."""
    return label_many([text])[0]


def artifact_dir() -> Path:
    return ARTIFACT_DIR
