"""Hallucination meter: after every sourced answer, check each claim against its sources with the NLI model.

before_answer starts loading the model in the background (so it's ready when the answer ends); after_answer
emits the `verify` step, the `verification` SSE event and `message.meta.verification`. Without a model, or when
the only sources are workspace code files (which an NLI model can't judge), the plugin stays silent.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.features.verify import nli, verifier

if TYPE_CHECKING:
    from app.agent.orchestrator import AgentRun

log = logging.getLogger("sphura.verify")

LOAD_WAIT_S = 20.0       # model on disk: loading takes ~1-2 s
DOWNLOAD_WAIT_S = 8.0    # first run: the download keeps going in the background for the next answer
VERIFY_TIMEOUT_S = 15.0


class VerifyPlugin:
    """See the module docstring."""

    async def before_answer(self, run: AgentRun) -> None:
        nli.prefetch()

    async def after_answer(self, run: AgentRun) -> None:
        if run.status != "complete" or not len(run.registry) or run.stop.is_set() or not run.content.strip():
            return
        skip = verifier.code_sources(run.registry.sources(), run.turn.workspace_id)
        if len(skip) >= len(run.registry):
            return  # only workspace code files: nothing an NLI model can judge
        scorer = await nli.aget(LOAD_WAIT_S if nli.on_disk() else DOWNLOAD_WAIT_S)
        if scorer is None:
            return
        contexts = {i: run.registry.context_for(i) or "" for i in range(1, len(run.registry) + 1)}
        run.phase("analyzing", "Checking claims against sources")
        step = run.step_start("verify", "Checking claims against sources")
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(verifier.verify, run.content, contexts, scorer, skip_sources=skip),
                VERIFY_TIMEOUT_S)
        except asyncio.TimeoutError:
            run.step_end(step, "error", "Verification timed out")
            return
        except Exception:  # noqa: BLE001
            log.exception("verification failed")
            run.step_end(step, "error", "Verification failed")
            return
        log.info("verified %d sentences in %.0f ms: %s (%.2f)", len(result["sentences"]),
                 (time.perf_counter() - started) * 1000, result["label"], result["score"])
        run.step_end(step, "done", verifier.summary(result))
        run.emit("verification", {"verification": result})
        run.meta_extra["verification"] = result


plugin = VerifyPlugin()
