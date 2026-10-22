"""A bundled list of ~150 common Indian (NSE) and US tickers for symbol search and mention detection."""
from __future__ import annotations

import re
from dataclasses import dataclass

NSE = "NSE"
BSE = "BSE"
NASDAQ = "NASDAQ"
NYSE = "NYSE"
INDEX = "INDEX"
FX = "FX"
CRYPTO = "CRYPTO"


@dataclass(frozen=True)
class Symbol:
    symbol: str
    name: str
    exchange: str
    aliases: tuple[str, ...] = ()


def _n(symbol: str, name: str, *aliases: str) -> Symbol:
    return Symbol(f"{symbol}.NS", name, NSE, aliases)


def _us(symbol: str, name: str, exchange: str, *aliases: str) -> Symbol:
    return Symbol(symbol, name, exchange, aliases)


SYMBOLS: list[Symbol] = [
    # ── NSE large caps ──
    _n("RELIANCE", "Reliance Industries", "reliance", "ril"), _n("TCS", "Tata Consultancy Services", "tcs"),
    _n("HDFCBANK", "HDFC Bank", "hdfc bank", "hdfc"), _n("ICICIBANK", "ICICI Bank", "icici bank", "icici"),
    _n("INFY", "Infosys", "infosys", "infy"), _n("SBIN", "State Bank of India", "sbi", "state bank"),
    _n("BHARTIARTL", "Bharti Airtel", "airtel", "bharti"), _n("ITC", "ITC", "itc"),
    _n("LT", "Larsen & Toubro", "l&t", "larsen"), _n("HINDUNILVR", "Hindustan Unilever", "hul", "hindustan unilever"),
    _n("KOTAKBANK", "Kotak Mahindra Bank", "kotak"), _n("AXISBANK", "Axis Bank", "axis bank", "axis"),
    _n("BAJFINANCE", "Bajaj Finance", "bajaj finance"), _n("BAJAJFINSV", "Bajaj Finserv", "bajaj finserv"),
    _n("MARUTI", "Maruti Suzuki", "maruti"), _n("TATAMOTORS", "Tata Motors", "tata motors"),
    _n("TATASTEEL", "Tata Steel", "tata steel"), _n("TITAN", "Titan Company", "titan"),
    _n("ASIANPAINT", "Asian Paints", "asian paints"), _n("SUNPHARMA", "Sun Pharmaceutical", "sun pharma"),
    _n("WIPRO", "Wipro", "wipro"), _n("HCLTECH", "HCL Technologies", "hcl", "hcl tech"),
    _n("TECHM", "Tech Mahindra", "tech mahindra"), _n("ULTRACEMCO", "UltraTech Cement", "ultratech"),
    _n("NTPC", "NTPC", "ntpc"), _n("POWERGRID", "Power Grid Corporation", "power grid"),
    _n("ONGC", "Oil & Natural Gas Corporation", "ongc"), _n("COALINDIA", "Coal India", "coal india"),
    _n("ADANIENT", "Adani Enterprises", "adani enterprises", "adani"), _n("ADANIPORTS", "Adani Ports", "adani ports"),
    _n("ADANIGREEN", "Adani Green Energy", "adani green"), _n("ADANIPOWER", "Adani Power", "adani power"),
    _n("JSWSTEEL", "JSW Steel", "jsw steel", "jsw"), _n("HINDALCO", "Hindalco Industries", "hindalco"),
    _n("NESTLEIND", "Nestle India", "nestle"), _n("BRITANNIA", "Britannia Industries", "britannia"),
    _n("DABUR", "Dabur India", "dabur"), _n("MARICO", "Marico", "marico"),
    _n("DRREDDY", "Dr. Reddy's Laboratories", "dr reddy", "dr reddys", "dr. reddy's"), _n("CIPLA", "Cipla", "cipla"),
    _n("DIVISLAB", "Divi's Laboratories", "divis", "divi's"), _n("APOLLOHOSP", "Apollo Hospitals", "apollo hospitals"),
    _n("BAJAJ-AUTO", "Bajaj Auto", "bajaj auto"), _n("HEROMOTOCO", "Hero MotoCorp", "hero motocorp", "hero"),
    _n("EICHERMOT", "Eicher Motors", "eicher", "royal enfield"), _n("M&M", "Mahindra & Mahindra", "mahindra", "m&m"),
    _n("TVSMOTOR", "TVS Motor", "tvs motor", "tvs"), _n("GRASIM", "Grasim Industries", "grasim"),
    _n("SHREECEM", "Shree Cement", "shree cement"), _n("INDUSINDBK", "IndusInd Bank", "indusind"),
    _n("SBILIFE", "SBI Life Insurance", "sbi life"), _n("HDFCLIFE", "HDFC Life Insurance", "hdfc life"),
    _n("ICICIPRULI", "ICICI Prudential Life", "icici prudential"), _n("ICICIGI", "ICICI Lombard", "icici lombard"),
    _n("LICI", "Life Insurance Corporation", "lic"), _n("BPCL", "Bharat Petroleum", "bpcl"),
    _n("IOC", "Indian Oil Corporation", "indian oil", "ioc"), _n("GAIL", "GAIL India", "gail"),
    _n("TATAPOWER", "Tata Power", "tata power"), _n("TATACONSUM", "Tata Consumer Products", "tata consumer"),
    _n("PIDILITIND", "Pidilite Industries", "pidilite"), _n("HAVELLS", "Havells India", "havells"),
    _n("SIEMENS", "Siemens India", "siemens"), _n("ABB", "ABB India", "abb"),
    _n("BEL", "Bharat Electronics", "bel", "bharat electronics"), _n("HAL", "Hindustan Aeronautics", "hal"),
    _n("DLF", "DLF", "dlf"), _n("GODREJPROP", "Godrej Properties", "godrej properties"),
    _n("ZOMATO", "Eternal (Zomato)", "zomato", "eternal"), _n("PAYTM", "One97 Communications (Paytm)", "paytm"),
    _n("NYKAA", "FSN E-Commerce (Nykaa)", "nykaa"), _n("POLICYBZR", "PB Fintech (Policybazaar)", "policybazaar"),
    _n("IRCTC", "IRCTC", "irctc"), _n("INDIGO", "InterGlobe Aviation (IndiGo)", "indigo"),
    _n("VEDL", "Vedanta", "vedanta"), _n("JIOFIN", "Jio Financial Services", "jio financial", "jio"),
    _n("PNB", "Punjab National Bank", "pnb"), _n("BANKBARODA", "Bank of Baroda", "bank of baroda", "bob"),
    _n("CANBK", "Canara Bank", "canara"), _n("IDFCFIRSTB", "IDFC First Bank", "idfc first"),
    _n("YESBANK", "Yes Bank", "yes bank"), _n("FEDERALBNK", "Federal Bank", "federal bank"),
    _n("MOTHERSON", "Samvardhana Motherson", "motherson"), _n("ASHOKLEY", "Ashok Leyland", "ashok leyland"),
    _n("AMBUJACEM", "Ambuja Cements", "ambuja"), _n("ACC", "ACC", "acc cement"),
    _n("LTIM", "LTIMindtree", "ltimindtree", "mindtree"), _n("PERSISTENT", "Persistent Systems", "persistent"),
    _n("COFORGE", "Coforge", "coforge"), _n("MPHASIS", "Mphasis", "mphasis"),
    _n("TRENT", "Trent", "trent", "westside"), _n("DMART", "Avenue Supermarts (DMart)", "dmart", "avenue supermarts"),
    _n("VBL", "Varun Beverages", "varun beverages"), _n("COLPAL", "Colgate-Palmolive India", "colgate"),
    _n("BOSCHLTD", "Bosch", "bosch"), _n("CHOLAFIN", "Cholamandalam Investment", "chola", "cholamandalam"),
    _n("MUTHOOTFIN", "Muthoot Finance", "muthoot"), _n("SHRIRAMFIN", "Shriram Finance", "shriram"),
    _n("RECLTD", "REC", "rec ltd"), _n("PFC", "Power Finance Corporation", "pfc"),
    _n("IRFC", "Indian Railway Finance Corporation", "irfc"), _n("NHPC", "NHPC", "nhpc"),
    _n("SUZLON", "Suzlon Energy", "suzlon"), _n("TATAELXSI", "Tata Elxsi", "tata elxsi"),
    _n("ZEEL", "Zee Entertainment", "zee"), _n("PVRINOX", "PVR INOX", "pvr"),
    _n("NAUKRI", "Info Edge (Naukri)", "naukri", "info edge"), _n("MCDOWELL-N", "United Spirits", "united spirits"),
    # ── indices, FX, commodities, crypto (yfinance symbols) ──
    Symbol("^NSEI", "NIFTY 50", INDEX, ("nifty", "nifty 50", "nifty50")),
    Symbol("^BSESN", "S&P BSE SENSEX", INDEX, ("sensex", "bse sensex")),
    Symbol("^NSEBANK", "NIFTY Bank", INDEX, ("bank nifty", "banknifty", "nifty bank")),
    Symbol("^CNXIT", "NIFTY IT", INDEX, ("nifty it",)),
    Symbol("^GSPC", "S&P 500", INDEX, ("s&p 500", "s&p", "sp500")), Symbol("^DJI", "Dow Jones Industrial Average", INDEX, ("dow", "dow jones")),
    Symbol("^IXIC", "NASDAQ Composite", INDEX, ("nasdaq",)), Symbol("^FTSE", "FTSE 100", INDEX, ("ftse",)),
    Symbol("^N225", "Nikkei 225", INDEX, ("nikkei",)), Symbol("^HSI", "Hang Seng", INDEX, ("hang seng",)),
    Symbol("USDINR=X", "US Dollar / Indian Rupee", FX, ("usd to inr", "usd inr", "dollar rate", "usd/inr", "dollar to rupee")),
    Symbol("EURINR=X", "Euro / Indian Rupee", FX, ("eur to inr", "euro to inr", "eur/inr")),
    Symbol("GBPINR=X", "British Pound / Indian Rupee", FX, ("gbp to inr", "pound to inr", "gbp/inr")),
    Symbol("EURUSD=X", "Euro / US Dollar", FX, ("eur usd", "eur/usd", "euro to dollar")),
    Symbol("GC=F", "Gold futures (USD/oz)", "COMMODITY", ("gold", "gold price")),
    Symbol("SI=F", "Silver futures (USD/oz)", "COMMODITY", ("silver", "silver price")),
    Symbol("CL=F", "Crude oil WTI futures", "COMMODITY", ("crude", "crude oil", "oil price")),
    Symbol("BTC-USD", "Bitcoin", CRYPTO, ("bitcoin", "btc")), Symbol("ETH-USD", "Ethereum", CRYPTO, ("ethereum", "eth")),
    # ── US large caps ──
    _us("AAPL", "Apple", NASDAQ, "apple"), _us("MSFT", "Microsoft", NASDAQ, "microsoft"),
    _us("GOOGL", "Alphabet (Google)", NASDAQ, "google", "alphabet"), _us("AMZN", "Amazon", NASDAQ, "amazon"),
    _us("NVDA", "NVIDIA", NASDAQ, "nvidia"), _us("META", "Meta Platforms", NASDAQ, "meta", "facebook"),
    _us("TSLA", "Tesla", NASDAQ, "tesla"), _us("BRK-B", "Berkshire Hathaway", NYSE, "berkshire"),
    _us("JPM", "JPMorgan Chase", NYSE, "jpmorgan", "jp morgan"), _us("V", "Visa", NYSE, "visa"),
    _us("MA", "Mastercard", NYSE, "mastercard"), _us("JNJ", "Johnson & Johnson", NYSE, "johnson & johnson"),
    _us("WMT", "Walmart", NYSE, "walmart"), _us("PG", "Procter & Gamble", NYSE, "procter"),
    _us("XOM", "ExxonMobil", NYSE, "exxon"), _us("UNH", "UnitedHealth", NYSE, "unitedhealth"),
    _us("HD", "Home Depot", NYSE, "home depot"), _us("KO", "Coca-Cola", NYSE, "coca cola", "coke"),
    _us("PEP", "PepsiCo", NASDAQ, "pepsi"), _us("NFLX", "Netflix", NASDAQ, "netflix"),
    _us("AMD", "Advanced Micro Devices", NASDAQ, "amd"), _us("INTC", "Intel", NASDAQ, "intel"),
    _us("ORCL", "Oracle", NYSE, "oracle"), _us("CRM", "Salesforce", NYSE, "salesforce"),
    _us("ADBE", "Adobe", NASDAQ, "adobe"), _us("IBM", "IBM", NYSE, "ibm"),
    _us("CSCO", "Cisco", NASDAQ, "cisco"), _us("QCOM", "Qualcomm", NASDAQ, "qualcomm"),
    _us("BAC", "Bank of America", NYSE, "bank of america"), _us("GS", "Goldman Sachs", NYSE, "goldman"),
    _us("MS", "Morgan Stanley", NYSE, "morgan stanley"), _us("C", "Citigroup", NYSE, "citi", "citigroup"),
    _us("DIS", "Walt Disney", NYSE, "disney"), _us("NKE", "Nike", NYSE, "nike"),
    _us("MCD", "McDonald's", NYSE, "mcdonalds", "mcdonald's"), _us("SBUX", "Starbucks", NASDAQ, "starbucks"),
    _us("BA", "Boeing", NYSE, "boeing"), _us("CAT", "Caterpillar", NYSE, "caterpillar"),
    _us("PFE", "Pfizer", NYSE, "pfizer"), _us("LLY", "Eli Lilly", NYSE, "eli lilly", "lilly"),
    _us("ABNB", "Airbnb", NASDAQ, "airbnb"), _us("UBER", "Uber", NYSE, "uber"),
    _us("PYPL", "PayPal", NASDAQ, "paypal"), _us("SHOP", "Shopify", NASDAQ, "shopify"),
    _us("COIN", "Coinbase", NASDAQ, "coinbase"), _us("PLTR", "Palantir", NASDAQ, "palantir"),
    _us("AVGO", "Broadcom", NASDAQ, "broadcom"), _us("TSM", "Taiwan Semiconductor", NYSE, "tsmc"),
    _us("INFY", "Infosys ADR", NYSE), _us("WIT", "Wipro ADR", NYSE), _us("HDB", "HDFC Bank ADR", NYSE),
    _us("IBN", "ICICI Bank ADR", NYSE), _us("SPY", "SPDR S&P 500 ETF", "ETF", "spy"),
    _us("QQQ", "Invesco QQQ (Nasdaq-100 ETF)", "ETF", "qqq"), _us("VOO", "Vanguard S&P 500 ETF", "ETF", "voo"),
]

