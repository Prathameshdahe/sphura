"""guard_in (redaction before anything else sees the text) and refuse (templated, no model call)."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from app.agent import adapters
from app.agent.guard import redact, refusal_text
from app.agent.run import attach
from app.agent.state import FinState

REDACTED_LABEL = {"card": "a card number", "account": "an account number", "aadhaar": "an Aadhaar number",
                  "pan": "a PAN"}


async def guard_in(state: FinState) -> dict[str, Any]:
    run = attach(state)
    clean, kinds = redact(run.turn.question)
    run.turn.question = clean
    run.turn.history = [{"role": m["role"], "content": redact(m["content"])[0]} for m in run.turn.history]
    if kinds:
        step = run.step_start("guard_in", "Removing sensitive numbers")
        what = ", ".join(REDACTED_LABEL.get(k, k) for k in kinds)
        run.step_end(step, "done", f"Redacted {what} before processing")
        run.meta_extra["redacted"] = kinds
    return {"question": clean, "redacted": kinds, "messages": [HumanMessage(content=clean)]}


async def refuse(state: FinState) -> dict[str, Any]:
    run = attach(state)
    text = refusal_text(state.get("question") or run.turn.question)
    # No model call at all: the template is the answer, and memory uses the rule-based extractor only, so a
    # preference stated in an off-topic message ("I prefer short answers") is not lost even with a cloud model.
    run.phase("composing", "Writing the answer")
    run.emit("delta", {"text": text})
    run.content = text
    await adapters.remember_without_model(run)
    return {"refusal": text, "draft": text, "sources": run.registry.sources(), "steps": run.steps,
            "memory_used": int(run.meta_extra.get("memoryUsed", 0) or 0)}
