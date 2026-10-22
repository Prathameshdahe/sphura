"""Local NLI cross-encoder (DeBERTa-v3-xsmall fine-tuned on SNLI+MultiNLI) on onnxruntime + tokenizers.

The quantized ONNX export is downloaded once from the Hugging Face Hub into DATA_DIR/models/nli and loaded as a
lazy, thread-safe singleton. Anything that goes wrong (offline first run, missing files, a broken runtime) just
makes `get()` / `aget()` return None so the verifier switches itself off — chat never breaks.

Downloads are skipped while pytest runs (unit tests stub the scorer) and can be disabled with
SPHURA_NLI_DOWNLOAD=0; SPHURA_VERIFY=0 turns the whole feature off.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.core.config import settings

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

log = logging.getLogger("sphura.verify.nli")

REPO_ID = "Xenova/nli-deberta-v3-xsmall"
MODEL_NAME = "nli-deberta-v3-xsmall (ONNX)"
ONNX_FILES = ("onnx/model_quantized.onnx", "onnx/model_int8.onnx", "onnx/model.onnx")  # preferred first
REQUIRED_FILES = ("config.json", "tokenizer.json")
MAX_TOKENS = 200  # premise windows are ~130 tokens; caps the cost of token-dense text (code)
BATCH_SIZE = 8
RETRY_AFTER_S = 600.0

_lock = threading.Lock()
_future_lock = threading.Lock()
_scorer: NLIScorer | None = None
_future: concurrent.futures.Future | None = None
_failed_at: float | None = None


def model_dir() -> Path:
    return settings.data_dir / "models" / "nli"


def _off(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("0", "false", "no", "off")


def disabled() -> bool:
    return _off("SPHURA_VERIFY")


def downloads_allowed() -> bool:
    return not _off("SPHURA_NLI_DOWNLOAD") and "PYTEST_CURRENT_TEST" not in os.environ


def _local_onnx(directory: Path) -> str | None:
    if not all((directory / f).is_file() for f in REQUIRED_FILES):
        return None
    return next((f for f in ONNX_FILES if (directory / f).is_file()), None)


def on_disk() -> bool:
    return _local_onnx(model_dir()) is not None


def can_load() -> bool:
    """True when a scorer is loaded or could be (files on disk, or a download is allowed)."""
    if _scorer is not None:
        return True
    if disabled():
        return False
    if _failed_at is not None and time.monotonic() - _failed_at < RETRY_AFTER_S:
        return False
    return on_disk() or downloads_allowed()


def _label_indexes(config: dict[str, Any]) -> dict[str, int]:
    """{"entailment": i, "neutral": j, "contradiction": k} from config.json's id2label."""
    out: dict[str, int] = {}
    for key, label in (config.get("id2label") or {}).items():
        name = str(label).lower()
        for canonical in ("entailment", "neutral", "contradiction"):
            if name.startswith(canonical[:6]):
                out[canonical] = int(key)
    if "entailment" not in out:
        raise ValueError(f"config.json has no entailment label: {config.get('id2label')}")
    return out


