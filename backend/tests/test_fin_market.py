"""/api/market/* with fake yfinance / web search: shapes, cache hits, symbol search, news sentiment, errors."""
from __future__ import annotations

import asyncio

import pytest

from app.features.market import cache, news, quotes, sentiment, symbols
from app.features.market import service
from app.tools import web


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def fake_yf(monkeypatch):
    calls = {"quote": [], "history": [], "search": []}

    def fetch_quote(symbol):
        calls["quote"].append(symbol)
        if symbol.startswith("NOPE"):
            raise cache.MarketError(f"No market data found for {symbol} (unknown symbol or market closed)")
        return {"symbol": symbol, "name": "Tata Consultancy Services", "price": 4123.45, "currency": "INR",
                "change": 12.3, "changePercent": 0.3, "dayHigh": 4150.0, "dayLow": 4100.0, "previousClose": 4111.15,
                "asOf": "2026-10-22T10:00:00Z", "source": "yfinance", "delayed": True}

    def fetch_history(symbol, period):
        calls["history"].append((symbol, period))
        return {"symbol": symbol, "period": period, "points": [{"date": "2026-09-22", "close": 4000.0},
                                                               {"date": "2026-10-22", "close": 4123.45}],
                "source": "yfinance", "asOf": "2026-10-22T10:00:00Z"}

    def yf_search(query, limit):
        calls["search"].append(query)
        return [symbols.Symbol("TATAMOTORS.BO", "Tata Motors Ltd", "BSE")]

    monkeypatch.setattr(quotes, "_fetch_quote_sync", fetch_quote)
    monkeypatch.setattr(quotes, "_fetch_history_sync", fetch_history)
    monkeypatch.setattr(symbols, "_yf_search_sync", yf_search)
    monkeypatch.setattr(cache, "BACKOFF_S", 0)
    return calls


def test_quote_shape_and_cache_hit(client, user, fake_yf):
    h = user["headers"]
    assert client.get("/api/market/quote?symbol=TCS.NS").status_code == 401
    r = client.get("/api/market/quote?symbol=tcs", headers=h)
    assert r.status_code == 200, r.text
    q = r.json()
    assert q == {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "price": 4123.45, "currency": "INR",
                 "change": 12.3, "changePercent": 0.3, "dayHigh": 4150.0, "dayLow": 4100.0,
                 "asOf": "2026-10-22T10:00:00Z", "source": "yfinance", "delayed": True}
    r2 = client.get("/api/market/quote?symbol=TCS.NS", headers=h)
    assert r2.status_code == 200 and r2.json() == q
    assert fake_yf["quote"] == ["TCS.NS"]  # served from the SQLite TTL cache the second time
    assert asyncio.run(service.get_quote("TCS.NS"))["cached"] is True


def test_quote_errors_are_friendly(client, user, fake_yf, monkeypatch):
    h = user["headers"]
    r = client.get("/api/market/quote?symbol=NOPE", headers=h)
    assert r.status_code == 404 and "No market data found" in r.json()["detail"]
    r = client.get("/api/market/quote?symbol=bad%20symbol!", headers=h)
    assert r.status_code == 400 and isinstance(r.json()["detail"], str)

    def boom(symbol):
        raise RuntimeError("yfinance exploded")

    monkeypatch.setattr(quotes, "_fetch_quote_sync", boom)
    r = client.get("/api/market/quote?symbol=AAPL", headers=h)
    assert r.status_code == 503 and r.json()["detail"] == "Market data is unavailable right now; try again shortly"


def test_single_flight_and_backoff(fake_yf, monkeypatch):
    attempts: list[str] = []

    def flaky(symbol):
        attempts.append(symbol)
        if len(attempts) < 3:
            raise RuntimeError("transient")
        return fake_yf and {"symbol": symbol, "name": symbol, "price": 1.0, "currency": "USD", "change": 0.0,
                            "changePercent": 0.0, "dayHigh": None, "dayLow": None, "previousClose": None,
                            "asOf": "2026-10-22T10:00:00Z", "source": "yfinance", "delayed": True}

    monkeypatch.setattr(quotes, "_fetch_quote_sync", flaky)

    async def scenario():
        return await asyncio.gather(service.get_quote("AAPL"), service.get_quote("AAPL"), service.get_quote("AAPL"))

    results = asyncio.run(scenario())
    assert all(r["symbol"] == "AAPL" for r in results) and len(attempts) == 3  # one fetch (2 retries), 3 callers


def test_history_shape_and_period_validation(client, user, fake_yf):
    h = user["headers"]
    r = client.get("/api/market/history?symbol=TCS&period=3mo", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"symbol": "TCS.NS", "period": "3mo", "points": [{"date": "2026-09-22", "close": 4000.0},
                                                                       {"date": "2026-10-22", "close": 4123.45}]}
    assert fake_yf["history"] == [("TCS.NS", "3mo")]
    r = client.get("/api/market/history?symbol=TCS&period=2y", headers=h)
    assert r.status_code == 400 and "period must be one of" in r.json()["detail"]


def test_symbol_search_bundled_then_yfinance(client, user, fake_yf):
    h = user["headers"]
    r = client.get("/api/market/search?q=hdfc", headers=h)
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert matches[0] == {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "exchange": "NSE"}
    assert all(set(m) == {"symbol", "name", "exchange"} for m in matches) and len(matches) >= 3
    assert fake_yf["search"] == []  # enough bundled matches: no network lookup
    r = client.get("/api/market/search?q=tata%20motors", headers=h)
    found = [m["symbol"] for m in r.json()["matches"]]
    assert found[0] == "TATAMOTORS.NS" and "TATAMOTORS.BO" in found and fake_yf["search"] == ["tata motors"]
    assert client.get("/api/market/search?q=", headers=h).status_code == 422


