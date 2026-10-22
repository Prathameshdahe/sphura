"""Provider registry over OpenAI-compatible Chat Completions (Gemini, Groq, Ollama, LM Studio, mock).

Model ids are "<provider>:<model>", split on the first colon.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI

from app.core.config import settings
from app.llm import mock
from app.llm.catalog import (CLOUD_MODELS, ENSEMBLE_ID, KEY_ENV, PROMPT_BUDGET, PROVIDER_LABELS,
                              find_cloud_model, preferred_local)
from app.llm.errors import map_error
from app.llm.local import LOCAL_PROVIDERS, discover_all, guess_tools, guess_vision, pretty_label
from app.llm.local import base_url as local_base_url
from app.llm.local import prime as _prime_local_discovery
from app.llm.think import ThinkFilter
from app.llm.types import LLMChunk, LLMError, ResolvedModel, ToolCall
from app.schemas import ModelInfo

log = logging.getLogger("sphura.llm")

PROVIDERS = ("gemini", "groq", "nvidia", "ollama", "lmstudio", "mock", "ensemble")
_DEFAULT_ORDER = ("ensemble", "groq", "nvidia", "gemini", "ollama", "lmstudio", "mock")
_LOCAL_HINT = {
    "ollama": ("qwen2.5:7b", "Start Ollama and pull a model: `ollama pull qwen2.5:7b`",
               "No chat models in Ollama yet: run `ollama pull qwen2.5:7b`"),
    "lmstudio": ("local-model", "Start the LM Studio local server (Developer tab, port 1234)",
                 "Load a chat model in LM Studio"),
}
_clients: dict[tuple, AsyncOpenAI] = {}
_prime_local_discovery()


# ── catalogue ────────────────────────────────────────────────────────────────
def _api_key(provider: str) -> str:
    return {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key,
            "nvidia": settings.nvidia_api_key}.get(provider, "")


def nvidia_thinking(enabled: bool) -> dict[str, Any]:
    """Nemotron models (only) think before answering unless the chat template is told not to; only deep effort keeps it
    (its thoughts arrive as `reasoning_content`, which the answer stream ignores)."""
    return {"chat_template_kwargs": {"enable_thinking": enabled}}


def _base(provider: str) -> str:
    if provider in LOCAL_PROVIDERS:
        return local_base_url(provider)
    return {"gemini": settings.gemini_base_url, "nvidia": settings.nvidia_base_url}.get(provider, settings.groq_base_url)


def _mock_info() -> ModelInfo:
    return ModelInfo(id=f"mock:{mock.MOCK_NAME}", provider="mock", label="Sphura Mock",
                     description="Offline test model", available=True, supports_tools=True)


def _local_info(provider: str, name: str, available: bool = True, reason: str | None = None) -> ModelInfo:
    label = PROVIDER_LABELS[provider]
    return ModelInfo(
        id=f"{provider}:{name}", provider=provider, label=pretty_label(name) if available else f"{label} (local)",
        description=f"{label} · local" if available else f"{label} · offline", available=available, reason=reason,
        supports_tools=guess_tools(provider, name), supports_vision=guess_vision(name),
    )


def _cloud_info(provider: str, name: str) -> ModelInfo:
    cat = find_cloud_model(provider, name)
    has_key = bool(_api_key(provider))
    return ModelInfo(
        id=f"{provider}:{name}", provider=provider, label=cat.label if cat else pretty_label(name),
        description=cat.description if cat else PROVIDER_LABELS[provider], available=has_key,
        reason=None if has_key else f"Add {KEY_ENV[provider]} to .env",
        supports_tools=cat.supports_tools if cat else True, supports_vision=cat.supports_vision if cat else False,
    )


def _curated_local() -> ModelInfo:
    """LOCAL_MODEL when Ollama has it, else the preferred installed model, else a hint to start Ollama."""
    status = discover_all()["ollama"]
    if status.reachable and status.models:
        wanted = settings.local_model.strip()
        names = status.models
        name = next((n for n in names if n == wanted or n == f"{wanted}:latest"), None) or preferred_local(names)
        return _local_info("ollama", name)
    placeholder, offline, empty = _LOCAL_HINT["ollama"]
    return _local_info("ollama", placeholder, False, empty if status.reachable else offline)


def ensemble_info(members: list[ModelInfo]) -> ModelInfo:
    ready = [m for m in members if m.available]
    names = " + ".join(PROVIDER_LABELS[m.provider] if m.provider != "ollama" else "local" for m in members)
    return ModelInfo(
        id=ENSEMBLE_ID, provider="ensemble", label="Sphura Ensemble",
        description=f"{names}, answers merged", available=bool(ready),
        reason=None if ready else "No model is available yet", supports_tools=True, supports_vision=False,
    )


def _curated_models() -> list[ModelInfo]:
    members = [_cloud_info("groq", settings.groq_model), _cloud_info("nvidia", settings.nvidia_model),
               _curated_local()]
    out = [ensemble_info(members), *members]
    if settings.sphura_enable_mock:
        out.append(_mock_info())
    return out


def ensemble_members() -> list[str]:
    """The available ensemble members, lead first (Groq → NVIDIA → local)."""
    return [m.id for m in _curated_models()[1:4] if m.available and m.provider != "mock"]


def _all_models() -> list[ModelInfo]:
    if settings.curated_models:
        return _curated_models()
    out: list[ModelInfo] = []
    for m in CLOUD_MODELS:
        has_key = bool(_api_key(m.provider))
        out.append(ModelInfo(
            id=f"{m.provider}:{m.name}", provider=m.provider, label=m.label, description=m.description,
            available=has_key, reason=None if has_key else f"Add {KEY_ENV[m.provider]} to .env",
            supports_tools=m.supports_tools, supports_vision=m.supports_vision,
        ))
    local = discover_all()
    for provider in LOCAL_PROVIDERS:
        status = local[provider]
        if status.reachable and status.models:
            out.extend(_local_info(provider, name) for name in status.models)
        elif provider == "ollama":  # the picker hints how to start Ollama; an unused LM Studio is left out
            placeholder, offline, empty = _LOCAL_HINT[provider]
            out.append(_local_info(provider, placeholder, False, empty if status.reachable else offline))
    if settings.sphura_enable_mock:
        out.append(_mock_info())
    return out


def _pick_default(models: list[ModelInfo]) -> str | None:
    available = [m for m in models if m.available]
    wanted = settings.default_model.strip()
    if wanted:
        if any(m.id == wanted for m in available):
            return wanted
        provider = wanted.split(":", 1)[0]
        if provider in KEY_ENV and _api_key(provider) and not any(m.id == wanted for m in models):
            return wanted  # an uncatalogued cloud model the user asked for explicitly
    for provider in _DEFAULT_ORDER:
        first = next((m for m in available if m.provider == provider), None)
        if first:
            return first.id
    return None


def list_models() -> list[ModelInfo]:
    """Every known model with availability. Blocking (≤1.5 s, cached 30 s): use to_thread from async code."""
    models = _all_models()
    default = _pick_default(models)
    if default and not any(m.id == default for m in models):
        provider, _, name = default.partition(":")
        models.insert(0, ModelInfo(id=default, provider=provider, label=name, description=PROVIDER_LABELS[provider],
                                   available=True))
    for m in models:
        m.is_default = m.id == default
    return models


def provider_status() -> dict[str, bool]:
    local = discover_all()
    return {
        "gemini": bool(settings.gemini_api_key),
        "groq": bool(settings.groq_api_key),
        "nvidia": bool(settings.nvidia_api_key),
        "ollama": local["ollama"].reachable,
        "lmstudio": local["lmstudio"].reachable,
    }


def resolve_model(model_id: str | None) -> ResolvedModel:
    """Validate a model id (None → server default). Explicit ids never touch the network."""
    if not model_id:
        default = next((m for m in list_models() if m.is_default), None)
        if default is None:
            raise LLMError("No AI model is available yet. Add GROQ_API_KEY, NVIDIA_API_KEY or GEMINI_API_KEY to .env, "
                           "or start Ollama / LM Studio.", "unavailable")
        model_id = default.id
    provider, _, name = model_id.partition(":")
    if provider not in PROVIDERS or not name:
        raise LLMError(f"Unknown model '{model_id}'.", "not_found")
    if provider == "mock":
        if not settings.sphura_enable_mock:
            raise LLMError("The mock model is disabled.", "unavailable")
        return ResolvedModel(model_id, provider, name, _mock_info(), PROMPT_BUDGET["mock"])
    if provider == "ensemble":
        members = ensemble_members()
        if not members:
            raise LLMError("No AI model is available for the ensemble yet.", "unavailable")
        lead = resolve_model(members[0])
        info = ensemble_info([m for m in _curated_models()[1:4]])
        info.supports_tools = lead.supports_tools
        return ResolvedModel(ENSEMBLE_ID, lead.provider, lead.name, info, lead.prompt_budget,
                             reasoning=lead.reasoning, extra={"ensemble": members, "lead": lead.id})
    if provider in KEY_ENV:
        if not _api_key(provider):
            raise LLMError(f"Add {KEY_ENV[provider]} to .env to use {PROVIDER_LABELS[provider]} models.",
                           "unavailable")
        cat = find_cloud_model(provider, name)
        info = ModelInfo(
            id=model_id, provider=provider, label=cat.label if cat else name,
            description=cat.description if cat else PROVIDER_LABELS[provider], available=True,
            supports_tools=cat.supports_tools if cat else True,
            supports_vision=cat.supports_vision if cat else False,
        )
        return ResolvedModel(model_id, provider, name, info, PROMPT_BUDGET[provider],
                             reasoning=bool(cat and cat.reasoning))
    return ResolvedModel(model_id, provider, name, _local_info(provider, name), PROMPT_BUDGET[provider])


def fallback_models(current_id: str, kind: str) -> list[str]:
    """Other available models to try after `current_id` failed with an error of `kind`."""
    current = current_id.split(":", 1)[0]
    candidates = [m for m in list_models() if m.available and m.id != current_id
                  and m.provider not in ("mock", "ensemble")]
    same = [m.id for m in candidates if m.provider == current]
    other = [m.id for m in candidates if m.provider != current]
    if settings.nvidia_api_key:  # NVIDIA's backups (Lightning, then DeepSeek) are not in the curated picker
        backups = [f"nvidia:{n}" for n in (settings.nvidia_fast_model, settings.nvidia_fallback_model)
                   if n and f"nvidia:{n}" != current_id and f"nvidia:{n}" not in same + other]
        if current == "nvidia":
            same[:0] = backups
        else:
            other.extend(backups)
    # a rate limit is per model, so one sibling of the same provider is worth a try before switching provider
    return same[:1] + other + same[1:] if kind == "rate_limit" else other + same


# ── calls ────────────────────────────────────────────────────────────────────
def _client(provider: str) -> AsyncOpenAI:
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = 0
    key = (provider, _base(provider), _api_key(provider), loop_id)
    client = _clients.get(key)
    if client is None:
        local = provider in LOCAL_PROVIDERS
        client = AsyncOpenAI(
            api_key=_api_key(provider) or ("ollama" if provider == "ollama" else "lm-studio"),
            base_url=_base(provider),
            timeout=openai.Timeout(180.0 if local else 60.0, connect=3.0 if local else 8.0),
            max_retries=0,  # the agent fails over to another model instead of waiting
        )
        _clients[key] = client
    return client


def _as_model(model: str | ResolvedModel) -> ResolvedModel:
    return model if isinstance(model, ResolvedModel) else resolve_model(model)


_OPTIONAL_PARAMS = ("reasoning_effort", "stream_options")


async def _create(m: ResolvedModel, kwargs: dict[str, Any]) -> Any:
    """Call the provider; on a 400, retry once without the optional extras some endpoints reject."""
    client = _client(m.provider)
    try:
        return await client.chat.completions.create(**kwargs)
    except openai.BadRequestError as exc:
        if any(p in kwargs for p in _OPTIONAL_PARAMS):
            log.info("%s rejected optional params (%s); retrying without them", m.id, exc.message)
            kwargs = {k: v for k, v in kwargs.items() if k not in _OPTIONAL_PARAMS}
            try:
                return await client.chat.completions.create(**kwargs)
            except Exception as retry_exc:  # noqa: BLE001
                raise map_error(retry_exc, m.provider, m.name) from retry_exc
        raise map_error(exc, m.provider, m.name) from exc
    except Exception as exc:  # noqa: BLE001
        raise map_error(exc, m.provider, m.name) from exc


async def chat_stream(
    model_id: str | ResolvedModel,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.4,
    reasoning_effort: str | None = None,
) -> AsyncIterator[LLMChunk]:
    """Stream text deltas; tool calls are assembled and yielded once, followed by finish and usage."""
    m = _as_model(model_id)
    if m.provider == "mock":
        async for chunk in mock.stream(messages, tools):
            yield chunk
        return
    kwargs: dict[str, Any] = {"model": m.name, "messages": messages, "stream": True, "temperature": temperature}
    if tools:
        kwargs.update(tools=tools, tool_choice="auto")
    if m.provider == "groq":  # usage arrives in a final chunk; other endpoints vary in support
        kwargs["stream_options"] = {"include_usage": True}
    if m.provider == "nvidia" and "nemotron" in m.name:
        kwargs["extra_body"] = nvidia_thinking(reasoning_effort == "high")
    elif reasoning_effort and m.reasoning:
        kwargs["reasoning_effort"] = reasoning_effort
    stream = await _create(m, kwargs)

    calls: dict[int, dict[str, str]] = {}
    think = ThinkFilter()
    finish: str | None = None
    usage: dict[str, int] | None = None
    try:
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = {"promptTokens": chunk.usage.prompt_tokens or 0,
                         "completionTokens": chunk.usage.completion_tokens or 0}
            for choice in chunk.choices or []:
                delta = choice.delta
                if delta is not None and delta.content:
                    text = think.feed(delta.content)
                    if text:
                        yield LLMChunk(kind="text", text=text)
                if delta is not None and delta.tool_calls:
                    if not calls:
                        yield LLMChunk(kind="tool_call_started")
                    for tc in delta.tool_calls:
                        idx = tc.index if tc.index is not None else len(calls)
                        slot = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        slot["id"] = tc.id or slot["id"]
                        if tc.function is not None:
                            name = tc.function.name or ""
                            if name and name != slot["name"]:
                                slot["name"] = name if not slot["name"] else slot["name"] + name
                            slot["arguments"] += tc.function.arguments or ""
                if choice.finish_reason:
                    finish = choice.finish_reason
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise map_error(exc, m.provider, m.name) from exc
    finally:
        try:
            await stream.close()
        except Exception:  # noqa: BLE001
            pass
    rest = think.flush()
    if rest:
        yield LLMChunk(kind="text", text=rest)
    if calls:
        assembled = [ToolCall(id=c["id"] or f"call_{i}", name=c["name"], arguments=c["arguments"] or "{}")
                     for i, c in sorted(calls.items())]
        yield LLMChunk(kind="tool_calls", tool_calls=assembled)
    yield LLMChunk(kind="finish", finish_reason=finish or ("tool_calls" if calls else "stop"))
    if usage:
        yield LLMChunk(kind="usage", usage=usage)


async def complete(
    model_id: str | ResolvedModel,
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
    json_mode: bool = False,
    timeout: float = 30.0,
) -> str:
    """One-shot completion (titles, query rewriting). Raises LLMError."""
    m = _as_model(model_id)
    if m.provider == "mock":
        return mock.complete(messages, json_mode)
    kwargs: dict[str, Any] = {"model": m.name, "messages": messages, "temperature": temperature,
                              "timeout": timeout}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if m.provider == "nvidia" and "nemotron" in m.name:
        kwargs["extra_body"] = nvidia_thinking(False)
    elif m.reasoning:
        kwargs["reasoning_effort"] = "low"
    resp = await _create(m, kwargs)
    text = (resp.choices[0].message.content or "") if resp.choices else ""
    think = ThinkFilter()
    return (think.feed(text) + think.flush()).strip()
