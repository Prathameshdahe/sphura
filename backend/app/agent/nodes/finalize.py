"""finalize: title for a new chat, memory write, persist the assistant message exactly as before."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agent import adapters, prompts
from app.agent.run import attach
from app.agent.state import FinState

log = logging.getLogger("sphura.agent.finalize")


async def finalize(state: FinState) -> dict[str, Any]:
    run = attach(state)
    answer = state.get("draft") or ""
    run.content = answer
    if not answer.strip():
        run.status, run.error = "error", "The model returned an empty answer. Try again or pick another model."
    if run.turn.is_new:
        run.title = (await adapters.generate_title(run) if run.status == "complete"
                     else prompts.fallback_title(run.turn.question))
    if run.status == "complete":
        await adapters.memory_after(run)
    run.finish_steps()
    try:
        await asyncio.to_thread(run.save, answer)
    except Exception:  # noqa: BLE001 — the stream layer reports it
        log.exception("could not save assistant message")
        run.status, run.error = "error", "The answer couldn't be saved. Please try again."
    return {"title": run.title, "draft": answer, "steps": run.steps, "sources": run.registry.sources(),
            "memory_used": int(run.meta_extra.get("memoryUsed", 0) or 0)}
