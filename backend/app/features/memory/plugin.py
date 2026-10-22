"""Long-term memory in every chat turn (only while the user has memory enabled).

before_answer: inject up to 8 of the user's memories (the most similar to the question when there are more)
into the system prompt, with a `memory_recall` step and `meta.memoryUsed`. It also starts fact extraction from
the user's message in the background, so the LLM call overlaps the answer instead of delaying `done`.
after_answer: wait briefly (≤ 1.5 s) for that extraction, save the new facts and report them in
`meta.memoriesAdded`; if it is still running, it is saved in the background when it finishes.
"""
from __future__ import annotations

import asyncio
import logging
import weakref
from typing import TYPE_CHECKING

from app.features.memory import extract, ranking, store

if TYPE_CHECKING:
    from app.agent.orchestrator import AgentRun
    from app.llm.types import ResolvedModel

log = logging.getLogger("sphura.memory")

MAX_RECALL = 8
RECALL_SHARE = 0.08   # of the model's prompt budget (≈ 4 chars per token): 8 × 500-char memories would otherwise
MIN_RECALL_CHARS = 600  # take ~1k tokens of a 3.8k Groq / local budget before research/workspace/finance add theirs
SAVE_WAIT_S = 1.5
RANK_TIMEOUT_S = 4.0  # loading bge-small from disk takes ~1-2 s; beyond that fall back to recency
RECALL_HEADER = (
    "What you know about the user (remembered from earlier conversations). Use it only when it is relevant to "
    "the current request, and never mention that you have a memory unless the user asks about it:"
)

_background: set[asyncio.Task] = set()


def _keep(task: asyncio.Task) -> asyncio.Task:
    """Hold a reference so a fire-and-forget task isn't garbage-collected mid-flight."""
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


def recall_block(contents: list[str]) -> str:
    return RECALL_HEADER + "\n" + "\n".join(f"- {c}" for c in contents)


def fit_budget(contents: list[str], prompt_budget: int) -> list[str]:
    """The leading (most relevant / newest) memories that fit the model's share of the prompt; at least one."""
    cap = max(MIN_RECALL_CHARS, int(prompt_budget * 4 * RECALL_SHARE))
    kept: list[str] = []
    used = 0
    for content in contents:
        cost = len(content) + 3  # "- " + newline
        if kept and used + cost > cap:
            break
        kept.append(content if cost <= cap else content[: cap - 4].rstrip() + "…")
        used += cost
    return kept


async def _extract(model: ResolvedModel, user_id: str, message: str) -> list[str]:
    """New facts from the message, already de-duplicated against the user's memories (never raises)."""
    try:
        facts = await extract.extract_facts(model, message)
        if not facts:
            return []
        existing = await asyncio.to_thread(store.existing_contents, user_id)
        return await asyncio.to_thread(ranking.novel, facts, existing)
    except Exception:  # noqa: BLE001
        log.exception("memory extraction failed")
        return []


async def _save_later(task: asyncio.Task, user_id: str, conversation_id: str) -> None:
    try:
        facts = await task
        if facts:
            await asyncio.to_thread(store.save_facts, user_id, conversation_id, facts)
    except Exception:  # noqa: BLE001
        log.exception("background memory save failed")


class MemoryPlugin:
    """See the module docstring."""

    def __init__(self) -> None:
        self._pending: weakref.WeakKeyDictionary[AgentRun, asyncio.Task] = weakref.WeakKeyDictionary()

    async def before_answer(self, run: AgentRun) -> None:
        enabled, items = await asyncio.to_thread(store.recall_state, run.turn.user_id)
        if not enabled:
            return
        if extract.should_extract(run.model, run.turn.question):
            self._pending[run] = _keep(asyncio.create_task(_extract(run.model, run.turn.user_id, run.turn.question)))
        if not items:
            return
        chosen = items[:MAX_RECALL]
        if len(items) > MAX_RECALL:
            try:  # a cold/unavailable embedding model must not hold up the answer
                chosen = await asyncio.wait_for(
                    asyncio.to_thread(ranking.rank, run.turn.question, items, MAX_RECALL), RANK_TIMEOUT_S)
            except asyncio.TimeoutError:
                log.info("memory ranking timed out; recalling the most recent memories")
        step = run.step_start("memory_recall", "Recalling what I know about you")
        contents = fit_budget([content for _, content in chosen], getattr(run.model, "prompt_budget", 8000))
        run.extra_system.append(recall_block(contents))
        run.meta_extra["memoryUsed"] = len(contents)
        run.step_end(step, "done", f"{len(contents)} {'memory' if len(contents) == 1 else 'memories'}")

    async def after_answer(self, run: AgentRun) -> None:
        task = self._pending.pop(run, None)
        if task is None:
            return
        try:
            facts = await asyncio.wait_for(asyncio.shield(task), SAVE_WAIT_S)
        except asyncio.TimeoutError:
            _keep(asyncio.create_task(_save_later(task, run.turn.user_id, run.turn.conversation_id)))
            return
        if not facts:
            return
        added = await asyncio.to_thread(store.save_facts, run.turn.user_id, run.turn.conversation_id, facts)
        if added:
            run.meta_extra["memoriesAdded"] = added


plugin = MemoryPlugin()
