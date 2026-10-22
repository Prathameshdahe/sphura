"""ensemble: "Sphura Ensemble" asks every member model and merges the answers.

The lead model (Groq → NVIDIA → local, the first available) has already run the draft ⇄ tools loop with its text
held back (the client saw nothing), so every calculator / market / document result is in the source registry. Here
the other members answer the same question in parallel from those sources, each with a prompt sized for it: cloud
models get the full context, the local 4B model a compact one and a word limit. Their calls are tagged
`nostream`, so no member token reaches the client. The lead then merges the candidates into one answer, streamed
like a normal draft. With a single usable candidate the merge is skipped and that answer is sent as it is.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agent import prompts
from app.agent.models import chat_model, gpu_busy, model_label, strip_thinking, to_llm_error
from app.agent.nodes.draft import separator
from app.agent.run import AgentRun, attach
from app.agent.state import FinState
from app.llm import registry
from app.llm.think import ThinkFilter
from app.llm.types import LLMError, ResolvedModel

log = logging.getLogger("sphura.agent.ensemble")

CLOUD_TIMEOUT_S = 25.0
LOCAL_TIMEOUT_S = 25.0
LOCAL_WORDS = 160
MERGE_TAG = "sphura_merge"
NOSTREAM = "nostream"  # LangGraph keeps model calls with this tag out of the `messages` stream
MERGE_INSTRUCTION = (
    "You are merging answers that several AI models wrote to the same finance question. Write the single best "
    "final answer for the user. Keep the most accurate, specific and useful content from the candidates and drop "
    "repetition. Every figure must agree with the numbered sources (tool and calculator results, the user's "
    "documents); when candidates disagree, trust the sources and leave out unsupported numbers. Keep [n] "
    "citations that point to the numbered sources. Never mention the candidates, the models or that answers were "
    "merged. Same style rules as always: lead with the answer, Markdown, concise, no emoji. Keep any ```chart``` "
    "block a candidate wrote if its numbers come from the sources."
)


def is_active(run: AgentRun) -> bool:
    return bool(run.model.extra.get("ensemble")) and len(run.model.extra.get("ensemble") or []) > 1


def member_messages(run: AgentRun, question: str, model: ResolvedModel) -> list[BaseMessage]:
    """System + recent history + the question with the numbered sources, sized for `model`."""
    local = model.provider in ("ollama", "lmstudio")
    budget = model.prompt_budget
    system = prompts.finance_system_prompt(run.intent, len(run.registry) > 0, [], run.extra_system)
    if local:
        system += f"\n- Answer in at most {LOCAL_WORDS} words."
    fixed = prompts.estimate_tokens(system) + prompts.estimate_tokens(question) + 200
    history_budget = max(0, min(4_000, int(budget * 0.2), budget - fixed - 600))
    history = prompts.trim_history(run.turn.history, history_budget)
    used = fixed + sum(prompts.estimate_tokens(h["content"]) for h in history)
    context = run.registry.render(max(1_000, (budget - used) * 4))
    out: list[BaseMessage] = [SystemMessage(content=system)]
    for h in prompts.normalise_turns(history):
        out.append(HumanMessage(content=h["content"]) if h["role"] == "user" else AIMessage(content=h["content"]))
    out.append(HumanMessage(content=prompts.user_turn(question, context, run.searches, run.notes)))
    return out


async def _ask(run: AgentRun, model_id: str, question: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        model = registry.resolve_model(model_id)
    except LLMError as err:
        return {"id": model_id, "label": model_id, "ok": False, "ms": 0, "text": "", "error": err.message}
    label = f"{registry.PROVIDER_LABELS.get(model.provider, model.provider)} · {model_label(model)}"
    local = model.provider in ("ollama", "lmstudio")
    step = run.step_start("ensemble_member", label)
    if local and gpu_busy():
        run.step_end(step, "error", "Skipped: the GPU is busy")
        return {"id": model.id, "label": label, "ok": False, "ms": 0, "text": "", "error": "GPU busy"}
    if local:
        from app.agent import lifecycle

        if not lifecycle.is_warm(model.name):  # loading a 4B model takes 8-60 s: never make the answer wait
            run.step_end(step, "error", "Skipped: the local model is still loading")
            return {"id": model.id, "label": label, "ok": False, "ms": 0, "text": "", "error": "cold"}
    try:
        llm = chat_model(model, effort=run.turn.effort, reasoning=False, streaming=False).with_config(tags=[NOSTREAM])
        result = await asyncio.wait_for(llm.ainvoke(member_messages(run, question, model)),
                                        LOCAL_TIMEOUT_S if local else CLOUD_TIMEOUT_S)
        content = result.content if isinstance(result.content, str) else "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in result.content)
        text = strip_thinking(content)
    except Exception as exc:  # noqa: BLE001 — one member failing never fails the answer
        err = to_llm_error(exc, model.provider, model.name)
        ms = int((time.perf_counter() - started) * 1000)
        run.step_end(step, "error", err.message)
        return {"id": model.id, "label": label, "ok": False, "ms": ms, "text": "", "error": err.message}
    ms = int((time.perf_counter() - started) * 1000)
    run.step_end(step, "done" if text else "error", f"answered in {ms / 1000:.1f} s" if text else "Empty answer")
    if local and text:
        lifecycle.mark_warm(model.name)
    return {"id": model.id, "label": label, "ok": bool(text), "ms": ms, "text": text}


async def _merge(run: AgentRun, question: str, candidates: list[dict[str, Any]], out: list[str]) -> None:
    """Stream the lead model's merge of the candidates (tagged so the SSE mapper forwards its tokens) into `out`,
    so whatever already reached the client is known if the stream breaks."""
    lead = run.model
    system = prompts.finance_system_prompt(run.intent, len(run.registry) > 0, [], []) + "\n\n" + MERGE_INSTRUCTION
    context = run.registry.render(max(2_000, lead.prompt_budget * 2))
    blocks = "\n\n".join(f"### Candidate {i}\n{c['text']}" for i, c in enumerate(candidates, 1))
    user = f"Question: {question}\n\n---\nSources:\n{context}\n\n---\nCandidate answers:\n\n{blocks}"
    llm = chat_model(lead, effort=run.turn.effort, reasoning=False).with_config(tags=[MERGE_TAG])
    think = ThinkFilter()
    async for chunk in llm.astream([SystemMessage(content=system), HumanMessage(content=user)]):
        raw = chunk.content if isinstance(chunk.content, str) else "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in chunk.content)
        if raw:
            out.append(think.feed(raw))
    out.append(think.flush())


async def ensemble(state: FinState) -> dict[str, Any]:
    run = attach(state)
    question = state.get("question") or run.turn.question
    members: list[str] = list(run.model.extra.get("ensemble") or [])
    lead_id = run.model.extra.get("lead") or (members[0] if members else run.model.id)
    lead_text = (state.get("draft") or "").strip()
    run.phase("thinking", f"Asking {len(members)} models")
    overall = run.step_start("ensemble", f"Asking {len(members)} models")
    lead_label = f"{registry.PROVIDER_LABELS.get(run.model.provider, run.model.provider)} · {model_label(run.model)}"
    lead_step = run.step_start("ensemble_member", lead_label)
    run.step_end(lead_step, "done" if lead_text else "error", "answered with the tools" if lead_text else "Empty")
    results = [{"id": lead_id, "label": lead_label, "ok": bool(lead_text), "ms": 0, "text": lead_text}]
    others = [m for m in members if m != lead_id]
    results += await asyncio.gather(*(_ask(run, m, question) for m in others))
    candidates = [r for r in results if r["ok"]]
    run.step_end(overall, "done", f"{len(candidates)} of {len(results)} answered")
    run.meta_extra["ensemble"] = {"lead": lead_id, "members": [
        {"id": r["id"], "label": r["label"], "ms": r["ms"], "ok": r["ok"]} for r in results]}

    if len(candidates) <= 1:
        final = candidates[0]["text"] if candidates else lead_text
        if final:
            run.emit("delta", {"text": separator("", final)})
        run.content = final
        return {"draft": final, "steps": run.steps}

    step = run.step_start("ensemble_merge", "Merging the answers")
    run.phase("composing", "Merging the answers")
    run.emit("_round", {"tools": False, "draft": ""})  # the mapper streams the merge like a normal round
    parts: list[str] = []
    try:
        await _merge(run, question, candidates, parts)
    except Exception as exc:  # noqa: BLE001 — keep what streamed, else fall back to the lead's answer
        log.info("ensemble merge failed: %s", exc)
    merged = "".join(parts).strip()
    if not merged:
        merged = candidates[0]["text"]
        run.emit("delta", {"text": separator("", merged)})
        run.step_end(step, "error", "Merge failed; showing the lead model's answer")
    else:
        run.step_end(step, "done", f"merged {len(candidates)} answers")
    run.content = merged
    return {"draft": merged, "steps": run.steps}
