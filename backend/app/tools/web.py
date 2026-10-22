"""Web tools for the agent: search (Tavily → DuckDuckGo fallback) and SSRF-safe page reading.

Neither function raises: failures come back as structured errors the agent can show.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import settings

log = logging.getLogger("sphura.web")

# An honest bot UA with a contact token: sites (incl. Wikipedia) reject spoofed browser UAs from non-browsers.
USER_AGENT = "Mozilla/5.0 (compatible; SphuraBot/1.0; +https://example.com/sphura-bot)"
_HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"}
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
PAGE_DEADLINE_S = 20.0  # whole fetch incl. redirects; httpx's 10 s timeout is per network operation
# ddgs queries a random mix of engines with a random browser fingerprint on every call; several engines answer
# 429/403 to bots, so roughly 1 call in 3 comes back "No results" for an ordinary query. Each retry is a fresh draw.
DDG_ATTEMPTS = 3
DDG_RETRY_DELAY_S = 0.6     # backoff: 0.6 s, then 1.2 s
DDG_ATTEMPT_TIMEOUT_S = 20.0
DDG_DEADLINE_S = 30.0       # all attempts together
_TEXT_TYPES = ("text/html", "application/xhtml", "text/plain", "text/markdown", "application/xml", "text/xml",
               "application/json")


@dataclass
class WebResult:
    title: str
    url: str
    snippet: str
    domain: str
    score: float | None = None


class SearchResults(list[WebResult]):
    """A list of results that can also carry an error / the provider used."""

    def __init__(self, items: list[WebResult] | None = None, error: str | None = None, provider: str = "") -> None:
        super().__init__(items or [])
        self.error = error
        self.provider = provider


@dataclass
class PageContent:
    url: str
    title: str = ""
    text: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text)


def domain_of(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:  # e.g. a malformed IPv6 literal produced by the model
        return ""
    return host[4:] if host.startswith("www.") else host


# ── search ───────────────────────────────────────────────────────────────────
async def _tavily(query: str, max_results: int) -> SearchResults:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={"query": query, "max_results": max_results, "search_depth": "basic",
                  "include_answer": False, "include_raw_content": False},
        )
        r.raise_for_status()
        data = r.json()
    items = [
        WebResult(title=str(i.get("title") or i.get("url")), url=str(i["url"]),
                  snippet=str(i.get("content") or "")[:600], domain=domain_of(str(i["url"])), score=i.get("score"))
        for i in data.get("results", []) if i.get("url")
    ]
    return SearchResults(items[:max_results], provider="tavily")


def _ddg_sync(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    return DDGS(timeout=8).text(query, max_results=max_results, safesearch="moderate")


async def _duckduckgo(query: str, max_results: int, timeout: float = DDG_ATTEMPT_TIMEOUT_S) -> SearchResults:
    raw = await asyncio.wait_for(asyncio.to_thread(_ddg_sync, query, max_results), timeout=timeout)
    items = [
        WebResult(title=str(i.get("title") or i.get("href")), url=str(i["href"]), snippet=str(i.get("body") or "")[:600],
                  domain=domain_of(str(i["href"])))
        for i in raw or [] if i.get("href", "").startswith(("http://", "https://"))
    ]
    return SearchResults(items[:max_results], provider="duckduckgo")


async def web_search(query: str, max_results: int = 6) -> SearchResults:
    query = " ".join(query.split())[:400]
    if not query:
        return SearchResults(error="Empty search query")
    if settings.tavily_api_key:
        try:
            return await _tavily(query, max_results)
        except Exception as exc:  # noqa: BLE001
            log.warning("Tavily search failed (%s); falling back to DuckDuckGo", type(exc).__name__)
    return await _duckduckgo_with_retries(query, max_results)


async def _duckduckgo_with_retries(query: str, max_results: int) -> SearchResults:
    """ddgs with up to DDG_ATTEMPTS fresh draws: "No results", an empty list and engine errors are all retried.

    ddgs reports "No results found" whenever the engines it happened to pick were rate-limited, even for
    perfectly ordinary queries, so only an answer that stays empty after every attempt counts as "no results".
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + DDG_DEADLINE_S
    failure: str | None = None
    for attempt in range(DDG_ATTEMPTS):
        if attempt:
            await asyncio.sleep(DDG_RETRY_DELAY_S * attempt)
        remaining = deadline - loop.time()
        if remaining < 1.0:
            break
        try:
            results = await _duckduckgo(query, max_results, timeout=min(DDG_ATTEMPT_TIMEOUT_S, remaining))
        except asyncio.TimeoutError:
            return SearchResults(error="Web search timed out")  # a hung engine: don't stack more stuck threads
        except Exception as exc:  # noqa: BLE001
            if "no results" in str(exc).lower():
                failure = None
            else:
                log.warning("DuckDuckGo search failed (attempt %d/%d): %s", attempt + 1, DDG_ATTEMPTS, exc)
                failure = "Web search is unavailable right now"
            continue
        if results:
            if attempt:
                log.info("DuckDuckGo answered on attempt %d/%d", attempt + 1, DDG_ATTEMPTS)
            return results
        failure = None  # an empty list (e.g. only non-http links): same as "No results"
    if failure:
        return SearchResults(error=failure)
    return SearchResults(provider="duckduckgo")


