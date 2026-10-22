"""GET /market/{search,quote,history,news} (docs/FINANCE_PLAN.md section 8). Upstream trouble → 503 with a message."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.db.models import User
from app.features.market import service
from app.features.market.schemas import HistoryOut, NewsOut, Quote, SearchOut, SymbolMatch

log = logging.getLogger("sphura.api.market")
router = APIRouter(prefix="/market", tags=["market"])


def _market_error(exc: service.MarketError) -> HTTPException:
    text = str(exc)
    code = status.HTTP_404_NOT_FOUND if "no market data" in text.lower() or "no price history" in text.lower() \
        else status.HTTP_503_SERVICE_UNAVAILABLE
    if "doesn't look like" in text or "must be one of" in text or "give a company" in text.lower():
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(code, text)


@router.get("/search")
async def search(q: str = Query(min_length=1, max_length=60), _user: User = Depends(get_current_user)) -> dict:
    """Bundled Indian + US tickers first; yfinance's lookup fills in when the bundled list has few matches."""
    try:
        found = await service.search_symbols(q)
    except Exception as exc:  # noqa: BLE001 — never a 500 for a lookup
        log.warning("symbol search failed for %s: %s", q, exc)
        found = service.search(q)
    matches = [SymbolMatch(symbol=s.symbol, name=s.name, exchange=s.exchange) for s in found]
    return SearchOut(matches=matches).dump()


@router.get("/quote")
async def quote(symbol: str = Query(min_length=1, max_length=24), _user: User = Depends(get_current_user)) -> dict:
    try:
        q = await service.get_quote(symbol)
    except service.MarketError as exc:
        raise _market_error(exc) from None
    except Exception as exc:  # noqa: BLE001 — never a 500 for a market lookup
        log.warning("quote failed for %s: %s", symbol, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Market data is unavailable right now") from None
    return Quote.model_validate(q).dump()


@router.get("/history")
async def history(symbol: str = Query(min_length=1, max_length=24), period: str = Query(default="1mo"),
                  _user: User = Depends(get_current_user)) -> dict:
    if period not in service.PERIODS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"period must be one of {', '.join(service.PERIODS)}")
    try:
        h = await service.get_history(symbol, period)
    except service.MarketError as exc:
        raise _market_error(exc) from None
    except Exception as exc:  # noqa: BLE001
        log.warning("history failed for %s: %s", symbol, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Market data is unavailable right now") from None
    return HistoryOut.model_validate(h).dump()


@router.get("/news")
async def news(query: str = Query(min_length=1, max_length=200), _user: User = Depends(get_current_user)) -> dict:
    try:
        result = await service.finance_news(query)
    except service.MarketError as exc:
        raise _market_error(exc) from None
    except Exception as exc:  # noqa: BLE001
        log.warning("news failed for %s: %s", query, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Finance news is unavailable right now") from None
    return NewsOut.model_validate({"items": result["items"]}).dump()
