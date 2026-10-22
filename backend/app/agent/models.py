"""LangChain chat models for the finance graph, provider error mapping and fail-over candidates.

Groq / Gemini / Ollama use their native LangChain integrations; the mock and LM Studio go through the existing
OpenAI-compatible registry (`app.llm.registry`) wrapped as a `BaseChatModel`, so the deterministic mock drives
the whole graph in tests and `registry.chat_stream` stays monkeypatchable.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import openai
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.messages.tool import ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.core.config import REPO_DIR, settings
from app.llm import registry
from app.llm.catalog import KEY_ENV, PROVIDER_LABELS, local_label, local_rank
from app.llm.errors import map_error
from app.llm.local import base_url as local_base_url
from app.llm.think import ThinkFilter
from app.llm.types import LLMError, ResolvedModel

log = logging.getLogger("sphura.agent.models")

GPU_BUSY_FLAG = REPO_DIR / "training" / "GPU_BUSY"
KEEP_ALIVE = "45m"
LOCAL_NUM_CTX = 8192
LOCAL_TIMEOUT_S = 180.0      # generous: a cold 4B model can take > 2 minutes to its first token
LOCAL_CONNECT_S = 5.0
CLOUD_TIMEOUT_S = 30.0       # an overloaded cloud model fails over instead of holding the answer
REASONING = {"fast": "low", "balanced": "medium", "deep": "high"}
TEMPERATURE = 0.2


def gpu_busy() -> bool:
    """True while the training engineer's GPU job owns the card (training/GPU_BUSY exists)."""
    return GPU_BUSY_FLAG.exists()


def native_ollama_base() -> str:
    """Ollama's native API root (the configured URL without the /v1 OpenAI shim)."""
    url = local_base_url("ollama")
    return url[:-3] if url.endswith("/v1") else url


def model_label(m: ResolvedModel) -> str:
    return local_label(m.name)[0] if m.provider == "ollama" else m.label


# ── message conversion for the OpenAI-compatible registry ────────────────────
def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


def to_openai_messages(messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            out.append({"role": "system", "content": _text(m.content)})
        elif isinstance(m, HumanMessage):
            out.append({"role": "user", "content": _text(m.content)})
        elif isinstance(m, ToolMessage):
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": _text(m.content)})
        elif isinstance(m, AIMessage):
            item: dict[str, Any] = {"role": "assistant", "content": _text(m.content)}
            if m.tool_calls:
                item["tool_calls"] = [{"id": c["id"] or f"call_{i}", "type": "function",
                                       "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                                      for i, c in enumerate(m.tool_calls)]
            out.append(item)
    return out


class RegistryChatModel(BaseChatModel):
    """`app.llm.registry` (mock, LM Studio) behind the LangChain chat-model interface."""

    resolved: Any
    temperature: float = TEMPERATURE
    reasoning_effort: str | None = None

    @property
    def _llm_type(self) -> str:
        return "sphura-registry"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable:
        return self.bind(tools=[convert_to_openai_tool(t) for t in tools], **kwargs)

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("RegistryChatModel is async-only; use ainvoke / astream")

    async def _agenerate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                         run_manager: AsyncCallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        text = await registry.complete(self.resolved, to_openai_messages(messages), temperature=self.temperature,
                                       timeout=float(kwargs.get("timeout") or 30.0))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    async def _astream(self, messages: list[BaseMessage], stop: list[str] | None = None,
                       run_manager: AsyncCallbackManagerForLLMRun | None = None,
                       **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        tools = kwargs.get("tools") or None
        async for item in registry.chat_stream(self.resolved, to_openai_messages(messages), tools=tools,
                                               temperature=self.temperature, reasoning_effort=self.reasoning_effort):
            if item.kind == "text" and item.text:
                chunk = ChatGenerationChunk(message=AIMessageChunk(content=item.text))
            elif item.kind == "tool_calls":
                calls = [ToolCallChunk(name=c.name, args=c.arguments, id=c.id, index=i)
                         for i, c in enumerate(item.tool_calls)]
                chunk = ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=calls))
            elif item.kind == "usage" and item.usage:
                usage = UsageMetadata(input_tokens=int(item.usage.get("promptTokens", 0)),
                                      output_tokens=int(item.usage.get("completionTokens", 0)),
                                      total_tokens=int(item.usage.get("promptTokens", 0))
                                      + int(item.usage.get("completionTokens", 0)))
                chunk = ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=usage))
            else:
                continue
            if run_manager is not None:
                await run_manager.on_llm_new_token(chunk.text, chunk=chunk)
            yield chunk


