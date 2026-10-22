"""market: deterministic quotes / history / news for the symbols mentioned, before the model drafts."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.agent.run import attach
from app.agent.state import FinState
from app.agent.tools.market import add_history_source, add_news_sources, add_quote_source
from app.features.market import service

log = logging.getLogger("sphura.agent.market")

MAX_SYMBOLS = 3
TOOL_TIMEOUT_S = 45.0
_NEWS = re.compile(r"\b(news|headline|headlines|latest|happening|why (?:did|is|has|are)|update|updates|"
                   r"announce|results|earnings|sentiment)\b", re.I)
_HISTORY = re.compile(r"\b(chart|history|trend|performance|performed|last (?:week|month|year|\d+ (?:months|years))|"
                      r"past (?:week|month|year)|ytd|year to date|1y|5y|6 months|3 months)\b", re.I)
_PERIOD = {"week": "1mo", "month": "1mo", "3 months": "3mo", "6 months": "6mo", "year": "1y", "ytd": "1y",
           "1y": "1y", "5y": "5y", "5 years": "5y"}
MARKET_INSTRUCTION = ("Market data: the quotes/headlines above were fetched live (delayed) by Sphura. Use those "
                      "figures verbatim with [n] citations, state the as-of time, and do not call get_quote again "
                      "for the same symbol.")


def _period(question: str) -> str:
    low = question.lower()
    for key, period in sorted(_PERIOD.items(), key=lambda kv: -len(kv[0])):  # "3 months" before "month"
        if key in low:
            return period
    return "1mo"


async def market(state: FinState) -> dict[str, Any]:
    run = attach(state)
    run.phase("searching", "Fetching market data")
    question = state.get("question") or run.turn.question
    found = service.mentions(question, limit=MAX_SYMBOLS)
    wants_news = bool(_NEWS.search(question)) or run.turn.web_search
    wants_history = bool(_HISTORY.search(question))
    quotes: list[dict[str, Any]] = []
    news_count = 0
    for sym in found:
        step = run.step_start("get_quote", f"Fetching the quote for {sym.name} ({sym.symbol})")
        try:
            q = await asyncio.wait_for(service.get_quote(sym.symbol), TOOL_TIMEOUT_S)
        except service.MarketError as exc:
            run.step_end(step, "error", str(exc))
            run.notes.append(f"Quote for {sym.symbol} unavailable: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001
            log.warning("quote failed for %s: %s", sym.symbol, exc)
            run.step_end(step, "error", "Market data is unavailable right now")
            run.notes.append(f"Quote for {sym.symbol} unavailable right now.")
            continue
        index = add_quote_source(run, q)
        quotes.append({"symbol": q["symbol"], "price": q["price"], "currency": q["currency"],
                       "changePercent": q["changePercent"], "source": index})
        run.step_end(step, "done", f"{q['price']:,.2f} {q['currency']} ({q['changePercent']:+.2f}%)")
        if wants_history and sym is found[0]:
            period = _period(question)
            hstep = run.step_start("get_history", f"Fetching {sym.symbol} history ({period})")
            try:
                h = await asyncio.wait_for(service.get_history(sym.symbol, period), TOOL_TIMEOUT_S)
                add_history_source(run, h)
                run.step_end(hstep, "done", f"{len(h['points'])} trading days")
            except Exception as exc:  # noqa: BLE001
                run.step_end(hstep, "error", str(exc) if isinstance(exc, service.MarketError) else
                             "Price history is unavailable right now")
    if wants_news or not found:
        query = " ".join(s.name for s in found) if found else question
        step = run.step_start("finance_news", f"Searching finance news for “{query[:60]}”")
        try:
            result = await asyncio.wait_for(service.finance_news(query), TOOL_TIMEOUT_S)
            items = result.get("items") or []
            add_news_sources(run, items)
            news_count = len(items)
            run.step_end(step, "done", f"{news_count} headline{'s' if news_count != 1 else ''}" if items
                         else "No results")
            run.searches.append(query)
        except service.MarketError as exc:
            run.step_end(step, "error", str(exc))
            run.notes.append(f"Finance news unavailable: {exc}")
        except Exception as exc:  # noqa: BLE001
            log.warning("news failed for %s: %s", query, exc)
            run.step_end(step, "error", "Finance news is unavailable right now")
            run.notes.append("Finance news is unavailable right now.")
    if quotes or news_count:
        run.extra_system.append(MARKET_INSTRUCTION)
    symbols = [s.symbol for s in found]
    run.meta_extra["market"] = {"symbols": symbols}
    return {"market": {"symbols": symbols, "quotes": quotes, "news": news_count},
            "sources": run.registry.sources(), "steps": run.steps}
