"""Quotes and price history from yfinance (blocking calls run in a worker thread, cached >= 60 s)."""
from __future__ import annotations

import asyncio
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any

from app.features.market import symbols
from app.features.market.cache import MarketError, MarketTimeout, cached

log = logging.getLogger("sphura.market")

QUOTE_TTL_S = 60.0
HISTORY_TTL_S = 300.0
FETCH_TIMEOUT_S = 20.0
PERIODS = ("1mo", "3mo", "6mo", "1y", "5y")
_SYMBOL_RE = re.compile(r"^[A-Z0-9&\-.^=]{1,20}$")


def _iso(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def valid_symbol(symbol: str) -> bool:
    return bool(_SYMBOL_RE.match(symbol or ""))


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def _field(info: Any, name: str) -> Any:
    """One fast_info field; yfinance raises (KeyError 'currentTradingPeriod', …) for unknown symbols."""
    try:
        return getattr(info, name, None)
    except Exception:  # noqa: BLE001
        return None


def _fetch_quote_sync(symbol: str) -> dict[str, Any]:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    info = ticker.fast_info
    price = _num(_field(info, "last_price"))
    previous = _num(_field(info, "previous_close"))
    if price is None:
        hist = ticker.history(period="5d")
        closes = [c for c in (_num(v) for v in getattr(hist, "Close", [])) if c is not None]
        if closes:
            price = closes[-1]
            previous = previous if previous is not None else (closes[-2] if len(closes) > 1 else None)
    if price is None:
        raise MarketError(f"No market data found for {symbol} (unknown symbol or market closed)")
    known = symbols.lookup(symbol)
    name = known.name if known else symbol
    change = price - previous if previous is not None else 0.0
    return {
        "symbol": symbol, "name": name, "price": round(price, 4), "currency": str(_field(info, "currency") or "USD"),
        "change": round(change, 4), "changePercent": round(change / previous * 100, 2) if previous else 0.0,
        "dayHigh": _num(_field(info, "day_high")), "dayLow": _num(_field(info, "day_low")),
        "previousClose": previous, "asOf": _iso(), "source": "yfinance", "delayed": True,
    }


def _fetch_history_sync(symbol: str, period: str) -> dict[str, Any]:
    import yfinance as yf

    hist = yf.Ticker(symbol).history(period=period)
    points = []
    for idx, close in zip(getattr(hist, "index", []), getattr(hist, "Close", [])):
        c = _num(close)
        if c is None:
            continue
        day = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        points.append({"date": day.strftime("%Y-%m-%d"), "close": round(c, 4)})
    if not points:
        raise MarketError(f"No price history found for {symbol}")
    return {"symbol": symbol, "period": period, "points": points, "source": "yfinance", "asOf": _iso()}


async def _in_thread(fn, *args):  # noqa: ANN001, ANN202
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), FETCH_TIMEOUT_S)
    except asyncio.TimeoutError:
        raise MarketTimeout("The market data provider took too long to answer") from None


async def get_quote(symbol: str) -> dict[str, Any]:
    """Latest (delayed) quote; cached 60 s; raises MarketError with a friendly message."""
    symbol = symbols.normalise(symbol)
    if not valid_symbol(symbol):
        raise MarketError("That doesn't look like a ticker symbol (try TCS.NS, AAPL or ^NSEI)")
    value, hit = await cached(f"quote:{symbol}", QUOTE_TTL_S, lambda: _in_thread(_fetch_quote_sync, symbol))
    return {**value, "cached": hit}


async def get_history(symbol: str, period: str = "1mo") -> dict[str, Any]:
    symbol = symbols.normalise(symbol)
    if not valid_symbol(symbol):
        raise MarketError("That doesn't look like a ticker symbol (try TCS.NS, AAPL or ^NSEI)")
    if period not in PERIODS:
        raise MarketError(f"period must be one of {', '.join(PERIODS)}")
    value, hit = await cached(f"history:{symbol}:{period}", HISTORY_TTL_S,
                              lambda: _in_thread(_fetch_history_sync, symbol, period))
    return {**value, "cached": hit}


async def fx_rate(base: str, quote: str) -> dict[str, Any]:
    pair = f"{base.strip().upper()}{quote.strip().upper()}=X"
    return await get_quote(pair)


def format_quote(q: dict[str, Any]) -> str:
    """One-line summary for sources / tool results."""
    sign = "+" if q.get("change", 0) >= 0 else ""
    extra = ""
    if q.get("dayHigh") is not None and q.get("dayLow") is not None:
        extra = f"; day range {q['dayLow']:,.2f}–{q['dayHigh']:,.2f}"
    return (f"{q['name']} ({q['symbol']}): {q['price']:,.2f} {q['currency']} ({sign}{q['change']:,.2f}, "
            f"{sign}{q['changePercent']:.2f}% vs previous close{extra}). Delayed data from yfinance as of "
            f"{q['asOf']}.")


def format_history(h: dict[str, Any]) -> str:
    pts = h["points"]
    first, last = pts[0], pts[-1]
    change = (last["close"] - first["close"]) / first["close"] * 100 if first["close"] else 0.0
    high = max(p["close"] for p in pts)
    low = min(p["close"] for p in pts)
    return (f"{h['symbol']} over {h['period']}: {first['date']} close {first['close']:,.2f} → {last['date']} close "
            f"{last['close']:,.2f} ({change:+.2f}%); period high {high:,.2f}, low {low:,.2f}; {len(pts)} trading days. "
            f"Source: yfinance (delayed).")
