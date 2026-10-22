"""GPU sharing protocol between the training and backend engineers (one GPU job at a time).

While a GPU job runs, `training/GPU_BUSY` exists (it holds the job name, pid and start time) and the backend
must not call Ollama. Before the job starts we unload every Ollama model (`ollama ps` → `ollama stop <model>`)
so the 6 GB of VRAM are free; the lock is removed when the job ends, even on failure.

    from gpu_lock import gpu_lock
    with gpu_lock("sft"):
        ...

CLI:  python gpu_lock.py status | release
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

LOCK_PATH = Path(__file__).resolve().parent / "GPU_BUSY"


def _ollama(*args: str) -> str:
    try:
        return subprocess.run(["ollama", *args], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def loaded_models() -> list[str]:
    """Names of the models Ollama currently holds in memory (first column of `ollama ps`)."""
    lines = [ln for ln in _ollama("ps").splitlines()[1:] if ln.strip()]
    return [ln.split()[0] for ln in lines]


def stop_ollama_models() -> list[str]:
    stopped = []
    for name in loaded_models():
        _ollama("stop", name)
        stopped.append(name)
    return stopped


def is_busy() -> bool:
    return LOCK_PATH.exists()


@contextlib.contextmanager
def gpu_lock(job: str, wait_s: float = 0.0) -> Iterator[Path]:
    """Create training/GPU_BUSY for the duration of `job`; waits up to `wait_s` for an existing lock."""
    deadline = time.time() + wait_s
    while LOCK_PATH.exists() and time.time() < deadline:
        time.sleep(5)
    if LOCK_PATH.exists():
        raise RuntimeError(f"{LOCK_PATH} exists — another GPU job is running ({LOCK_PATH.read_text().strip()})")
    stopped = stop_ollama_models()
    LOCK_PATH.write_text(f"{job} pid={os.getpid()} started={time.strftime('%Y-%m-%dT%H:%M:%S')}\n", encoding="utf-8")
    if stopped:
        print(f"[gpu_lock] stopped Ollama models: {', '.join(stopped)}")
    print(f"[gpu_lock] acquired for {job}")
    try:
        yield LOCK_PATH
    finally:
        with contextlib.suppress(OSError):
            LOCK_PATH.unlink()
        print(f"[gpu_lock] released ({job})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "release":
        with contextlib.suppress(OSError):
            LOCK_PATH.unlink()
        print("released")
    else:
        print("busy: " + LOCK_PATH.read_text().strip() if LOCK_PATH.exists() else "free")
        print("ollama loaded:", loaded_models() or "none")