_BY_SYMBOL = {s.symbol.upper(): s for s in SYMBOLS}
_ALIAS_INDEX: list[tuple[str, Symbol]] = sorted(
    ((alias.lower(), s) for s in SYMBOLS for alias in (*s.aliases, s.name.lower())),
    key=lambda item: -len(item[0]),
)
_WORD = re.compile(r"[a-z0-9&.'/-]+")
_EXPLICIT = re.compile(r"(?:\b([A-Z]{3,6}=X|[A-Z]{2,5}-USD|[A-Z][A-Z0-9&-]{1,11}(?:\.(?:NS|BO))?)\b"
                       r"|(?<!\S)(\^[A-Z0-9]{2,8})\b)")
_GENERIC_UPPER = {"I", "A", "EMI", "SIP", "FD", "RD", "PPF", "NPS", "GST", "ITR", "TDS", "LPA", "INR", "USD", "EUR",
                  "UPI", "NEFT", "IMPS", "RTGS", "ATM", "PAN", "KYC", "IPO", "ETF", "NAV", "PE", "EPS", "ROE", "ROI",
                  "EBITDA", "EBIT", "P&L", "CAGR", "XIRR", "FY", "AY", "NSE", "BSE", "SEBI", "RBI", "OK", "AI", "US",
                  "UK", "EU", "HRA", "LTCG", "STCG", "CIBIL", "MF", "ELSS", "ULIP", "DIY", "CEO", "CFO", "Q1", "Q2",
                  "Q3", "Q4", "YTD", "YOY", "QOQ", "VS", "THE", "AND", "OR", "NOT", "ASAP", "TV", "PC", "ID"}


