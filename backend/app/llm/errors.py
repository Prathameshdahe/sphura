"""Map provider SDK exceptions to short, human messages."""
from __future__ import annotations

import openai

from app.llm.catalog import KEY_ENV, PROVIDER_LABELS
from app.llm.local import base_url
from app.llm.types import LLMError


def _detail(exc: openai.APIStatusError) -> str:
    body = exc.body if isinstance(exc.body, dict) else {}
    err = body.get("error", body) if isinstance(body, dict) else {}
    msg = err.get("message") if isinstance(err, dict) else None
    text = str(msg or exc.message or "").strip().replace("\n", " ")
    return text[:200]


def map_error(exc: Exception, provider: str, model: str) -> LLMError:
    label = PROVIDER_LABELS.get(provider, provider)
    local = provider in ("ollama", "lmstudio")
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, openai.APITimeoutError):
        return LLMError(f"{label} took too long to respond. Try again or pick a faster model.", "timeout")
    if isinstance(exc, openai.APIConnectionError):
        if local:
            hint = "Start Ollama (`ollama serve`)" if provider == "ollama" else "Start the LM Studio local server"
            return LLMError(f"{label} isn't running on {base_url(provider)}. {hint}.", "connection")
        return LLMError(f"Couldn't reach {label}. Check your internet connection.", "connection")
    if isinstance(exc, openai.APIStatusError):
        status, detail = exc.status_code, _detail(exc)
        low = detail.lower()
        if status in (401, 403):
            env = KEY_ENV.get(provider)
            fix = f" Check {env} in .env." if env else ""
            return LLMError(f"{label} rejected the API key.{fix}", "auth", status)
        if status == 413 or "request too large" in low or "context length" in low or "context_length" in low:
            return LLMError(f"The request is too large for {label} ({model}). Try a shorter question, fewer "
                            "documents or another model.", "too_large", status)
        if status == 429:
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
    if isinstance(exc, openai.APIError):  # error event inside an otherwise successful stream
        detail = str(exc.message or "").strip().replace("\n", " ")[:200]
        if "tool" in detail.lower() or "function" in detail.lower():
            return LLMError(f"{label} couldn't use tools with {model}: {detail}", "tools")
        if "rate limit" in detail.lower():
            return LLMError(f"{label} rate limit reached for {model}. Wait a minute or pick another model.",
                            "rate_limit")
        return LLMError(f"{label} stopped with an error: {detail or 'unknown error'}", "server")
    return LLMError(f"Unexpected error from {label}: {type(exc).__name__}", "unknown")
