"""tools: run the tool calls the draft asked for (bounded), add their results as sources and ToolMessages."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.run import AgentRun, attach, current_run
from app.agent.state import FinState
from app.agent.tools import CALCULATOR_NAMES, MARKET_NAMES, STEP_LABELS, tool_by_name

log = logging.getLogger("sphura.agent.tools")

MAX_CALLS_PER_ROUND = 4
MAX_TOOL_CALLS = 12
TOOL_TIMEOUT_S = 90.0
CALCULATOR_FILE = "Sphura calculators"


@dataclass
class _CalcSource:
    """A calculator result as a citable `doc` source (duck-typed like a RetrievedChunk)."""

    doc_id: str | None
    filename: str
    page: int | None
    chunk_index: int
    text: str
    score: float | None = None
    section: str | None = None


def _pretty(result: str) -> str:
    try:
        data = json.loads(result)
    except ValueError:
        return result
    if not isinstance(data, dict):
        return result
    parts = []
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            continue
        parts.append(f"{key}: {value}")
    return "; ".join(parts) or result


def _args_label(name: str, args: dict[str, Any]) -> str:
    base = STEP_LABELS.get(name, f"Calling {name}")
    if name in ("get_quote", "get_history") and args.get("symbol"):
        return f"{base} for {args['symbol']}"
    if name == "finance_news" and args.get("query"):
        return f"{base} for “{str(args['query'])[:50]}”"
    if name == "search_documents" and args.get("query"):
        return f"{base} for “{str(args['query'])[:50]}”"
    if name == "income_tax_estimate":
        from app.agent.tools.tax import rules

        try:
            return f"{base} ({rules()['income_tax']['financial_year']})"
        except Exception:  # noqa: BLE001
            return base
    return base


async def _run_one(run: AgentRun, call: dict[str, Any], index: int) -> ToolMessage:
    name = call.get("name") or "tool"
    args = call.get("args") or {}
    call_id = call.get("id") or f"call_{index}"
    tool = tool_by_name(name)
    if tool is None:
        step = run.step_start(name, f"Calling {name}")
        run.step_end(step, "error", "This tool isn't available")
        return ToolMessage(content=f"Tool {name} is not available.", tool_call_id=call_id, name=name)
    step = run.step_start(name, _args_label(name, args))
    try:
        result = await asyncio.wait_for(tool.ainvoke(args), TOOL_TIMEOUT_S)
        text = result if isinstance(result, str) else json.dumps(result)
    except asyncio.TimeoutError:
        run.step_end(step, "error", "The tool took too long")
        return ToolMessage(content=f"{name} timed out.", tool_call_id=call_id, name=name)
    except Exception as exc:  # noqa: BLE001 — bad arguments, provider trouble: tell the model, keep going
        detail = " ".join(str(exc).split())[:160]
        run.step_end(step, "error", detail or "Tool failed")
        return ToolMessage(content=f"{name} failed: {detail or 'error'}. Fix the arguments or answer without it.",
                           tool_call_id=call_id, name=name)
    if name in CALCULATOR_NAMES:
        summary = _pretty(text)
        source = run.registry.add_doc(_CalcSource(doc_id=None, filename=CALCULATOR_FILE, page=None,
                                                  chunk_index=run.tool_calls,
                                                  text=f"{name}({json.dumps(args)}) → {summary}",
                                                  section=f"{name} result"))
        run.emit_sources()
        run.step_end(step, "done", summary[:120])
        text = f"{text}\n\nCite these figures as [{source}]."
    else:
        first = text.splitlines()[0] if text else ""
        run.step_end(step, "done" if not text.lower().startswith(("quote unavailable", "history unavailable",
                                                                   "news unavailable", "fx rate unavailable"))
                     else "error", first[:120])
    return ToolMessage(content=text, tool_call_id=call_id, name=name)


_TAX_QUESTION = re.compile(r"\btax|\bregime\b", re.I)
_INCOME_WORDS = re.compile(r"\b(earn|earning|income|salary|ctc|package|lpa|make)\b", re.I)
_SCALED = re.compile(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(lpa|lakhs?|lacs?|l\b|crores?|cr\b)", re.I)
_RUPEES = re.compile(r"(?:₹|rs\.?|inr)\s*(\d[\d,]{4,})", re.I)


def income_in(question: str) -> float | None:
    """The annual income in a tax question ("I earn 12 LPA, which regime?"), else None."""
    if not (_TAX_QUESTION.search(question) and _INCOME_WORDS.search(question)):
        return None
    m = _SCALED.search(question)
    if m:
        value = float(m.group(1)) * (1e7 if m.group(2).lower().startswith("cr") else 1e5)
    else:
        m = _RUPEES.search(question)
        value = float(m.group(1).replace(",", "")) if m else 0.0
    return value if 1e5 <= value <= 1e9 else None


async def pre_calculate(run: AgentRun, question: str) -> None:
    """Run the calculator a question obviously needs before the first draft, so a small local model cannot skip
    it and guess (it once answered "old regime" for 12 LPA without calling the tax tool)."""
    income = income_in(question)
    if income is None or tool_by_name("income_tax_estimate") is None:
        return
    run.tool_calls += 1
    call = {"name": "income_tax_estimate", "args": {"gross_income": income, "regime": "both"}, "id": "pre_tax"}
    await _run_one(run, call, 0)
    run.notes.append("The income-tax calculator already ran for both regimes (see the calculator source). Base the "
                     "comparison on its figures and cite it; do not recompute tax yourself.")


async def tools(state: FinState) -> dict[str, Any]:
    run = attach(state)
    current_run.set(run)
    last = next((m for m in reversed(state.get("messages") or []) if isinstance(m, AIMessage)), None)
    calls = list(last.tool_calls) if last is not None else []
    allowed = max(0, min(MAX_CALLS_PER_ROUND, MAX_TOOL_CALLS - run.tool_calls))
    calls, skipped = calls[:allowed], calls[allowed:]
    names = {c.get("name") for c in calls}
    if names & MARKET_NAMES:
        run.phase("searching", "Fetching market data")
    elif "search_documents" in names:
        run.phase("reading", "Reading your documents")
    elif names:
        run.phase("analyzing", "Calculating")
    results: list[ToolMessage] = []
    for i, call in enumerate(calls):
        run.tool_calls += 1
        results.append(await _run_one(run, call, i))
    for call in skipped:
        results.append(ToolMessage(content="Tool budget exhausted: answer with what you have.",
                                   tool_call_id=call.get("id") or "call_skipped", name=call.get("name") or "tool"))
    return {"messages": results, "sources": run.registry.sources(), "steps": run.steps}
