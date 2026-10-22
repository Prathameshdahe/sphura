"""Startup / shutdown for the agent: the SQLite checkpointer and the local-model warm-up.

The warm-up keeps the preferred Ollama model loaded (`keep_alive` 45 m, refreshed every 4 minutes) so the first
answer of a demo does not pay the ~2-minute cold load. It stays away from the GPU while the training engineer's
`training/GPU_BUSY` flag exists, and every error is swallowed: a missing Ollama is not a server problem.
Set SPHURA_OLLAMA_WARMUP=0 to switch the warm-up off (e.g. a mock-only server while the GPU is training).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import threading
import time
from typing import Any

import httpx

from app.agent import graph as graph_module
from app.agent.models import KEEP_ALIVE, LOCAL_NUM_CTX, gpu_busy, native_ollama_base
from app.core.config import settings
from app.llm import local
from app.llm.catalog import preferred_local

log = logging.getLogger("sphura.agent.lifecycle")

WARM_INTERVAL_S = 240.0
KEEP_ALIVE_S = 45 * 60.0  # KEEP_ALIVE ("45m") in seconds
CHECK_INTERVAL_S = 30.0   # how often the GPU flag is looked at
WARM_TIMEOUT_S = 300.0  # a cold 4B load can take minutes; this runs in the background
_conn: Any = None
_saver: Any = None
_warm_task: asyncio.Task | None = None
_warm: dict[str, float] = {}  # model name → monotonic time of the last successful warm-up


def warm_up_enabled() -> bool:
    return os.environ.get("SPHURA_OLLAMA_WARMUP", "1").strip().lower() not in ("0", "false", "no", "off")


def preload_enabled() -> bool:
    """CPU models are preloaded at startup unless SPHURA_PRELOAD=0 (and never inside the test runner)."""
    off = os.environ.get("SPHURA_PRELOAD", "1").strip().lower() in ("0", "false", "no", "off")
    return not off and "pytest" not in sys.modules


def preload_cpu_models() -> None:
    """Load the trained router, NLI verifier, categoriser and sentiment model (CPU) so the first demo answer does
    not pay their load time. Each step is optional and fails soft; RAG embeddings are warmed by the documents API."""
    steps = []
    try:
        from app.agent.classify import router_predict

        steps.append(("router", lambda: router_predict("warm up the finance router")))
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.features.verify import nli

        steps.append(("nli", lambda: nli.get(wait_s=300.0)))
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.features.finance import categoriser_model

        steps.append(("categoriser", lambda: categoriser_model.predict_one("UPI/SWIGGY/warm up", "debit")))
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.features.market import sentiment

        steps.append(("sentiment", lambda: sentiment.label_many(["Markets rose today"])))
    except Exception:  # noqa: BLE001
        pass
    for name, fn in steps:
        started = time.perf_counter()
        try:
            fn()
            log.info("preloaded %s in %.0f ms", name, (time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001
            log.info("preload of %s skipped: %s", name, exc)


def checkpoint_path() -> str:
    return str(settings.data_dir / "graph.db")


def warm_model() -> str | None:
    """The local model the warm-up last kept loaded (None when nothing has been warmed)."""
    return max(_warm, key=_warm.__getitem__) if _warm else None


def mark_warm(name: str) -> None:
    """A local model just answered, so Ollama keeps it resident for KEEP_ALIVE."""
    _warm[name] = time.monotonic()


def is_warm(name: str) -> bool:
    """Loaded by the warm-up or used for an answer within the keep-alive window (best effort, this process)."""
    seen = _warm.get(name)
    return seen is not None and time.monotonic() - seen < KEEP_ALIVE_S




def warm_target(installed: list[str]) -> str | None:
    """The local model that last answered here, else DEFAULT_MODEL when it is an installed Ollama model, else
    qwen3.5 → nemotron → sphura-fin → others. Only one 4B model fits in 6 GB of VRAM, so re-warming anything but
    the model in use would evict it and the next answer would pay a full reload."""
    recent = warm_model()
    if recent in installed:
        return recent
    wanted = settings.default_model.strip()
    if wanted.startswith("ollama:") and wanted.split(":", 1)[1] in installed:
        return wanted.split(":", 1)[1]
    return preferred_local(installed)


def warm_payload(name: str) -> dict[str, Any]:
    """A one-token /api/generate request: loads the model, keeps it resident for KEEP_ALIVE and runs one prompt so
    the GPU kernels are initialised before the first real question."""
    return {"model": name, "prompt": "Hi", "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
            "options": {"num_ctx": LOCAL_NUM_CTX, "num_predict": 1}}


async def warm_up_once(client: httpx.AsyncClient | None = None) -> str | None:
    """Load the preferred local model with keep_alive (unless the GPU is reserved); returns its name or None."""
    if gpu_busy():
        return None
    status = await asyncio.to_thread(local.discover, "ollama")
    if not status.reachable or not status.models:
        return None
    name = warm_target(status.models)
    if not name:
        return None
    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(WARM_TIMEOUT_S, connect=3.0))
    try:
        # Same num_ctx as every ChatOllama call: Ollama reloads a runner whose context size differs.
        r = await client.post(f"{native_ollama_base()}/api/generate", json=warm_payload(name))
        r.raise_for_status()
    finally:
        if own:
            await client.aclose()
    _warm[name] = time.monotonic()
    log.info("local model %s kept loaded (keep_alive %s)", name, KEEP_ALIVE)
    return name


async def release_local(client: httpx.AsyncClient | None = None) -> list[str]:
    """Unload the models this process kept warm (keep_alive 0) so a training job gets the VRAM back."""
    names = list(_warm)
    if not names:
        return []
    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=3.0))
    try:
        for name in names:
            try:
                await client.post(f"{native_ollama_base()}/api/generate", json={"model": name, "keep_alive": 0})
            except Exception as exc:  # noqa: BLE001
                log.info("could not unload %s: %s", name, exc)
            _warm.pop(name, None)
    finally:
        if own:
            await client.aclose()
    log.info("released local model(s) for the GPU job: %s", ", ".join(names))
    return names


async def _warm_loop() -> None:
    """Every CHECK_INTERVAL_S: unload while training/GPU_BUSY exists, else re-warm every WARM_INTERVAL_S."""
    last = -WARM_INTERVAL_S
    while True:
        try:
            if gpu_busy():
                await release_local()
            elif time.monotonic() - last >= WARM_INTERVAL_S:
                await warm_up_once()
                last = time.monotonic()
        except Exception as exc:  # noqa: BLE001 — never a server problem
            log.info("local model warm-up skipped: %s", exc)
        await asyncio.sleep(CHECK_INTERVAL_S)


async def startup(warm: bool = True) -> None:
    """Open data_dir/graph.db for the AsyncSqliteSaver, compile the checkpointed graph, start the warm-up."""
    global _conn, _saver, _warm_task
    await shutdown()
    try:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        _conn = await aiosqlite.connect(checkpoint_path())
        _saver = AsyncSqliteSaver(_conn)
        await _saver.setup()
        graph_module.set_checkpointer(_saver, asyncio.get_running_loop())
        log.info("graph checkpointer ready (%s)", checkpoint_path())
    except Exception as exc:  # noqa: BLE001 — the graph still runs without a checkpointer
        log.warning("graph checkpointer unavailable (%s); running without one", exc)
        _conn = _saver = None
        graph_module.set_checkpointer(None)
    if preload_enabled():
        threading.Thread(target=preload_cpu_models, name="sphura-preload", daemon=True).start()
    if warm and warm_up_enabled():
        _warm_task = asyncio.create_task(_warm_loop(), name="sphura-ollama-warmup")


async def shutdown() -> None:
    global _conn, _saver, _warm_task
    if _warm_task is not None:
        _warm_task.cancel()
        with contextlib.suppress(BaseException):
            await _warm_task
        _warm_task = None
    graph_module.set_checkpointer(None)
    if _conn is not None:
        with contextlib.suppress(Exception):
            await _conn.close()
    _conn = _saver = None


def checkpointer() -> Any:
    return _saver
