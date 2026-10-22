"""Tiny stdlib HTTP client for the local Ollama server and the Gemini REST API (export smoke test + eval judge).

The training venv has no `httpx` (only `httpx2`, pulled in by `datasets`), so this uses `urllib.request` and
adds no dependency. Keys are read from the environment and never logged.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def post_json(url: str, body: dict[str, Any], timeout: float = 300, headers: dict[str, str] | None = None) -> dict:
    """POST `body` as JSON and return the decoded JSON reply; raises RuntimeError with the status on HTTP errors."""
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from None


def ollama_chat(model: str, messages: list[dict], num_predict: int = 16, temperature: float = 0.0,
                timeout: float = 300) -> dict:
    """One non-streaming /api/chat call with thinking off; returns Ollama's JSON reply."""
    body = {"model": model, "stream": False, "think": False, "messages": messages,
            "options": {"temperature": temperature, "num_predict": num_predict}}
    return post_json(f"{OLLAMA_URL}/api/chat", body, timeout=timeout)


def gemini_chat(model: str, messages: list[dict], num_predict: int = 16, timeout: float = 120) -> str:
    """system + user messages → Gemini generateContent text (temperature 0)."""
    key = os.environ["GEMINI_API_KEY"]
    body = {"systemInstruction": {"parts": [{"text": messages[0]["content"]}]},
            "contents": [{"role": "user", "parts": [{"text": m["content"]}]} for m in messages[1:]],
            "generationConfig": {"temperature": 0, "maxOutputTokens": num_predict}}
    data = post_json(GEMINI_URL.format(model=model), body, timeout=timeout, headers={"x-goog-api-key": key})
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
