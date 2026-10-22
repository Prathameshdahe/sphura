"""Headline sentiment: the training engineer's fine-tuned model when present, else a tiny lexicon.

Lookup order (each step is optional and fails soft):
  1. `app.features.sentiment` — a module the training engineer may ship with `predict(texts) -> list[...]`
     where each item is ("positive"|"neutral"|"negative", score) or {"label": ..., "score": ...}.
  2. an ONNX export in backend/ml/artifacts/sentiment/ (model*.onnx + tokenizer.json + config.json with id2label),
     run with onnxruntime + tokenizers (the same stack the NLI verifier uses; no torch needed).
  3. the lexicon below.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR

log = logging.getLogger("sphura.market.sentiment")

ARTIFACT_DIR = BACKEND_DIR / "ml" / "artifacts" / "sentiment"
LABELS = ("positive", "neutral", "negative")
_POSITIVE = re.compile(
    r"\b(surge|surges|surged|rally|rallies|rallied|gain|gains|gained|profit|profits|beat|beats|upgrade|upgraded|"
    r"record|strong|stronger|growth|grow|grows|jump|jumps|jumped|soar|soars|soared|rise|rises|rose|rising|"
    r"outperform|outperforms|bullish|dividend|expansion|expands|buyback|approval|approved|wins|won|high|higher|"
    r"boost|boosts|boosted|recover|recovers|recovery|rebound|rebounds|optimistic|positive|upbeat|robust|"
    r"milestone|breakthrough|hits? record)\b", re.I)
_NEGATIVE = re.compile(
    r"\b(fall|falls|fell|falling|drop|drops|dropped|loss|losses|decline|declines|declined|plunge|plunges|plunged|"
    r"downgrade|downgraded|weak|weaker|miss|misses|missed|slump|slumps|slumped|crash|crashes|crashed|fraud|probe|"
    r"penalty|penalties|bearish|cut|cuts|layoff|layoffs|default|defaults|slowdown|tumble|tumbles|tumbled|sink|"
    r"sinks|sank|low|lower|lowest|concern|concerns|worry|worries|risk|risks|lawsuit|fine|fined|ban|banned|"
    r"warning|warns|warned|selloff|sell-off|volatile|volatility|pressure|debt|bankrupt|bankruptcy|scam|"
    r"investigation|negative|pessimistic|disappoint|disappoints|disappointing|halt|halted|recall)\b", re.I)

_lock = threading.Lock()
_backend: Any = None       # callable(texts) -> list[(label, score)]
_backend_name = "lexicon"
_probed = False


def lexicon(text: str) -> tuple[str, float]:
    pos = len(_POSITIVE.findall(text or ""))
    neg = len(_NEGATIVE.findall(text or ""))
    if pos == neg:
        return "neutral", 0.5 if pos == 0 else 0.55
    score = abs(pos - neg) / (pos + neg + 1)
    return ("positive" if pos > neg else "negative"), round(min(0.95, 0.55 + score / 2), 3)


def _normalise(item: Any) -> tuple[str, float]:
    if isinstance(item, dict):
        label, score = item.get("label"), item.get("score", 0.5)
    elif isinstance(item, (tuple, list)) and len(item) >= 2:
        label, score = item[0], item[1]
    else:
        label, score = str(item), 0.5
    label = str(label).lower()
    if label.startswith("pos") or label in ("bullish", "label_2"):
        label = "positive"
    elif label.startswith("neg") or label in ("bearish", "label_0"):
        label = "negative"
    elif label not in LABELS:
        label = "neutral"
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0.5
    return label, round(max(0.0, min(1.0, score)), 3)


def _module_backend() -> Any | None:
    try:
        import importlib

        mod = importlib.import_module("app.features.sentiment")
    except Exception:  # noqa: BLE001
        return None
    fn = getattr(mod, "predict", None) or getattr(mod, "label", None) or getattr(mod, "classify", None)
    return fn if callable(fn) else None


def _onnx_backend() -> Any | None:
    if not ARTIFACT_DIR.is_dir():
        return None
    model = next((p for p in (ARTIFACT_DIR / "model_quantized.onnx", ARTIFACT_DIR / "model.onnx",
                              ARTIFACT_DIR / "onnx" / "model_quantized.onnx", ARTIFACT_DIR / "onnx" / "model.onnx")
                  if p.is_file()), None)
    tokenizer_path = ARTIFACT_DIR / "tokenizer.json"
    config_path = ARTIFACT_DIR / "config.json"
    if model is None or not tokenizer_path.is_file() or not config_path.is_file():
        return None
    try:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        config = json.loads(config_path.read_text(encoding="utf-8"))
        id2label = {int(k): str(v) for k, v in (config.get("id2label") or {}).items()}
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(128)
        tokenizer.enable_padding()
        session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
        names = {i.name for i in session.get_inputs()}

        def predict(texts: list[str]) -> list[tuple[str, float]]:
            enc = tokenizer.encode_batch(list(texts))
            feeds: dict[str, Any] = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64)}
            if "attention_mask" in names:
                feeds["attention_mask"] = np.array([e.attention_mask for e in enc], dtype=np.int64)
            if "token_type_ids" in names:
                feeds["token_type_ids"] = np.array([e.type_ids for e in enc], dtype=np.int64)
            logits = session.run(None, feeds)[0]
            out = []
            for row in logits:
                exp = [math.exp(x - max(row)) for x in row]
                probs = [x / sum(exp) for x in exp]
                best = max(range(len(probs)), key=probs.__getitem__)
                out.append((id2label.get(best, f"label_{best}"), probs[best]))
            return out

        return predict
    except Exception as exc:  # noqa: BLE001
        log.warning("sentiment ONNX model could not be loaded (%s); using the lexicon", exc)
        return None


def _probe() -> None:
    global _backend, _backend_name, _probed
    with _lock:
        if _probed:
            return
        fn = _module_backend()
        if fn is not None:
            _backend, _backend_name = fn, "app.features.sentiment"
            try:  # the training engineer's module names its backend, e.g. "distilbert-finance-sentiment (int8 ONNX)"
                import importlib

                _backend_name = str(importlib.import_module("app.features.sentiment").model.backend_name())
            except Exception:  # noqa: BLE001
                pass
        else:
            fn = _onnx_backend()
            if fn is not None:
                _backend, _backend_name = fn, "distilbert-finance-sentiment (ONNX)"
        _probed = True
        log.info("news sentiment backend: %s", _backend_name)


def reset() -> None:
    """Forget the probed backend (tests / after training)."""
    global _backend, _backend_name, _probed
    with _lock:
        _backend, _backend_name, _probed = None, "lexicon", False


def backend_name() -> str:
    _probe()
    return _backend_name


def label_many(texts: list[str]) -> list[dict[str, Any]]:
    """[{label, score}] per text; the trained model when available, else the lexicon. Never raises."""
    _probe()
    if _backend is not None and texts:
        try:
            raw = _backend(list(texts))
            if len(raw) == len(texts):
                return [dict(zip(("label", "score"), _normalise(item))) for item in raw]
        except Exception as exc:  # noqa: BLE001
            log.warning("sentiment model failed (%s); using the lexicon", exc)
    return [dict(zip(("label", "score"), lexicon(t))) for t in texts]


def available_model_dir() -> Path | None:
    return ARTIFACT_DIR if ARTIFACT_DIR.is_dir() else None
