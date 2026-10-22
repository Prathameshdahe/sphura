"""draft: the chat model writes (or asks for tools) over the gathered context; streams tokens.

The text the user sees is decided by `RoundBuffer`, shared with the SSE mapper (app/agent/stream.py) so that
`state["draft"]` and the streamed deltas are identical: in a tool round, text is held back until it is clearly
an answer (≥ LIVE_AFTER_CHARS without a tool call) and a preamble that ends in tool calls is dropped.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage

from app.agent import adapters, prompts
from app.agent.models import can_fail_over, chat_model, fallback_candidates, model_label, to_llm_error
from app.agent.run import AgentRun, attach
from app.agent.state import FinState
from app.agent.tools import tools_for
from app.llm import registry
from app.llm.think import ThinkFilter
from app.llm.types import LLMError

log = logging.getLogger("sphura.agent.draft")

MAX_ROUNDS = {"fast": 1, "balanced": 3, "deep": 6}
LIVE_AFTER_CHARS = 150
MAX_ATTEMPTS = 4   # Groq free-tier limits are tight: sibling model → Gemini → local before giving up
LOCAL_PROVIDERS = ("ollama", "lmstudio")
WRITING = "Writing the answer"
LOADING = "Loading local model"
SLOW_NOTICE_S = 10.0   # no token yet after this long on a local model: say why the wait is long
SLOW_LABEL = "Loading local model (the first reply can take a minute)"
THINKING = "Thinking it through"


class RoundBuffer:
    """Which streamed text becomes part of the answer this round (see the module docstring)."""

    def __init__(self, tools_bound: bool) -> None:
        self.live = not tools_bound
        self.saw_tool = False
        self.buffer = ""
        self.think = ThinkFilter()

    def feed(self, chunk: AIMessageChunk) -> str:
        """Text to release now for one streamed chunk."""
        if chunk.tool_call_chunks:
            self.saw_tool = True
        raw = chunk.content if isinstance(chunk.content, str) else "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in chunk.content)
        text = self.think.feed(raw) if raw else ""
        if not text:
            return ""
        if self.live:
            return text
        self.buffer += text
        if not self.saw_tool and len(self.buffer) >= LIVE_AFTER_CHARS:
            self.live, out, self.buffer = True, self.buffer, ""
            return out
        return ""

    def finish(self, has_tool_calls: bool) -> str:
        """Text to release when the model's turn ends (a preamble before tool calls is dropped)."""
        rest = self.think.flush()
        if has_tool_calls:
            self.buffer = ""
            return ""
        out, self.buffer = self.buffer + rest, ""
        return out


def join_answer(so_far: str, text: str) -> str:
    """Append a round's text to the answer (rounds are separated by a blank line)."""
    if not text:
        return so_far
    if so_far.strip():
        return so_far + ("\n\n" + text.lstrip() if not so_far.endswith("\n\n") else text.lstrip())
    return so_far + text


def separator(so_far: str, text: str) -> str:
    """The delta the client must receive so that its content equals `join_answer(so_far, text)`."""
    if not text:
        return ""
    if so_far.strip() and not so_far.endswith("\n\n"):
        return "\n\n" + text.lstrip()
    return text.lstrip() if so_far.strip() else text


def _round_messages(state: FinState) -> list[BaseMessage]:
    """This turn's AI / tool messages so far (after the user's message)."""
    rounds: list[BaseMessage] = []
    for m in reversed(state.get("messages") or []):
        if isinstance(m, HumanMessage):
            break
        rounds.append(m)
    rounds.reverse()
    return rounds


def build_messages(run: AgentRun, state: FinState, tools: list[Any]) -> list[BaseMessage]:
    budget = run.model.prompt_budget
    names = [t.name for t in tools]
    system = prompts.finance_system_prompt(run.intent, len(run.registry) > 0, names, run.extra_system)
    question = state.get("question") or run.turn.question
    tool_cost = prompts.estimate_tokens(json.dumps([t.args_schema.model_json_schema() if t.args_schema else {}
                                                    for t in tools])) if tools else 0
    fixed = prompts.estimate_tokens(system) + prompts.estimate_tokens(question) + 200 + tool_cost
    history_budget = max(0, min(12_000, int(budget * 0.3), budget - fixed - 600))
    history = prompts.trim_history(run.turn.history, history_budget)
    used = fixed + sum(prompts.estimate_tokens(h["content"]) for h in history)
    context = run.registry.render(max(1_200, (budget - used) * 4))
    turn = prompts.user_turn(question, context, run.searches, run.notes)
    messages: list[BaseMessage] = [SystemMessage(content=system)]
    for h in prompts.normalise_turns(history):
        messages.append(HumanMessage(content=h["content"]) if h["role"] == "user" else AIMessage(content=h["content"]))
    messages.append(HumanMessage(content=turn))
    messages.extend(_round_messages(state))
    return messages


async def _failover(run: AgentRun, err: LLMError) -> bool:
    candidates = await asyncio.to_thread(fallback_candidates, run.model.id, err.kind)
    tried = {run.model.id, *run.fallbacks}  # never bounce back to a model that already failed this turn
    for candidate in (c for c in candidates if c not in tried):
        try:
            nxt = registry.resolve_model(candidate)
        except LLMError:
            continue
        step = run.step_start("switch_model", f"Switching to {model_label(nxt)}")
        run.step_end(step, "done", err.message)
        run.fallbacks.append(run.model.id)
        run.model = nxt
        run.phase("thinking", f"Retrying with {model_label(nxt)}")
        return True
    return False


