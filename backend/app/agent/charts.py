"""Chart specs built from computed figures (never from model output), appended to answers as ```chart blocks.

A spec is the JSON the chat renders with recharts: {type: bar | line | area | pie, title, unit, labels,
series: [{name, data}]}. Every number comes from the pandas analytics or the market service, so a chart can be
trusted as much as the table next to it. The model may also write a chart block itself (the prompt allows it when
the numbers are in the sources); verify only appends ours when the answer has none.
"""
from __future__ import annotations

import json
from typing import Any

from app.features.finance.money import month_label

MAX_SLICES = 6       # pie: the top categories, the rest as "Other"
MAX_BARS = 12        # bars / months shown
MAX_POINTS = 60      # line: price history is down-sampled to this many points
MAX_PER_ANSWER = 2
_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def _unit(currency: str | None, scale: str | None = None) -> str:
    symbol = _SYMBOLS.get((currency or "").upper(), currency or "")
    return f"{symbol} {scale}".strip() if scale else symbol


def _round(value: float) -> float:
    return round(float(value), 2)


def _spending_pie(report: dict[str, Any]) -> dict[str, Any] | None:
    rows = [c for c in report.get("byCategory") or [] if c.get("amount")]
    if len(rows) < 2:
        return None
    rows = sorted(rows, key=lambda c: abs(c["amount"]), reverse=True)
    top, rest = rows[:MAX_SLICES], rows[MAX_SLICES:]
    labels = [str(c["category"]) for c in top]
    data = [_round(abs(c["amount"])) for c in top]
    if rest:
        labels.append("Other")
        data.append(_round(sum(abs(c["amount"]) for c in rest)))
    return {"type": "pie", "title": "Spending by category", "unit": _unit(report.get("currency")),
            "labels": labels, "series": [{"name": "Spent", "data": data}]}


def _monthly_bars(report: dict[str, Any]) -> dict[str, Any] | None:
    months = (report.get("byMonth") or [])[-MAX_BARS:]
    if len(months) < 2:
        return None
    return {"type": "bar", "title": "Money in and out by month", "unit": _unit(report.get("currency")),
            "labels": [month_label(m["month"]) for m in months],
            "series": [{"name": "In", "data": [_round(m["inflow"]) for m in months]},
                       {"name": "Out", "data": [_round(abs(m["outflow"])) for m in months]}]}


def _balance_bars(report: dict[str, Any]) -> dict[str, Any] | None:
    sheet = report.get("balanceSheet") or {}
    pairs = [(label, sheet.get(key)) for label, key in
             (("Total assets", "totalAssets"), ("Total liabilities", "totalLiabilities"), ("Equity", "equity"))]
    pairs = [(label, value) for label, value in pairs if value is not None]
    if len(pairs) < 2:
        return None
    return {"type": "bar", "title": "Balance sheet", "unit": _unit(report.get("currency"), report.get("amountUnit")),
            "labels": [label for label, _ in pairs], "series": [{"name": "Amount", "data": [_round(v) for _, v in pairs]}]}


def _category_bars(report: dict[str, Any]) -> dict[str, Any] | None:
    rows = [c for c in report.get("byCategory") or [] if c.get("amount")][:MAX_BARS]
    if len(rows) < 2:
        return None
    return {"type": "bar", "title": "By category", "unit": _unit(report.get("currency")),
            "labels": [str(c["category"]) for c in rows],
            "series": [{"name": "Amount", "data": [_round(c["amount"]) for c in rows]}]}


def _pnl_bars(report: dict[str, Any]) -> dict[str, Any] | None:
    """Revenue → expenses → profit, this year next to the previous one when the statement has both."""
    pnl = report.get("profitLoss") or {}
    keys = [("Revenue", "revenue", "previousRevenue"), ("Total expenses", "totalExpenses", "previousTotalExpenses"),
            ("EBITDA", "ebitda", "previousEbitda"), ("Net profit", "netProfit", "previousNetProfit")]
    rows = [(label, pnl.get(key), pnl.get(prev) if prev else None) for label, key, prev in keys
            if pnl.get(key) is not None]
    if len(rows) < 2:
        return None
    series = [{"name": pnl.get("period") or "This year", "data": [_round(v) for _, v, _ in rows]}]
    if all(p is not None for *_, p in rows):
        series.append({"name": pnl.get("previousPeriod") or "Previous year", "data": [_round(p) for *_, p in rows]})
    return {"type": "bar", "title": "Profit and loss", "unit": _unit(report.get("currency"), report.get("amountUnit")),
            "labels": [label for label, *_ in rows], "series": series}


def report_charts(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Up to two charts for one analysed file, most useful first."""
    kind = report.get("kind")
    pnl = _pnl_bars(report) if report.get("profitLoss") else None
    if kind == "bank_statement":
        found = [_spending_pie(report), _monthly_bars(report)]
    elif kind == "balance_sheet":
        found = [pnl, _balance_bars(report), _category_bars(report)]
    else:
        found = [pnl, _category_bars(report)]
    return [c for c in found if c][:MAX_PER_ANSWER]


def history_chart(history: dict[str, Any]) -> dict[str, Any] | None:
    points = history.get("points") or []
    if len(points) < 2:
        return None
    step = max(1, -(-len(points) // MAX_POINTS))
    sample = points[::step]
    if sample[-1] is not points[-1]:
        sample.append(points[-1])
    unit = "₹" if str(history.get("symbol", "")).upper().endswith((".NS", ".BO")) else ""
    return {"type": "line", "title": f"{history['symbol']} closing price ({history.get('period', '')})",
            "unit": unit, "labels": [str(p["date"])[:10] for p in sample],
            "series": [{"name": "Close", "data": [_round(p["close"]) for p in sample]}]}


def fence(spec: dict[str, Any]) -> str:
    return "```chart\n" + json.dumps(spec, ensure_ascii=False, separators=(",", ":")) + "\n```"


def has_chart(answer: str) -> bool:
    return "```chart" in answer


def charts_block(specs: list[dict[str, Any]]) -> str:
    return "\n\n".join(fence(s) for s in specs[:MAX_PER_ANSWER])
