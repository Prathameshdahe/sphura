"""Market API shapes (docs/FINANCE_PLAN.md section 8)."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas import CamelModel


class SymbolMatch(CamelModel):
    symbol: str
    name: str
    exchange: str


class SearchOut(CamelModel):
    matches: list[SymbolMatch] = Field(default_factory=list)


class Quote(CamelModel):
    symbol: str
    name: str
    price: float
    currency: str
    change: float
    change_percent: float
    day_high: float | None = None
    day_low: float | None = None
    as_of: str
    source: Literal["yfinance"] = "yfinance"
    delayed: bool = True


class HistoryPoint(CamelModel):
    date: str
    close: float


class HistoryOut(CamelModel):
    symbol: str
    period: str
    points: list[HistoryPoint]


class Sentiment(CamelModel):
    label: Literal["positive", "neutral", "negative"]
    score: float


class NewsItem(CamelModel):
    title: str
    url: str
    domain: str
    snippet: str
    published_at: str | None = None
    sentiment: Sentiment


class NewsOut(CamelModel):
    items: list[NewsItem]
