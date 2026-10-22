"""Profit and loss statement: find the P&L lines (revenue, expenses, profit before / after tax) in a table, compute
margins and year-on-year growth, and, with a balance sheet from the same workbook, ROE / ROA / interest cover.

Works on Schedule III statements ("Revenue from operations", "Profit for the year") and simple MSME ones ("Sales",
"Net profit"). The amount column is the latest year's (same rule as the balance sheet); the next most recent year,
when present, gives the growth figures.
"""
from __future__ import annotations

import re

from app.features.finance.balance import _NOT_AMOUNT, _YEAR
from app.features.finance.money import money
from app.features.finance.parsing import Table, numeric_share, parse_amount

# first match wins, so the specific lines come before the generic ones ("total income" before "income")
_LINES: list[tuple[str, re.Pattern[str]]] = [
    ("totalIncome", re.compile(r"^total (income|revenue)\b")),
    ("totalExpenses", re.compile(r"^total expen")),
    ("otherIncome", re.compile(r"^other (operating )?income\b")),
    ("revenue", re.compile(r"^(net )?(revenue|sales|turnover)\b|^income from operations|^gross receipts")),
    ("profitBeforeTax", re.compile(r"profit\s*(/\s*\(?loss\)?)?\s*before\s*(exceptional.*)?tax|^pbt\b")),
    ("tax", re.compile(r"^(total )?tax expense|^(current )?tax\b|^income[- ]tax|^provision for (income )?tax")),
    ("netProfit", re.compile(r"(profit|loss)\s*(/\s*\(?loss\)?)?\s*(for|of) the (year|period)|^net profit|"
                             r"profit after tax|^pat\b")),
    ("financeCosts", re.compile(r"^finance cost|^interest( expense| paid| cost|$)")),
    ("depreciation", re.compile(r"depreciation")),
]
_REVENUE_HINT = re.compile(r"revenue|sales|turnover|income from operations|gross receipts")
_PROFIT_LINE = re.compile(r"profit|loss")


def _label(row: list, text_cols: list[int]) -> str:
    return " ".join(str(row[i]).strip() for i in text_cols if row[i] is not None).lower()


def _year_columns(table: Table) -> list[int]:
    """Numeric columns, most recent year first (columns without a year keep their left-to-right order)."""
    found = []
    for i, head in enumerate(table.header):
        if _NOT_AMOUNT.search(str(head or "").lower()):
            continue
        if numeric_share([row[i] for row in table.rows]) >= 0.6:
            years = [int(y) for y in _YEAR.findall(str(head or ""))]
            found.append((max(years) if years else -1, -i, i))
    return [i for *_, i in sorted(found, reverse=True)]


def _text_cols(table: Table, numeric: list[int]) -> list[int]:
    cols = []
    for i in range(len(table.header)):
        values = [row[i] for row in table.rows if row[i] is not None]
        if i not in numeric and values and numeric_share(values) < 0.5:
            cols.append(i)
    return cols[:1]


def looks_like_pnl(table: Table) -> bool:
    numeric = _year_columns(table)
    text = _text_cols(table, numeric)
    if not numeric or not text:
        return False
    labels = [_label(row, text) for row in table.rows]
    # a revenue line plus a profit / loss line (a balance sheet has "profit" in reserves but no revenue line)
    return any(_REVENUE_HINT.search(t) for t in labels) and any(_PROFIT_LINE.search(t) for t in labels)


