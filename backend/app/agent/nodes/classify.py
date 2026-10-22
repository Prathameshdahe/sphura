"""classify: rules → trained finance router → keywords → (when still unsure) structured output from the model."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent import adapters, prompts
from app.agent.classify import ROUTER_THRESHOLD, Classification, classify as classify_text, label_for
from app.agent.models import chat_model, gpu_busy
from app.agent.run import attach
from app.agent.state import INTENTS, FinState

log = logging.getLogger("sphura.agent.classify")

LLM_TIMEOUT_S = 20.0
NO_LLM_PROVIDERS = ("mock", "lmstudio")
# A cloud model classifies in well under a second, so it is asked whenever the router is less than fairly sure;
# a local model only below the router's own threshold (it shares the GPU with the answer).
CLOUD_ASSIST_THRESHOLD = 0.75


class IntentOut(BaseModel):
    intent: Literal["spending", "documents", "market", "explain", "advice", "out_of_scope"]
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)


async def _llm_classify(run: Any, question: str) -> Classification | None:
    """Structured output from the chat model (thinking off); None on any failure or timeout."""
    system, user = prompts.classify_messages(question, run.turn.history)
    try:
        model = chat_model(run.model, reasoning=False, temperature=0.0, streaming=False).with_structured_output(IntentOut)
        out = await asyncio.wait_for(
            model.ainvoke([SystemMessage(content=system["content"]), HumanMessage(content=user["content"])]),
            LLM_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — the keyword result stands
        log.info("llm classification skipped: %s", exc)
        return None
    if not isinstance(out, IntentOut) or out.intent not in INTENTS:
        return None
    return Classification(out.intent, round(float(out.confidence), 3), "llm")


def _model_ready(run: Any) -> bool:
    """A cold local model is not loaded just to classify (a 20 s timeout would cut its load short)."""
    if run.model.provider != "ollama":
        return True
    from app.agent import lifecycle

    return lifecycle.is_warm(run.model.name)


async def classify(state: FinState) -> dict[str, Any]:
    run = attach(state)
    run.phase("thinking", "Understanding your question")
    question = state.get("question") or run.turn.question
    attached = [d.filename for d in await asyncio.to_thread(adapters.load_documents, run.turn.user_id,
                                                            run.turn.doc_ids)]
    result = await asyncio.to_thread(classify_text, question, web_search=run.turn.web_search, attached=attached,
                                     follow_up=bool(run.turn.history))
    cloud = run.model.provider not in ("ollama", "lmstudio", "mock")
    threshold = CLOUD_ASSIST_THRESHOLD if cloud else ROUTER_THRESHOLD
    if (result.confidence < threshold and result.method != "rule"
            and run.model.provider not in NO_LLM_PROVIDERS and (cloud or not gpu_busy()) and _model_ready(run)):
        better = await _llm_classify(run, question)
        if better is not None:
            result = better
    run.intent = result.intent
    step = run.step_start("router", f"{label_for(result.intent)} · {result.confidence:.0%}")
    run.step_end(step, "done", {"rule": "Decided by the request (attachments / web toggle)",
                                "router": "Trained finance intent router", "keywords": "Keyword classifier",
                                "llm": "Structured output from the model"}.get(result.method, result.method))
    run.meta_extra["router"] = {"label": result.intent, "confidence": result.confidence,
                                "autoSearch": result.intent == "market"}
    return {"intent": result.intent, "intent_confidence": result.confidence, "steps": run.steps}
