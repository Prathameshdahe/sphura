"""Discovery of models served by local OpenAI-compatible servers (Ollama, LM Studio)."""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.config import settings

LOCAL_PROVIDERS = ("ollama", "lmstudio")
_TTL_S = 30.0
_TIMEOUT_S = 1.5
_EMBEDDING = re.compile(r"embed|bge-|minilm|e5-|gte-|rerank|nomic-bert", re.I)
_VISION = re.compile(r"llava|vision|-vl\b|vl:|gemma3|minicpm-v|moondream|qwen2\.5vl|llama4", re.I)
# sphura-fin: our QLoRA export has no tool template (tool calls come back as plain text)
_NO_TOOLS = re.compile(r"gemma|phi[23]|tinyllama|codellama|deepseek-r1|llava|starcoder|orca|sphura-fin", re.I)


@dataclass
class LocalStatus:
    reachable: bool
    models: list[str] = field(default_factory=list)
    error: str | None = None


_cache: dict[str, tuple[float, LocalStatus]] = {}
_lock = threading.Lock()
_refreshing = False


def base_url(provider: str) -> str:
    """Configured base URL; "localhost" becomes 127.0.0.1 because on Windows the IPv6 (::1) attempt that
    "localhost" makes first costs ~2 s per new connection when the server only listens on IPv4."""
    url = (settings.ollama_base_url if provider == "ollama" else settings.lmstudio_base_url).rstrip("/")
    parts = urlsplit(url)
    if parts.hostname == "localhost":
        netloc = "127.0.0.1" + (f":{parts.port}" if parts.port else "")
        url = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return url


def _probe(provider: str) -> LocalStatus:
    try:
        r = httpx.get(f"{base_url(provider)}/models", timeout=_TIMEOUT_S)
        r.raise_for_status()
        data = r.json().get("data") or []
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        return LocalStatus(reachable=False, error=type(exc).__name__)
    ids = [str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id")]
    return LocalStatus(reachable=True, models=[i for i in ids if not _EMBEDDING.search(i)])


def _refresh(providers: list[str]) -> None:
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        for provider, status in zip(providers, pool.map(_probe, providers)):
            _cache[provider] = (time.monotonic(), status)


def _refresh_in_background(providers: list[str]) -> None:
    global _refreshing
    try:
        _refresh(providers)
    finally:
        _refreshing = False


def discover_all(force: bool = False) -> dict[str, LocalStatus]:
    """Status of every local provider, probed in parallel. Cached for 30 s; after that the stale value is
    served while a background refresh runs, so only the very first call (or `force`) waits on the network."""
    global _refreshing
    now = time.monotonic()
    with _lock:
        missing = [p for p in LOCAL_PROVIDERS if force or p not in _cache]
        if missing:
            _refresh(missing)
        stale = [p for p in LOCAL_PROVIDERS if now - _cache[p][0] > _TTL_S]
        if stale and not _refreshing:
            _refreshing = True
            threading.Thread(target=_refresh_in_background, args=(stale,), daemon=True).start()
        return {p: _cache[p][1] for p in LOCAL_PROVIDERS}


def prime() -> None:
    """Probe local servers in the background so the first request doesn't wait on the network."""
    threading.Thread(target=discover_all, name="sphura-local-discovery", daemon=True).start()


def discover(provider: str) -> LocalStatus:
    return discover_all()[provider]


def guess_tools(provider: str, name: str) -> bool:
    """LM Studio emulates tool calling for every model; Ollama rejects tools for some families."""
    return provider == "lmstudio" or not _NO_TOOLS.search(name)


def guess_vision(name: str) -> bool:
    return bool(_VISION.search(name))


def pretty_label(name: str) -> str:
    """'qwen2.5:7b' → 'Qwen2.5 7B', 'qwen/qwen2.5-coder-14b' → 'Qwen2.5 Coder 14B'."""
    base = name.split("/")[-1].replace(":latest", "")
    parts = re.split(r"[:\-_ ]+", base)
    out = []
    for p in parts:
        if re.fullmatch(r"\d+(\.\d+)?[bm]", p, re.I):
            out.append(p.upper())
        elif p:
            out.append(p[0].upper() + p[1:])
    return " ".join(out) or name