# ── factory ──────────────────────────────────────────────────────────────────
def chat_model(m: ResolvedModel, *, effort: str = "balanced", reasoning: bool | None = False,
               temperature: float = TEMPERATURE, streaming: bool = True) -> BaseChatModel:
    """A LangChain chat model for a resolved Sphura model id (`reasoning=False` turns thinking off locally;
    `streaming=False` makes `ainvoke` use the one-shot completion path, e.g. titles and classification)."""
    common: dict[str, Any] = {"disable_streaming": not streaming}
    if m.provider == "groq":
        from langchain_groq import ChatGroq

        kwargs: dict[str, Any] = {"model": m.name, "api_key": settings.groq_api_key, "temperature": temperature,
                                  "max_retries": 0, "timeout": CLOUD_TIMEOUT_S, "streaming": streaming, **common}
        if settings.groq_base_url:
            # ChatGroq appends /openai/v1 itself; the setting is the OpenAI-compatible URL (used for voice / registry)
            kwargs["base_url"] = settings.groq_base_url.rstrip("/").removesuffix("/openai/v1")
        if m.reasoning:
            kwargs["reasoning_effort"] = REASONING.get(effort, "medium")
        return ChatGroq(**kwargs)
    if m.provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=m.name, google_api_key=settings.gemini_api_key, temperature=temperature,
                                      max_retries=0, timeout=CLOUD_TIMEOUT_S,
                                      thinking_level=gemini_thinking(m.name, effort, bool(reasoning)), **common)
    if m.provider == "ollama":
        from langchain_ollama import ChatOllama

        timeout = httpx.Timeout(LOCAL_TIMEOUT_S, connect=LOCAL_CONNECT_S)
        return ChatOllama(model=m.name, base_url=native_ollama_base(), temperature=temperature,
                          keep_alive=KEEP_ALIVE, num_ctx=LOCAL_NUM_CTX, reasoning=reasoning,
                          client_kwargs={"timeout": timeout}, async_client_kwargs={"timeout": timeout}, **common)
    return RegistryChatModel(resolved=m, temperature=temperature,
                             reasoning_effort=REASONING.get(effort) if m.reasoning else None, **common)


def gemini_thinking(name: str, effort: str, reasoning: bool) -> str:
    """Gemini 3 thinks by default (2-3 s before the first token on Flash-Lite): "minimal" unless deep effort asks
    for reasoning. Pro models have no "minimal" level, so they get "low"."""
    if reasoning:
        return "high" if effort == "deep" else "low"
    return "low" if "pro" in name else "minimal"


# ── errors ───────────────────────────────────────────────────────────────────
def _status_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    return code if isinstance(code, int) else None


def _detail(exc: BaseException) -> str:
    text = str(getattr(exc, "message", None) or exc or "").strip().replace("\n", " ")
    return text[:200]


