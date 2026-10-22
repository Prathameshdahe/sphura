"""verify: output guardrails (advice disclaimer, empty answer), computed charts, then the NLI check of claims vs
sources (chart blocks are fenced, so the claim splitter skips them)."""
from __future__ import annotations

from typing import Any

import re

from app.agent import adapters
from app.agent.prompts import outside_code
from app.agent.charts import charts_block, has_chart
from app.agent.guard import ADVICE_DISCLAIMER, needs_disclaimer
from app.agent.nodes.draft import join_answer, separator
from app.agent.run import attach
from app.agent.state import FinState


_MARKER = re.compile(r"\s?\[(\d+(?:\s*,\s*\d+)*)\](?!\()")


_WIDE = re.compile(r"【(\d+)(?:†[^】]*)?】")  # gpt-oss cites as 【3】 or 【3†L1-L4】


def normalise_citations(answer: str) -> str:
    return outside_code(answer, lambda prose: _WIDE.sub(r"[\1]", prose))


def drop_phantom_citations(answer: str, sources: int) -> str:
    """Remove [n] markers that point past the sources this turn actually has (a model citing "[2]" with none)."""
    def keep(m: re.Match[str]) -> str:
        return m.group(0) if all(1 <= int(n) <= sources for n in re.split(r"\s*,\s*", m.group(1))) else ""
    return outside_code(answer, lambda prose: _MARKER.sub(keep, prose))


async def verify(state: FinState) -> dict[str, Any]:
    run = attach(state)
    answer = drop_phantom_citations(normalise_citations(state.get("draft") or ""), len(run.registry))
    if run.charts and answer.strip() and not has_chart(answer):
        block = charts_block(run.charts)
        run.emit("delta", {"text": separator(answer, block)})
        answer = join_answer(answer, block)
    if state.get("intent") == "advice" and answer.strip() and needs_disclaimer(answer):
        run.emit("delta", {"text": separator(answer, ADVICE_DISCLAIMER)})
        answer = join_answer(answer, ADVICE_DISCLAIMER)
    run.content = answer
    verification = None
    if answer.strip() and len(run.registry):
        verification = await adapters.verify_after(run)
    return {"draft": answer, "verification": verification, "steps": run.steps}