def test_symbol_helpers():
    assert service.normalise("tcs") == "TCS.NS" and service.normalise("AAPL") == "AAPL"
    assert service.normalise("nifty") == "^NSEI" and service.normalise("usd to inr") == "USDINR=X"
    found = {s.symbol for s in service.mentions("news about HDFC Bank and TCS share price, plus my EMI")}
    assert found == {"HDFCBANK.NS", "TCS.NS"}
    assert service.mentions("what is a SIP and how does EMI work") == []
    assert [s.symbol for s in service.mentions("is AAPL or ^NSEI a better index?")] == ["AAPL", "^NSEI"]


def test_news_labels_sentiment_and_ranks_finance_domains(client, user, monkeypatch):
    async def fake_search(query, max_results=6):
        return web.SearchResults([
            web.WebResult(title="Random blog", url="https://blog.example.com/x", snippet="HDFC Bank fell sharply",
                          domain="blog.example.com"),
            web.WebResult(title="HDFC Bank profit surges 20% on strong loan growth", url="https://www.livemint.com/a",
                          snippet="Record quarter.", domain="livemint.com"),
        ], provider="fake")

    monkeypatch.setattr(web, "web_search", fake_search)
    monkeypatch.setattr(sentiment, "_backend", None)
    monkeypatch.setattr(sentiment, "_backend_name", "lexicon")
    monkeypatch.setattr(sentiment, "_probed", True)
    r = client.get("/api/market/news?query=HDFC%20Bank", headers=user["headers"])
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["domain"] for i in items] == ["livemint.com", "blog.example.com"]  # finance domains first
    assert items[0]["sentiment"]["label"] == "positive" and items[1]["sentiment"]["label"] == "negative"
    assert set(items[0]) == {"title", "url", "domain", "snippet", "publishedAt", "sentiment"}
    assert 0 <= items[0]["sentiment"]["score"] <= 1
    assert news.finance_query("HDFC Bank").endswith("stock market news")

    async def down(query, max_results=6):
        return web.SearchResults(error="Web search is unavailable right now")

    cache.clear()
    monkeypatch.setattr(web, "web_search", down)
    r = client.get("/api/market/news?query=HDFC%20Bank", headers=user["headers"])
    assert r.status_code == 503 and r.json()["detail"] == "Web search is unavailable right now"


def test_sentiment_backend_falls_back_to_lexicon():
    assert sentiment.lexicon("Profit surges to a record high")[0] == "positive"
    assert sentiment.lexicon("Shares plunge after fraud probe")[0] == "negative"
    assert sentiment.lexicon("The board will meet on Monday")[0] == "neutral"
    labels = sentiment.label_many(["Stock rallies on upgrade", "Company reports loss"])
    assert [set(x) for x in labels] == [{"label", "score"}] * 2
    assert sentiment.backend_name()


def test_unknown_symbol_from_yfinance_is_a_404_without_retries(client, user, monkeypatch):
    """yfinance raises KeyError('currentTradingPeriod') from fast_info for unknown tickers: map it to 404."""
    import sys
    import types

    tickers: list[str] = []

    class FastInfo:
        def __getattr__(self, name):
            raise KeyError("currentTradingPeriod")

    class History:
        Close: list = []

    class Ticker:
        def __init__(self, symbol):
            tickers.append(symbol)
            self.fast_info = FastInfo()

        def history(self, period="5d"):
            return History()

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=Ticker))
    monkeypatch.setattr(cache, "BACKOFF_S", 0)
    r = client.get("/api/market/quote?symbol=NOTAREALTICKERX", headers=user["headers"])
    assert r.status_code == 404 and "No market data found for NOTAREALTICKERX" in r.json()["detail"]
    assert tickers == ["NOTAREALTICKERX"]  # a bad symbol is not retried


def test_a_cancelled_leader_does_not_cancel_callers_sharing_its_fetch():
    """The chat's 45 s guard (or a closed tab) cancels the fetching caller: the others get a MarketError, not a
    CancelledError that would end their SSE stream without a done/error event."""
    fetches: list[int] = []

    async def hang():
        fetches.append(1)
        await asyncio.sleep(5)

    async def scenario():
        leader = asyncio.create_task(cache.cached("quote:HANG", 60, hang))
        while not fetches:
            await asyncio.sleep(0.01)
        follower = asyncio.create_task(cache.cached("quote:HANG", 60, hang))
        await asyncio.sleep(0.3)  # the follower reads the (empty) cache in a thread, then joins the leader's fetch
        leader.cancel()
        with pytest.raises(cache.MarketError):
            await follower
        assert leader.cancelled() and fetches == [1]

    asyncio.run(scenario())


def test_a_timeout_is_not_retried(monkeypatch):
    monkeypatch.setattr(cache, "BACKOFF_S", 0)
    monkeypatch.setattr(quotes, "FETCH_TIMEOUT_S", 0.05)
    calls: list[str] = []

    def slow(symbol):
        calls.append(symbol)
        import time

        time.sleep(0.3)

    monkeypatch.setattr(quotes, "_fetch_quote_sync", slow)
    with pytest.raises(cache.MarketError, match="took too long"):
        asyncio.run(service.get_quote("AAPL"))
    assert calls == ["AAPL"]

    async def search_hangs(query, limit):
        calls.append(query)
        raise asyncio.TimeoutError

    monkeypatch.setattr(symbols, "_run_search", search_hangs)
    assert asyncio.run(symbols.search_symbols("zzqx")) == []  # bundled list only, after a single attempt
    assert calls == ["AAPL", "zzqx"]