def lookup(symbol: str) -> Symbol | None:
    return _BY_SYMBOL.get(symbol.strip().upper())


def search(query: str, limit: int = 8) -> list[Symbol]:
    """Prefix / substring search over symbols, names and aliases (bundled list only; no network)."""
    q = " ".join(query.lower().split())
    if not q:
        return []
    scored: list[tuple[int, Symbol]] = []
    seen: set[str] = set()
    for s in SYMBOLS:
        keys = [s.symbol.lower(), s.symbol.lower().split(".")[0], s.name.lower(), *s.aliases]
        score = 0
        for k in keys:
            if k == q:
                score = max(score, 100)
            elif k.startswith(q):
                score = max(score, 80 - min(20, len(k) - len(q)))
            elif q in k:
                score = max(score, 50)
            elif all(w in k for w in q.split()):
                score = max(score, 40)
        if score and s.symbol not in seen:
            seen.add(s.symbol)
            scored.append((score, s))
    scored.sort(key=lambda item: (-item[0], item[1].symbol))
    return [s for _, s in scored[:limit]]


def mentions(text: str, limit: int = 3) -> list[Symbol]:
    """Symbols mentioned in free text: explicit tickers (TCS.NS, AAPL, ^NSEI) and known names/aliases."""
    found: list[Symbol] = []
    seen: set[str] = set()
    for plain, index in _EXPLICIT.findall(text or ""):
        token = (plain or index).upper()
        if token in _GENERIC_UPPER:
            continue
        s = lookup(token) or lookup(token + ".NS")
        if s is None and ("." in token or token.startswith("^") or token.endswith(("=X", "-USD"))):
            s = Symbol(token, token, "UNKNOWN")
        if s is not None and s.symbol not in seen:
            seen.add(s.symbol)
            found.append(s)
    lowered = " " + " ".join(_WORD.findall((text or "").lower())) + " "
    for alias, s in _ALIAS_INDEX:
        if s.symbol in seen or len(alias) < 3:
            continue
        if f" {alias} " in lowered or (len(alias) > 5 and alias in lowered):
            seen.add(s.symbol)
            found.append(s)
        if len(found) >= limit:
            break
    return found[:limit]