def to_llm_error(exc: BaseException, provider: str, model: str) -> LLMError:
    """Map any provider SDK exception (openai, groq, google-genai, ollama, httpx) to a short LLMError."""
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, openai.OpenAIError):
        return map_error(exc, provider, model)  # type: ignore[arg-type]
    label = PROVIDER_LABELS.get(provider, provider)
    local = provider in ("ollama", "lmstudio")
    name = type(exc).__name__
    detail = _detail(exc)
    low = detail.lower()
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)) or "Timeout" in name:
        return LLMError(f"{label} took too long to respond. Try again or pick a faster model.", "timeout")
    status = _status_of(exc)
    if status is None and ("connect" in name.lower() or isinstance(exc, (ConnectionError, httpx.TransportError))
                           or "connection" in low):
        if local:
            hint = "Start Ollama (`ollama serve`)" if provider == "ollama" else "Start the LM Studio local server"
            return LLMError(f"{label} isn't running on {local_base_url(provider)}. {hint}.", "connection")
        return LLMError(f"Couldn't reach {label}. Check your internet connection.", "connection")
    if status is not None:
        if status in (401, 403):
            env = KEY_ENV.get(provider)
            fix = f" Check {env} in .env." if env else ""
            return LLMError(f"{label} rejected the API key.{fix}", "auth", status)
        if status == 413 or "request too large" in low or "context length" in low or "context_length" in low:
            return LLMError(f"The request is too large for {label} ({model}). Try a shorter question, fewer "
                            "documents or another model.", "too_large", status)
        if status == 429 or "rate limit" in low or "resource_exhausted" in low or "quota" in low:
            return LLMError(f"{label} rate limit reached for {model}. Wait a minute or pick another model.",
                            "rate_limit", status)
        if status == 404 or "not found" in low or "does not exist" in low:
            if provider == "ollama":
                return LLMError(f"Model '{model}' isn't installed in Ollama. Run `ollama pull {model}`.",
                                "not_found", status)
            return LLMError(f"Model '{model}' isn't available on {label}.", "not_found", status)
        if status == 400 and ("tool" in low or "function" in low):
            return LLMError(f"{label} couldn't use tools with {model}: {detail}", "tools", status)
        if status >= 500:
            return LLMError(f"{label} is having trouble right now (HTTP {status}). Try again shortly.",
                            "server", status)
        return LLMError(f"{label} rejected the request: {detail or f'HTTP {status}'}", "bad_request", status)
    if "tool" in low and ("support" in low or "not" in low):
        return LLMError(f"{label} couldn't use tools with {model}: {detail}", "tools")
    if "rate limit" in low:
        return LLMError(f"{label} rate limit reached for {model}. Wait a minute or pick another model.", "rate_limit")
    return LLMError(f"Unexpected error from {label}: {name}", "unknown")


def can_fail_over(err: LLMError, provider: str | None = None) -> bool:
    """Real provider errors (auth, rate limit, connection, HTTP 5xx, missing model) always; a timeout only for a
    cloud model (an overloaded Gemini answers 504 after a minute), never for a local one that is still loading."""
    if err.kind == "timeout":
        return provider is not None and provider not in ("ollama", "lmstudio")
    return err.kind in {"auth", "rate_limit", "connection", "server", "not_found", "unavailable", "too_large"}


def fallback_candidates(current_id: str, kind: str) -> list[str]:
    """Groq ⇄ Gemini → local: other available models worth trying after `current_id` failed (never the mock)."""
    ids = registry.fallback_models(current_id, kind)
    cloud = [i for i in ids if i.split(":", 1)[0] in KEY_ENV]
    local = [i for i in ids if i.split(":", 1)[0] not in KEY_ENV]
    if gpu_busy():
        return cloud
    from app.agent.lifecycle import warm_model  # lazy: lifecycle imports this module

    warm = warm_model()
    # the model the warm-up keeps resident first (no 3 GB reload), then sphura-fin → qwen3.5 → nemotron → others
    local.sort(key=lambda i: (i.split(":", 1)[1] != warm if i.startswith("ollama:") else True,
                              local_rank(i.split(":", 1)[1]) if i.startswith("ollama:") else 99))
    return cloud + local


def strip_thinking(text: str) -> str:
    think = ThinkFilter()
    return (think.feed(text) + think.flush()).strip()
