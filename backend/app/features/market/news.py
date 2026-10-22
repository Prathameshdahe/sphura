"""Finance news through the existing web search, biased to finance/news domains, labelled with sentiment."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.features.market import sentiment
from app.features.market.cache import MarketError, cached
from app.tools import web

log = logging.getLogger("sphura.market.news")

NEWS_TTL_S = 300.0
MAX_ITEMS = 6
FINANCE_DOMAINS = (
    "economictimes.indiatimes.com", "moneycontrol.com", "livemint.com", "business-standard.com", "reuters.com",
    "bloomberg.com", "cnbc.com", "cnbctv18.com", "ndtvprofit.com", "financialexpress.com", "thehindubusinessline.com",
    "zeebiz.com", "businesstoday.in", "ft.com", "wsj.com", "marketwatch.com", "finance.yahoo.com", "investing.com",
    "nseindia.com", "bseindia.com", "sebi.gov.in", "rbi.org.in", "incometax.gov.in", "morningstar.in",
    "groww.in", "zerodha.com", "tickertape.in", "screener.in", "valueresearchonline.com", "etmoney.com",
)
_BLOCKED = ("pinterest.", "facebook.com", "instagram.com", "tiktok.com", "quora.com")


def _domain_rank(domain: str) -> int:
    d = (domain or "").lower()
    for i, good in enumerate(FINANCE_DOMAINS):
        if d == good or d.endswith("." + good):
            return i
    return len(FINANCE_DOMAINS) + (50 if any(b in d for b in _BLOCKED) else 0)


def finance_query(query: str) -> str:
    q = " ".join(query.split())
    low = q.lower()
    if not any(w in low for w in ("news", "stock", "share", "market", "results", "earnings")):
        q += " stock market news"
    return q[:300]


async def _search(query: str) -> list[dict[str, Any]]:
    results = await web.web_search(finance_query(query), max_results=10)
    if results.error:
        raise MarketError(results.error)
    ranked = sorted(results, key=lambda r: _domain_rank(r.domain))
    items = [{"title": r.title, "url": r.url, "domain": r.domain, "snippet": r.snippet[:400], "publishedAt": None}
             for r in ranked if not any(b in (r.domain or "") for b in _BLOCKED)][:MAX_ITEMS]
    labels = await asyncio.to_thread(sentiment.label_many, [f"{i['title']}. {i['snippet']}" for i in items])
    for item, label in zip(items, labels):
        item["sentiment"] = label
    return items


async def finance_news(query: str) -> dict[str, Any]:
    """{items: NewsItem[], cached, sentimentModel}; raises MarketError when search is unavailable."""
    q = " ".join((query or "").split())
    if not q:
        raise MarketError("Give a company, ticker or topic to search news for")
    items, hit = await cached(f"news:{q.lower()}", NEWS_TTL_S, lambda: _search(q))
    return {"items": items, "cached": hit, "sentimentModel": sentiment.backend_name()}