def _lines(table: Table, column: int, text: list[int]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in table.rows:
        label = _label(row, text)
        value = parse_amount(row[column])[0] if column < len(row) else None
        if not label or value is None:
            continue
        for key, pattern in _LINES:
            if pattern.search(label):
                out.setdefault(key, value)
                break
    return out


def _ratio(a: float | None, b: float | None) -> float | None:
    return round(a / b, 4) if a is not None and b else None


def _complete(v: dict[str, float]) -> dict[str, float | None]:
    revenue = v.get("revenue")
    total_income = v.get("totalIncome") or (revenue + v.get("otherIncome", 0.0) if revenue is not None else None)
    pbt = v.get("profitBeforeTax")
    net = v.get("netProfit")
    if net is None and pbt is not None and "tax" in v:
        net = pbt - v["tax"]
    expenses = v.get("totalExpenses")
    if expenses is None and total_income is not None and pbt is not None:
        expenses = total_income - pbt
    ebitda = None
    if pbt is not None and {"financeCosts", "depreciation"} <= v.keys():
        ebitda = pbt + v["financeCosts"] + v["depreciation"]
    return {"revenue": revenue, "otherIncome": v.get("otherIncome"), "totalIncome": total_income,
            "totalExpenses": expenses, "ebitda": ebitda, "financeCosts": v.get("financeCosts"),
            "depreciation": v.get("depreciation"), "profitBeforeTax": pbt, "tax": v.get("tax"), "netProfit": net}


def analyze_pnl(table: Table) -> dict | None:
    """The P&L figures for the latest year (and growth against the previous one), or None."""
    numeric = _year_columns(table)
    text = _text_cols(table, numeric)
    if not numeric or not text:
        return None
    now = _complete(_lines(table, numeric[0], text))
    if now["revenue"] is None or (now["netProfit"] is None and now["profitBeforeTax"] is None):
        return None
    before = _complete(_lines(table, numeric[1], text)) if len(numeric) > 1 else {}
    revenue, net = now["revenue"], now["netProfit"]

    def growth(key: str) -> float | None:
        old = before.get(key)
        return round((now[key] - old) / abs(old), 4) if now.get(key) is not None and old else None

    return {
        **{k: (round(x, 2) if x is not None else None) for k, x in now.items()},
        "period": str(table.header[numeric[0]] or "").strip() or None,
        "previousPeriod": (str(table.header[numeric[1]] or "").strip() or None) if len(numeric) > 1 else None,
        "netMargin": _ratio(net, revenue),
        "ebitdaMargin": _ratio(now["ebitda"], revenue),
        "revenueGrowth": growth("revenue"),
        "profitGrowth": growth("netProfit"),
        "previousRevenue": before.get("revenue"),
        "previousTotalExpenses": before.get("totalExpenses"),
        "previousEbitda": before.get("ebitda"),
        "previousNetProfit": before.get("netProfit"),
        "interestCoverage": _ratio((now["profitBeforeTax"] or 0) + (now["financeCosts"] or 0), now["financeCosts"])
        if now["profitBeforeTax"] is not None else None,
        "returnOnEquity": None,
        "returnOnAssets": None,
    }


def link_balance_sheet(pnl: dict, sheet: dict | None) -> None:
    """ROE / ROA when the same workbook has a balance sheet."""
    if not sheet:
        return
    pnl["returnOnEquity"] = _ratio(pnl.get("netProfit"), sheet.get("equity"))
    pnl["returnOnAssets"] = _ratio(pnl.get("netProfit"), sheet.get("totalAssets"))


def _pct(x: float | None) -> str:
    return f"{x:.1%}" if x is not None else "—"


def pnl_insights(pnl: dict, currency: str | None, unit: str | None = None) -> list[str]:
    """`unit` is the scale the statement states ("crore", "lakh"), appended to every amount."""
    def amount(value: float) -> str:
        return money(value, currency) + (f" {unit}" if unit else "")

    out = []
    head = f"Revenue {amount(pnl['revenue'])}"
    if pnl.get("revenueGrowth") is not None:
        head += f", {'up' if pnl['revenueGrowth'] >= 0 else 'down'} {abs(pnl['revenueGrowth']):.1%} on the previous year"
    out.append(head + ".")
    if pnl.get("netProfit") is not None:
        line = f"Net profit {amount(pnl['netProfit'])} (net margin {_pct(pnl.get('netMargin'))})"
        if pnl.get("profitGrowth") is not None:
            line += f", profit {'up' if pnl['profitGrowth'] >= 0 else 'down'} {abs(pnl['profitGrowth']):.1%}"
        out.append(line + ".")
    if pnl.get("ebitdaMargin") is not None:
        out.append(f"EBITDA margin {_pct(pnl['ebitdaMargin'])}.")
    if pnl.get("interestCoverage") is not None:
        cover = pnl["interestCoverage"]
        note = "comfortable" if cover >= 3 else "thin: profits barely cover interest" if cover < 1.5 else "adequate"
        out.append(f"Interest coverage {cover:.1f}x ({note}).")
    if pnl.get("returnOnEquity") is not None:
        out.append(f"Return on equity {_pct(pnl['returnOnEquity'])}; return on assets {_pct(pnl.get('returnOnAssets'))}.")
    return out
