"""Market tools (quotes, history, FX, finance news) over `app.features.market`; results become `web` sources."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import tool

from app.agent.charts import history_chart
from app.agent.run import AgentRun, current_run
from app.features.market import service

log = logging.getLogger("sphura.agent.tools")

TOOL_TIMEOUT_S = 45.0
YAHOO = "https://finance.yahoo.com/quote/"


def _run() -> AgentRun | None:
    return current_run.get()


def add_quote_source(run: AgentRun | None, q: dict[str, Any]) -> int | None:
    if run is None:
        return None
    symbol = q["symbol"]
    index = run.registry.add_web(f"{YAHOO}{symbol}", f"{q['name']} ({symbol}) quote", service.format_quote(q),
                                 "finance.yahoo.com")
    run.emit_sources()
    return index


def add_history_source(run: AgentRun | None, h: dict[str, Any]) -> int | None:
    if run is None:
        return None
    index = run.registry.add_web(f"{YAHOO}{h['symbol']}/history?period={h['period']}",
                                 f"{h['symbol']} price history ({h['period']})", service.format_history(h),
                                 "finance.yahoo.com")
    run.emit_sources()
    chart = history_chart(h)
    if chart:  # one price chart per symbol: the longer history wins
        same = next((i for i, c in enumerate(run.charts) if c["title"].startswith(f"{h['symbol']} ")), None)
        if same is None:
            run.charts.append(chart)
        elif len(chart["labels"]) > len(run.charts[same]["labels"]) or chart["title"] == run.charts[same]["title"]:
            run.charts[same] = chart
    return index


def add_news_sources(run: AgentRun | None, items: list[dict[str, Any]]) -> list[int]:
    if run is None:
        return []
    indexes = []
    for item in items:
        s = item.get("sentiment") or {}
        tag = f"[{s.get('label', 'neutral')} {float(s.get('score', 0.5)):.2f}] " if s else ""
        indexes.append(run.registry.add_web(item["url"], item["title"], tag + (item.get("snippet") or ""),
                                            item.get("domain") or ""))
    run.emit_sources()
    return indexes


def _cite(index: int | None) -> str:
    return f" Cite as [{index}]." if index else ""


async def _guarded(coro: Any) -> Any:
    return await asyncio.wait_for(coro, TOOL_TIMEOUT_S)


@tool
async def get_quote(symbol: str) -> str:
    """Latest (delayed) price of a stock, index, ETF, commodity or crypto via yfinance. Indian names get the
    NSE suffix automatically ("TCS" → "TCS.NS"); indices use ^NSEI (NIFTY 50), ^BSESN (SENSEX), ^GSPC (S&P 500)."""
    try:
        q = await _guarded(service.get_quote(symbol))
    except service.MarketError as exc:
        return f"Quote unavailable: {exc}"
    except Exception as exc:  # noqa: BLE001
        log.warning("get_quote failed for %s: %s", symbol, exc)
        return "Quote unavailable: market data is not reachable right now."
    return service.format_quote(q) + _cite(add_quote_source(_run(), q))


@tool
async def get_history(symbol: str, period: str = "1mo") -> str:
    """Closing-price history of a symbol over period 1mo, 3mo, 6mo, 1y or 5y (yfinance, delayed)."""
    try:
        h = await _guarded(service.get_history(symbol, period))
    except service.MarketError as exc:
        return f"History unavailable: {exc}"
    except Exception as exc:  # noqa: BLE001
        log.warning("get_history failed for %s: %s", symbol, exc)
        return "History unavailable: market data is not reachable right now."
    return service.format_history(h) + _cite(add_history_source(_run(), h))


@tool
async def fx_rate(base: str, quote: str) -> str:
    """Latest exchange rate between two currencies, e.g. base="USD", quote="INR" (yfinance, delayed)."""
    try:
        q = await _guarded(service.fx_rate(base, quote))
    except service.MarketError as exc:
        return f"FX rate unavailable: {exc}"
    except Exception as exc:  # noqa: BLE001
        log.warning("fx_rate failed for %s/%s: %s", base, quote, exc)
        return "FX rate unavailable: market data is not reachable right now."
    return service.format_quote(q) + _cite(add_quote_source(_run(), q))


@tool
async def finance_news(query: str) -> str:
    """Recent finance/business news headlines about a company, sector or topic, each labelled with sentiment
    (positive / neutral / negative). Results become numbered sources to cite."""
    try:
        result = await _guarded(service.finance_news(query))
    except service.MarketError as exc:
        return f"News unavailable: {exc}"
    except Exception as exc:  # noqa: BLE001
        log.warning("finance_news failed for %s: %s", query, exc)
        return "News unavailable: web search is not reachable right now."
    items = result.get("items") or []
    if not items:
        return f"No recent finance news found for “{query}”."
    indexes = add_news_sources(_run(), items)
    lines = []
    for item, index in zip(items, indexes or [None] * len(items)):
        s = item.get("sentiment") or {}
        ref = f"[{index}] " if index else ""
        lines.append(f"{ref}{item['title']} — {item.get('domain', '')} (sentiment: {s.get('label', 'neutral')} "
                     f"{float(s.get('score', 0.5)):.2f}): {item.get('snippet', '')[:300]}")
    return "\n".join(lines)
