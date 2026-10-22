"""Public surface of the market feature (used by /api/market and the agent's market tools)."""
from __future__ import annotations

from app.features.market.cache import MarketError
from app.features.market.news import finance_news
from app.features.market.quotes import PERIODS, format_history, format_quote, fx_rate, get_history, get_quote
from app.features.market.symbols import Symbol, lookup, mentions, normalise, search, search_symbols

__all__ = ["MarketError", "finance_news", "PERIODS", "format_history", "format_quote", "fx_rate", "get_history",
           "get_quote", "Symbol", "lookup", "mentions", "normalise", "search", "search_symbols"]