class NLIScorer:
    """Batched P(label | premise, hypothesis). Thread-safe: ORT sessions and HF tokenizers allow concurrent use."""

    name = MODEL_NAME

    def __init__(self, directory: Path, onnx_file: str) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._np = np
        config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
        self.labels = _label_indexes(config)
        pad_id = int(config.get("pad_token_id") or 0)
        self._tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=MAX_TOKENS, strategy="longest_first")
        pad_token = self._tokenizer.id_to_token(pad_id) or "[PAD]"
        self._tokenizer.enable_padding(pad_id=pad_id, pad_token=pad_token)

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = max(1, min(8, (os.cpu_count() or 2) // 2))  # >8 threads measured slower
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self._session = ort.InferenceSession(str(directory / onnx_file), options,
                                             providers=["CPUExecutionProvider"])
        self._inputs = {i.name for i in self._session.get_inputs()}
        self.onnx_file = onnx_file

    def _batch(self, pairs: Sequence[tuple[str, str]]) -> Any:
        np = self._np
        encodings = self._tokenizer.encode_batch([(p, h) for p, h in pairs])
        feeds = {"input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                 "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64)}
        if "token_type_ids" in self._inputs:
            feeds["token_type_ids"] = np.array([e.type_ids for e in encodings], dtype=np.int64)
        logits = self._session.run(None, feeds)[0].astype(np.float64)
        logits -= logits.max(axis=-1, keepdims=True)
        exp = np.exp(logits)
        return exp / exp.sum(axis=-1, keepdims=True)

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[dict[str, float]]:
        """Label probabilities per (premise, hypothesis); pairs are length-sorted into batches to cut padding."""
        if not pairs:
            return []
        order = sorted(range(len(pairs)), key=lambda i: len(pairs[i][0]) + len(pairs[i][1]))
        out: list[dict[str, float]] = [{} for _ in pairs]
        for start in range(0, len(order), BATCH_SIZE):
            idx = order[start:start + BATCH_SIZE]
            probs = self._batch([pairs[i] for i in idx])
            for row, i in enumerate(idx):
                out[i] = {label: float(probs[row][col]) for label, col in self.labels.items()}
        return out

    def entailment(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        return [p["entailment"] for p in self.predict(pairs)]


def _download(directory: Path) -> str:
    from huggingface_hub import hf_hub_download

    directory.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_FILES:
        if not (directory / name).is_file():
            hf_hub_download(REPO_ID, name, local_dir=str(directory))
    error: Exception | None = None
    for name in ONNX_FILES:
        try:
            hf_hub_download(REPO_ID, name, local_dir=str(directory))
            return name
        except Exception as exc:  # noqa: BLE001 — try the next export
            error = exc
    raise RuntimeError(f"no ONNX export could be downloaded from {REPO_ID}") from error


def load() -> NLIScorer | None:
    """Blocking: the loaded scorer, loading (and downloading if allowed) on first use; None if unavailable."""
    global _scorer, _failed_at
    if _scorer is not None or disabled():
        return _scorer
    with _lock:
        if _scorer is not None:
            return _scorer
        if _failed_at is not None and time.monotonic() - _failed_at < RETRY_AFTER_S:
            return None
        directory = model_dir()
        try:
            onnx_file = _local_onnx(directory)
            if onnx_file is None:
                if not downloads_allowed():
                    return None
                started = time.perf_counter()
                onnx_file = _download(directory)
                log.info("NLI model %s downloaded in %.1f s", REPO_ID, time.perf_counter() - started)
            started = time.perf_counter()
            _scorer = NLIScorer(directory, onnx_file)
            _failed_at = None
            log.info("NLI model %s (%s) loaded in %.0f ms", REPO_ID, onnx_file, (time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001 — the verifier just switches itself off
            _failed_at = time.monotonic()
            log.warning("NLI verifier unavailable: %s", exc)
    return _scorer


def _start() -> concurrent.futures.Future:
    """The in-flight background load (started if none is running)."""
    global _future
    with _future_lock:
        if _future is None or _future.done():
            future: concurrent.futures.Future = concurrent.futures.Future()

            def work() -> None:
                try:
                    future.set_result(load())
                except BaseException as exc:  # noqa: BLE001
                    future.set_exception(exc)

            threading.Thread(target=work, name="sphura-nli-load", daemon=True).start()
            _future = future
        return _future


def prefetch() -> None:
    """Start loading in the background (no-op when loaded, disabled or impossible)."""
    if _scorer is None and can_load():
        _start()


def get(wait_s: float = 60.0) -> NLIScorer | None:
    """Sync: the scorer, waiting up to `wait_s` for a load/download in progress."""
    if _scorer is not None:
        return _scorer
    if not can_load():
        return None
    try:
        return _start().result(timeout=wait_s)
    except Exception:  # noqa: BLE001 — timeout or load failure
        return None


async def aget(wait_s: float) -> NLIScorer | None:
    """Async: like `get`; a slow load keeps going in the background after the wait gives up."""
    if _scorer is not None:
        return _scorer
    if not can_load():
        return None
    try:
        return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(_start())), wait_s)
    except Exception:  # noqa: BLE001
        return None
