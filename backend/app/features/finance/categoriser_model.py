"""Loader for the trained transaction categoriser (backend/ml/artifacts/categoriser/).

Backends, first available wins (each fails soft, so the rule categoriser always remains):
  1. DistilBERT fine-tune exported to ONNX — `model_quantized.onnx` (int8) or `model.onnx`, with
     `tokenizer.json` and `config.json` (id2label); run with onnxruntime + tokenizers (no torch needed).
  2. the sklearn ladder — `sklearn.joblib` ({"pipeline": TF-IDF + logistic regression, "labels", "display"}).
The model input is "<credit|debit> | <narration>" (see ml/categoriser_data.model_text); outputs are the
dashboard display names ("Dining", "Loans & EMI", …) from `labels.json`.

Cascade: when both backends load, the deploy.json winner answers and any row it is unsure of (confidence below
CASCADE_THRESHOLD) goes to the other one, whose answer is kept only at FALLBACK_MIN or above: DistilBERT is
overconfident and gives gibberish such as "MYSTERY MERCHANT" 0.76-0.88, which must stay "Other". TF-IDF wins on
narrations shaped like its training data (98.6% vs 95.4%) but falls to 53.6% on merchants it never saw, where
DistilBERT keeps 69.8%; the cascade scores 98.1% and 64.9% (scripts/workbook_test.py, samples/test_workbooks).
"""
from __future__ import annotations

import json
import logging
import math
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR

log = logging.getLogger("sphura.finance.categoriser")

ARTIFACT_DIR = BACKEND_DIR / "ml" / "artifacts" / "categoriser"
MAX_TOKENS = 64
BATCH = 64
CASCADE_THRESHOLD = 0.5
FALLBACK_MIN = 0.9

_lock = threading.Lock()
_backend: Any = None          # callable(list[str]) -> list[(label_id, prob)]
_backend_name = "none"
_fallback: Any = None         # the other backend, asked when the first is unsure
_display: dict[str, str] = {}
_probed = False


def model_text(text: str, direction: str) -> str:
    """Exactly what the training data looked like (ml/categoriser_data.model_text)."""
    return f"{direction} | {' '.join((text or '').split())}"


def _load_display() -> dict[str, str]:
    try:
        data = json.loads((ARTIFACT_DIR / "labels.json").read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in (data.get("display") or {}).items()}
    except (OSError, ValueError):
        return {}


def _onnx_backend() -> Any | None:
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
        options.intra_op_num_threads = 2  # the API serves other requests while a statement is categorised
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
                    total = sum(exp)
                    best = max(range(len(row)), key=row.__getitem__)
                    out.append((id2label.get(best, f"label_{best}"), exp[best] / total))
            return out

        return predict, f"distilbert ({'int8' if 'quantized' in model.name else 'fp32'} ONNX)"
    except Exception as exc:  # noqa: BLE001
        log.warning("categoriser ONNX model could not be loaded (%s)", exc)
        return None


def _sklearn_backend() -> Any | None:
    path = ARTIFACT_DIR / "sklearn.joblib"
    if not path.is_file():
        return None
    try:
        import joblib

        bundle = joblib.load(path)
        pipeline = bundle["pipeline"]
        classes = [str(c) for c in pipeline.classes_]

        def predict(texts: list[str]) -> list[tuple[str, float]]:
            probs = pipeline.predict_proba(texts)
            return [(classes[int(row.argmax())], float(row.max())) for row in probs]

        return predict, str(bundle.get("model_name") or "tf-idf + logistic regression")
    except Exception as exc:  # noqa: BLE001
        log.warning("categoriser sklearn model could not be loaded (%s)", exc)
        return None


def _preferred() -> str:
    """deploy.json names the rung that won on the held-out test ('onnx' or 'sklearn'); default onnx."""
    try:
        data = json.loads((ARTIFACT_DIR / "deploy.json").read_text(encoding="utf-8"))
        return "sklearn" if data.get("backend") == "sklearn" else "onnx"
    except (OSError, ValueError):
        return "onnx"


def _probe() -> None:
    global _backend, _backend_name, _fallback, _display, _probed
    with _lock:
        if _probed:
            return
        order = (_sklearn_backend, _onnx_backend) if _preferred() == "sklearn" else (_onnx_backend, _sklearn_backend)
        first, second = order[0](), order[1]()
        found = first or second
        if found is not None:
            _backend, _backend_name = found
        if first is not None and second is not None:
            _fallback = second[0]
            _backend_name = f"{first[1]}, {second[1]} when unsure"
        _display = _load_display()
        _probed = True
        log.info("transaction categoriser backend: %s", _backend_name)


def reset() -> None:
    """Forget the loaded model (tests / after retraining)."""
    global _backend, _backend_name, _fallback, _display, _probed
    with _lock:
        _backend, _backend_name, _fallback, _display, _probed = None, "none", None, {}, False
    predict_one.cache_clear()


def available() -> bool:
    _probe()
    return _backend is not None


def backend_name() -> str:
    _probe()
    return _backend_name


def _display_name(label: str) -> str:
    return _display.get(label) or label.replace("_", " ").title()


def predict_many(texts: list[str], directions: list[str]) -> list[tuple[str, float]] | None:
    """[(display category, confidence)] per narration, or None when no model is available. Never raises."""
    _probe()
    if _backend is None or not texts:
        return None
    inputs = [model_text(t, d) for t, d in zip(texts, directions)]
    try:
        raw = _backend(inputs)
    except Exception as exc:  # noqa: BLE001
        log.warning("categoriser model failed (%s); using the rules", exc)
        return None
    unsure = [i for i, (_, prob) in enumerate(raw) if prob < CASCADE_THRESHOLD]
    if unsure and _fallback is not None:
        try:
            for i, pred in zip(unsure, _fallback([inputs[i] for i in unsure])):
                if pred[1] >= FALLBACK_MIN:
                    raw[i] = pred
        except Exception as exc:  # noqa: BLE001 — the first backend's answers stand
            log.warning("categoriser fallback failed (%s)", exc)
    return [(_display_name(label), round(float(prob), 4)) for label, prob in raw]


@lru_cache(maxsize=8192)
def predict_one(text: str, direction: str) -> tuple[str, float] | None:
    out = predict_many([text], [direction])
    return out[0] if out else None


def artifact_present() -> bool:
    return (ARTIFACT_DIR / "sklearn.joblib").is_file() or any(
        (ARTIFACT_DIR / n).is_file() for n in ("model_quantized.onnx", "model.onnx"))


def artifact_dir() -> Path:
    return ARTIFACT_DIR
