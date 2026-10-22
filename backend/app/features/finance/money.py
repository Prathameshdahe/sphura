"""Money / date formatting for insights and summaries (Indian digit grouping for INR)."""
from __future__ import annotations

from datetime import date

SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def _indian_group(whole: int) -> str:
    s = str(whole)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def money(value: float | None, currency: str | None, decimals: int | None = None) -> str:
    """₹1,23,456 / $4,610,000 / 1,234.50 — whole units from 1,000 up, 2 decimals below."""
    if value is None:
        return "—"
    places = decimals if decimals is not None else (0 if abs(value) >= 1000 else 2)
    x = round(abs(value), places)  # round first so 999.999 → 1,000.00 and -0.001 → 0.00 (no "-0.00")
    negative = value < 0 and x > 0
    if currency == "INR":
        whole = int(x)
        text = _indian_group(whole)
        if places:
            text += f"{x - whole:.{places}f}"[1:]
    else:
        text = f"{x:,.{places}f}"
    symbol = SYMBOLS.get(currency or "")
    prefix = symbol if symbol else (f"{currency} " if currency else "")
    return f"{'-' if negative else ''}{prefix}{text}"


def signed_money(value: float, currency: str | None) -> str:
    return ("+" if value > 0 else "") + money(value, currency)


def month_label(month: str) -> str:
    """'2026-04' → 'Apr 2026'."""
    try:
        year, mon = month.split("-")
        return date(int(year), int(mon), 1).strftime("%b %Y")
    except (ValueError, TypeError):
        return month


def period_label(start: str, end: str) -> str:
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        return f"{start} to {end}"
    if a.year == b.year:
        return f"{a.day} {a:%b} – {b.day} {b:%b %Y}"
    return f"{a.day} {a:%b %Y} – {b.day} {b:%b %Y}"


def pct(part: float, whole: float) -> str:
    return f"{part / whole:.0%}" if whole else "—"
