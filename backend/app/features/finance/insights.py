"""Optional LLM-written insights over the computed report (falls back to the deterministic ones)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.llm import registry

log = logging.getLogger("sphura.finance.insights")

INSIGHTS_TIMEOUT_S = 15.0
LOCAL_TIMEOUT_S = 8.0
LOCAL_PROVIDERS = ("ollama", "lmstudio")
_SYSTEM = ("You are a precise financial analyst. Using ONLY the computed figures in the JSON below, write 3 to 5 "
           "short, specific insights about this data, one per line, each starting with \"- \". Quote exact figures "
           "with their currency, compare months or categories, and point out anything unusual. No preamble, no "
           "headings, no advice to buy or sell specific securities.")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$")


def _compact(report: dict[str, Any]) -> dict[str, Any]:
    keys = ("filename", "kind", "currency", "period", "totals", "byMonth", "balanceSheet", "insights")
    out = {k: report.get(k) for k in keys if report.get(k)}
    if report.get("byCategory"):
        out["byCategory"] = report["byCategory"][:10]
    if report.get("topTransactions"):
        out["topTransactions"] = report["topTransactions"][:5]
    return out


def parse_bullets(raw: str) -> list[str]:
    lines = []
    for line in (raw or "").splitlines():
        m = _BULLET.match(line)
        text = (m.group(1) if m else "").strip().strip("*").strip()
        if 15 <= len(text) <= 320:
            lines.append(text)
    return lines[:5]


async def llm_insights(report: dict[str, Any], timeout: float = INSIGHTS_TIMEOUT_S) -> list[str] | None:
    """3-5 bullets from the default model, or None (no model, mock model, error, or unusable text)."""
    try:
        model = await asyncio.to_thread(registry.resolve_model, None)
    except Exception as exc:  # noqa: BLE001
        log.info("finance insights: no model (%s)", exc)
        return None
    if model.provider == "mock":
        return None
    if model.provider in LOCAL_PROVIDERS:
        from app.agent import lifecycle
        from app.agent.models import gpu_busy

        # the dashboard must not wait on a model that is loading or evicted by a training job: the deterministic
        # insights are already in the report
        if gpu_busy() or (model.provider == "ollama" and not lifecycle.is_warm(model.name)):
            return None
        timeout = min(timeout, LOCAL_TIMEOUT_S)
    messages = [{"role": "system", "content": _SYSTEM},
                {"role": "user", "content": json.dumps(_compact(report), ensure_ascii=False)[:12_000]}]
    try:
        raw = await asyncio.wait_for(registry.complete(model, messages, temperature=0.2, timeout=timeout - 2),
                                     timeout)
    except Exception as exc:  # noqa: BLE001
        log.info("finance insights: model call failed (%s)", exc)
        return None
    bullets = parse_bullets(raw)
    return bullets if len(bullets) >= 2 else None