# ── SSRF guard ───────────────────────────────────────────────────────────────
def _blocked_ip(raw: str) -> bool:
    try:
        ip = ipaddress.ip_address(raw.split("%", 1)[0])
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast


async def check_url(url: str) -> str | None:
    """Return why `url` must not be fetched, or None when it is a public http(s) address."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "Invalid URL"
    if parts.scheme not in ("http", "https"):
        return "Only http and https URLs can be read"
    host = parts.hostname
    if not host:
        return "Invalid URL"
    if parts.username or parts.password:
        return "URLs with credentials are not allowed"
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
        addresses = [host]
    except ValueError:
        try:
            infos = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(host, port or (443 if parts.scheme == "https" else 80),
                                                       type=socket.SOCK_STREAM),
                timeout=5.0,
            )
        except (OSError, UnicodeError, asyncio.TimeoutError):  # UnicodeError: invalid IDNA label
            return f"Couldn't resolve {host}"
        addresses = [str(info[4][0]) for info in infos]
    if not addresses or any(_blocked_ip(a) for a in addresses):
        return "Blocked: private or reserved network address"
    return None


# ── page reading ─────────────────────────────────────────────────────────────
def _peer_ip(resp: httpx.Response) -> str | None:
    stream = resp.extensions.get("network_stream")
    try:
        addr = stream.get_extra_info("server_addr") if stream is not None else None
    except Exception:  # noqa: BLE001
        return None
    return str(addr[0]) if addr else None


def _extract(body: bytes, url: str, content_type: str) -> tuple[str, str]:
    if "html" in content_type or "xml" in content_type:
        import trafilatura

        doc = trafilatura.bare_extraction(body, url=url, with_metadata=True, include_tables=True,
                                          include_comments=False, favor_recall=True)
        if doc is not None:
            return str(getattr(doc, "title", "") or ""), str(getattr(doc, "text", "") or "")
        return "", ""
    return "", body.decode("utf-8", errors="replace")


async def _fetch(url: str) -> PageContent | tuple[str, bytes, str]:
    """(final url, body, content type) of a public text page, or a PageContent carrying the error."""
    current = url
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False,
                                     headers=_HEADERS) as client:
            for _ in range(MAX_REDIRECTS + 1):
                reason = await check_url(current)
                if reason:
                    return PageContent(url=url, error=reason)
                async with client.stream("GET", current) as resp:
                    peer = _peer_ip(resp)
                    if peer and _blocked_ip(peer):  # DNS changed between our check and the connect
                        return PageContent(url=url, error="Blocked: private or reserved network address")
                    if resp.is_redirect and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        continue
                    if resp.status_code >= 400:
                        return PageContent(url=current, error=f"The site answered HTTP {resp.status_code}")
                    ctype = resp.headers.get("content-type", "text/html").lower()
                    if not any(t in ctype for t in _TEXT_TYPES):
                        return PageContent(url=current, error=f"Unsupported content type ({ctype.split(';')[0]})")
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) >= MAX_PAGE_BYTES:
                            break
                    return current, bytes(body[:MAX_PAGE_BYTES]), ctype
            return PageContent(url=url, error="Too many redirects")
    except httpx.TimeoutException:
        return PageContent(url=current, error="The page took too long to load")
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        return PageContent(url=current, error=f"Couldn't load the page ({type(exc).__name__})")


async def read_page(url: str, max_chars: int = 12000) -> PageContent:
    url = url.strip()
    try:
        fetched = await asyncio.wait_for(_fetch(url), timeout=PAGE_DEADLINE_S)
    except asyncio.TimeoutError:
        return PageContent(url=url, error="The page took too long to load")
    except Exception as exc:  # noqa: BLE001  (never raise into the agent)
        log.warning("fetch failed for %s: %s", url, exc)
        return PageContent(url=url, error="Couldn't load the page")
    if isinstance(fetched, PageContent):
        return fetched
    current, body, ctype = fetched
    try:
        title, text = await asyncio.wait_for(asyncio.to_thread(_extract, body, current, ctype), timeout=15.0)
    except Exception as exc:  # noqa: BLE001
        log.warning("extraction failed for %s: %s", current, exc)
        return PageContent(url=current, error="Couldn't extract readable text")
    text = text.strip()
    if not text:
        return PageContent(url=current, title=title, error="No readable text on the page")
    if is_bot_challenge(title, text):
        return PageContent(url=current, title=title, error="The site blocked automated reading")
    return PageContent(url=current, title=title or domain_of(current), text=text[:max_chars])


_CHALLENGE_RE = re.compile(
    r"checking your browser|just a moment\.\.\.|attention required|verify (that )?you are (a )?human|"
    r"enable javascript and cookies to continue|are you a robot|access denied|ddos protection by",
    re.I)


def is_bot_challenge(title: str, text: str) -> bool:
    """A short anti-bot interstitial (Cloudflare "Just a moment...", PMC "Checking your browser") — not content."""
    return len(text.split()) < 80 and bool(_CHALLENGE_RE.search(f"{title}\n{text}"))


# ── binary downloads (wave 2: Paper Lens PDFs) ──────────────────────────────
BINARY_DEADLINE_S = 90.0


@dataclass
class BinaryContent:
    url: str
    data: bytes = b""
    content_type: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.data)


async def _fetch_binary(url: str, max_bytes: int, accept: str) -> BinaryContent:
    current = url
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    limit_mb = max(1, max_bytes // (1024 * 1024))
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False, trust_env=False,
                                     headers=headers) as client:
            for _ in range(MAX_REDIRECTS + 1):
                reason = await check_url(current)
                if reason:
                    return BinaryContent(url=url, error=reason)
                async with client.stream("GET", current) as resp:
                    peer = _peer_ip(resp)
                    if peer and _blocked_ip(peer):
                        return BinaryContent(url=url, error="Blocked: private or reserved network address")
                    if resp.is_redirect and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        continue
                    if resp.status_code >= 400:
                        return BinaryContent(url=current, error=f"The site answered HTTP {resp.status_code}")
                    ctype = resp.headers.get("content-type", "").lower()
                    declared = resp.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > max_bytes:
                        return BinaryContent(url=current, content_type=ctype,
                                             error=f"The file is larger than {limit_mb} MB")
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:  # never keep a truncated binary
                            return BinaryContent(url=current, content_type=ctype,
                                                 error=f"The file is larger than {limit_mb} MB")
                    return BinaryContent(url=current, data=bytes(body), content_type=ctype)
            return BinaryContent(url=url, error="Too many redirects")
    except httpx.TimeoutException:
        return BinaryContent(url=current, error="The download took too long")
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        return BinaryContent(url=current, error=f"Couldn't download the file ({type(exc).__name__})")


async def fetch_bytes(url: str, max_bytes: int = 40 * 1024 * 1024, accept: str = "*/*",
                      deadline: float = BINARY_DEADLINE_S) -> BinaryContent:
    """SSRF-guarded, size-capped binary download (e.g. an open-access PDF). Never raises.

    Same guard as read_page: every hop is resolved and checked, redirects are followed manually and the
    connected peer is re-checked. Bodies over `max_bytes` are rejected rather than truncated.
    """
    url = url.strip()
    try:
        return await asyncio.wait_for(_fetch_binary(url, max_bytes, accept), timeout=deadline)
    except asyncio.TimeoutError:
        return BinaryContent(url=url, error="The download took too long")
    except Exception as exc:  # noqa: BLE001  (never raise into callers)
        log.warning("binary fetch failed for %s: %s", url, exc)
        return BinaryContent(url=url, error="Couldn't download the file")