def waiting_label(run: AgentRun) -> str:
    """"Loading local model" unless this Ollama model is known to be resident (warm-up or a recent answer)."""
    if run.model.provider == "ollama":
        from app.agent import lifecycle

        if not lifecycle.is_warm(run.model.name):
            return LOADING
    return WRITING


async def _slow_notice(run: AgentRun) -> None:
    await asyncio.sleep(SLOW_NOTICE_S)
    run.phase("composing", SLOW_LABEL)


def _to_message(full: AIMessageChunk) -> AIMessage:
    return AIMessage(content=full.content, tool_calls=[c for c in full.tool_calls if c.get("name")],
                     id=full.id, usage_metadata=full.usage_metadata, response_metadata=full.response_metadata)


async def draft(state: FinState) -> dict[str, Any]:
    run = attach(state)
    rounds = int(state.get("tool_rounds") or 0)
    if rounds == 0:
        await adapters.memory_before(run)
        run.docs_ready = await asyncio.to_thread(adapters.has_ready_documents, run.turn.user_id, run.turn.doc_ids)
        if run.intent in ("explain", "advice"):
            from app.agent.nodes.tools import pre_calculate

            await pre_calculate(run, state.get("question") or run.turn.question)
    use_tools = rounds < MAX_ROUNDS.get(run.turn.effort, 3) and run.model.supports_tools and run.tools_ok
    tools = tools_for(run.intent, run.docs_ready) if use_tools else []
    run.phase("composing", waiting_label(run))
    # Sphura Ensemble: the lead's own text is only a candidate for the merge, so the client is not shown it
    hidden = len(run.model.extra.get("ensemble") or []) > 1
    run.emit("_round", {"tools": bool(tools), "draft": state.get("draft") or "", "hidden": hidden})

    attempts = 0
    reasoning = run.turn.effort == "deep"
    while True:
        messages = build_messages(run, state, tools)
        model = chat_model(run.model, effort=run.turn.effort, reasoning=reasoning)
        if tools:
            model = model.bind_tools(tools)
        buffer = RoundBuffer(bool(tools))
        full: AIMessageChunk | None = None
        released = ""
        started = False
        # Local generation is never failed over for slowness (a cold load takes minutes); the user is told instead.
        notice = asyncio.create_task(_slow_notice(run)) if run.model.provider in LOCAL_PROVIDERS else None
        try:
            async for chunk in model.astream(messages):
                if not isinstance(chunk, AIMessageChunk):
                    continue
                if not started and chunk.additional_kwargs.get("reasoning_content"):
                    if notice is not None:  # deep effort: the model is thinking, not loading
                        notice.cancel()
                    run.phase("thinking", THINKING)
                if not started and (chunk.content or chunk.tool_call_chunks):
                    started = True
                    if notice is not None:
                        notice.cancel()
                    run.phase("composing", WRITING)
                full = chunk if full is None else full + chunk
                released += buffer.feed(chunk)
        except Exception as exc:  # noqa: BLE001
            err = to_llm_error(exc, run.model.provider, run.model.name)
            if started or attempts >= MAX_ATTEMPTS:
                raise err from exc
            if err.kind == "tools" and tools:
                log.info("tools disabled for %s: %s", run.model.id, err.message)
                run.tools_ok, tools = False, []
                continue
            if reasoning and "think" in f"{exc} {err.message}".lower():
                # e.g. Ollama: '"sphura-fin-1.7b" does not support thinking' (deep effort on a non-thinking model)
                log.info("thinking disabled for %s: %s", run.model.id, err.message)
                reasoning = False
                continue
            if not can_fail_over(err, run.model.provider) or not await _failover(run, err):
                raise err from exc
            attempts += 1
            continue
        finally:
            if notice is not None:
                notice.cancel()
        break

    if run.model.provider == "ollama":
        from app.agent import lifecycle

        lifecycle.mark_warm(run.model.name)

    if full is None:
        ai = AIMessage(content="")
    else:
        ai = _to_message(full)
        if not tools and ai.tool_calls:  # no tools were offered this round (budget spent): it must answer now
            log.info("ignoring %d tool call(s) from %s in a no-tools round", len(ai.tool_calls), run.model.id)
            ai = AIMessage(content=ai.content, id=ai.id, usage_metadata=ai.usage_metadata,
                           response_metadata=ai.response_metadata)
        if full.usage_metadata:
            run.usage["promptTokens"] += int(full.usage_metadata.get("input_tokens", 0) or 0)
            run.usage["completionTokens"] += int(full.usage_metadata.get("output_tokens", 0) or 0)
    released += buffer.finish(bool(ai.tool_calls))
    answer = join_answer(state.get("draft") or "", released)
    run.content = answer
    return {"messages": [ai], "tool_rounds": rounds + 1, "draft": answer, "sources": run.registry.sources(),
            "steps": run.steps, "memory_used": int(run.meta_extra.get("memoryUsed", 0) or 0)}
