"""SQLite TTL cache (data_dir/market_cache.db) with single-flight fetches and retry/backoff.

`cached(key, ttl, fetch)` returns the cached JSON value when fresh; otherwise exactly one coroutine fetches it
(concurrent callers for the same key await that one), with up to 3 attempts and exponential backoff. A fetch that
keeps failing is remembered for FAILURE_TTL_S so a flaky upstream is not hammered.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import settings

log = logging.getLogger("sphura.market.cache")

MIN_TTL_S = 60.0
FAILURE_TTL_S = 30.0
ATTEMPTS = 3
BACKOFF_S = 0.5

_db_lock = threading.Lock()
_inflight: dict[str, asyncio.Future] = {}
_failures: dict[str, tuple[float, str]] = {}


class MarketError(Exception):
    """A friendly, user-facing market data error (never a stack trace)."""


class MarketTimeout(MarketError):
    """The provider did not answer in time; retrying a hanging upstream only multiplies the wait."""


UNAVAILABLE = "Market data is unavailable right now; try again shortly"


def _path() -> str:
    return str(settings.data_dir / "market_cache.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_path(), timeout=5.0)
    conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL NOT NULL)")
    return conn


def _read(key: str) -> Any | None:
    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT value, expires FROM cache WHERE key = ?", (key,)).fetchone()
    if row is None or row[1] < time.time():
        return None
    try:
        return json.loads(row[0])
    except ValueError:
        return None


def _write(key: str, value: Any, ttl: float) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    with _db_lock, _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO cache (key, value, expires) VALUES (?, ?, ?)",
                     (key, payload, time.time() + ttl))
        conn.execute("DELETE FROM cache WHERE expires < ?", (time.time() - 3600,))


def clear() -> None:
    """Forget everything (tests)."""
    _failures.clear()
    with _db_lock, _connect() as conn:
        conn.execute("DELETE FROM cache")


async def cached(key: str, ttl: float, fetch: Callable[[], Awaitable[Any]]) -> tuple[Any, bool]:
    """(value, from_cache). Raises MarketError when the fetch keeps failing."""
    ttl = max(MIN_TTL_S, ttl)
    hit = await asyncio.to_thread(_read, key)
    if hit is not None:
        return hit, True
    failed = _failures.get(key)
    if failed and time.monotonic() - failed[0] < FAILURE_TTL_S:
        raise MarketError(failed[1])
    loop = asyncio.get_running_loop()
    pending = _inflight.get(key)
    if pending is not None and not pending.done():
        return await asyncio.shield(pending), False
    future: asyncio.Future = loop.create_future()
    _inflight[key] = future
    try:
        value = await _fetch_with_backoff(key, fetch)
        await asyncio.to_thread(_write, key, value, ttl)
        future.set_result(value)
        return value, False
    except BaseException as exc:
        if not future.done():
            # A cancelled leader (client gone, outer timeout) must not cancel the callers sharing its fetch:
            # they get a normal MarketError instead of a CancelledError that would end their stream.
            shared = exc if isinstance(exc, Exception) else MarketError(UNAVAILABLE)
            future.set_exception(shared)
            future.exception()  # mark retrieved: without concurrent waiters asyncio would log it as unhandled
        raise
    finally:
        if _inflight.get(key) is future:
            _inflight.pop(key, None)
        if not future.done():
            future.cancel()


async def _fetch_with_backoff(key: str, fetch: Callable[[], Awaitable[Any]]) -> Any:
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        if attempt:
            await asyncio.sleep(BACKOFF_S * (2 ** (attempt - 1)))
        try:
            value = await fetch()
            _failures.pop(key, None)
            return value
        except MarketError as exc:
            last = exc
            if isinstance(exc, MarketTimeout) or "not found" in str(exc).lower() or "unknown" in str(exc).lower():
                break  # a bad symbol or a hanging provider doesn't get better with retries
        except TimeoutError:  # asyncio.TimeoutError is TimeoutError on Python 3.11+
            log.info("market fetch %s timed out", key)
            last = MarketTimeout("The market data provider took too long to answer")
            break
        except Exception as exc:  # noqa: BLE001
            log.info("market fetch %s failed (attempt %d/%d): %s", key, attempt + 1, ATTEMPTS, exc)
            last = exc
    message = str(last) if isinstance(last, MarketError) else UNAVAILABLE
    _failures[key] = (time.monotonic(), message)
    raise MarketError(message)