def _yf_search_sync(query: str, limit: int) -> list[Symbol]:
    """yfinance's symbol search (network); malformed entries are skipped."""
    import yfinance as yf

    out: list[Symbol] = []
    for q in (yf.Search(query, max_results=limit, news_count=0).quotes or []):
        symbol = str(q.get("symbol") or "").strip().upper()
        if not symbol or q.get("quoteType") in ("OPTION", "FUTURE"):
            continue
        name = str(q.get("shortname") or q.get("longname") or symbol)
        exchange = str(q.get("exchDisp") or q.get("exchange") or "UNKNOWN")
        out.append(Symbol(symbol, name, exchange))
    return out


async def search_symbols(query: str, limit: int = 8, min_bundled: int = 3) -> list[Symbol]:
    """Bundled matches first; when they are few, yfinance's lookup fills the rest (cached, failures ignored)."""
    import asyncio

    from app.features.market.cache import cached

    found = search(query, limit)
    if len(found) >= min_bundled:
        return found
    q = " ".join(query.lower().split())
    try:
        raw, _ = await cached(f"symsearch:{q}", 3600.0, lambda: _run_search(q, limit))
    except Exception:  # noqa: BLE001 — the bundled list is always enough to answer
        return found
    seen = {s.symbol for s in found}
    for item in raw:
        if item["symbol"] not in seen:
            seen.add(item["symbol"])
            found.append(Symbol(item["symbol"], item["name"], item["exchange"]))
    return found[:limit]


async def _run_search(query: str, limit: int) -> list[dict[str, str]]:
    import asyncio

    results = await asyncio.wait_for(asyncio.to_thread(_yf_search_sync, query, limit), 15.0)
    return [{"symbol": s.symbol, "name": s.name, "exchange": s.exchange} for s in results]


def normalise(symbol: str) -> str:
    """Upper-case; bare Indian names get the NSE suffix ("tcs" → "TCS.NS")."""
    s = symbol.strip().upper()
    if not s:
        return s
    if s in _BY_SYMBOL:
        return s
    if f"{s}.NS" in _BY_SYMBOL:
        return f"{s}.NS"
    for alias, sym in _ALIAS_INDEX:
        if alias == symbol.strip().lower():
            return sym.symbol
    return s
