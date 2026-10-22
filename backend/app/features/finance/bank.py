"""Bank statement analytics: signed transactions → totals, months, categories, top transactions, insights."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from app.features.finance.categorize import categorize
from app.features.finance.money import month_label, money, pct, period_label, signed_money
from app.features.finance.parsing import Table, guess_currency, norm_header, numeric_share, parse_amount, parse_dates

TOP_TRANSACTIONS = 10
PER_CATEGORY_TOP = 3
_INFLOW_HINTS = ("Salary", "Refunds", "Interest")
_DEBIT_WORDS = {"dr", "d", "debit", "db", "out", "withdrawal", "w", "expense", "spend"}
_CREDIT_WORDS = {"cr", "c", "credit", "in", "deposit", "income", "receipt"}


@dataclass
class Tx:
    date: date
    description: str
    amount: float  # > 0 money in, < 0 money out
    category: str
    balance: float | None
    order: int


def looks_like_bank(table: Table) -> bool:
    r = table.roles
    if "date" not in r or not ({"debit", "credit", "amount"} & r.keys()):
        return False
    dates, _ = parse_dates([row[r["date"]] for row in table.rows[:500]])
    present = sum(1 for row in table.rows[:500] if row[r["date"]] is not None)
    return present > 0 and sum(d is not None for d in dates) >= 0.5 * present


def _cell(row: list, idx: int | None):  # noqa: ANN202
    return row[idx] if idx is not None and idx < len(row) else None


def _description_index(table: Table) -> int | None:
    if "description" in table.roles:
        return table.roles["description"]
    used = set(table.roles.values())
    best, best_len = None, 0.0
    for i in range(len(table.header)):
        if i in used:
            continue
        values = [row[i] for row in table.rows[:300] if row[i] is not None]
        if not values or numeric_share(values) > 0.5:
            continue
        avg = sum(len(str(v)) for v in values) / len(values)
        if avg > best_len:
            best, best_len = i, avg
    return best


def _signs_from_balance(amounts: list[float | None], balances: list[float | None]) -> list[int] | None:
    """Infer debit/credit from running balance differences (statement oldest- or newest-first)."""
    def score(order: str) -> tuple[int, list[int]]:
        signs, hits = [0] * len(amounts), 0
        for i, a in enumerate(amounts):
            j = i - 1 if order == "asc" else i + 1
            if a is None or not 0 <= j < len(amounts) or balances[i] is None or balances[j] is None:
                continue
            diff = balances[i] - balances[j]
            if abs(abs(diff) - abs(a)) <= max(0.011, abs(a) * 1e-6):
                signs[i] = 1 if diff > 0 else -1
                hits += 1
        return hits, signs

    known = sum(1 for a, b in zip(amounts, balances) if a is not None and b is not None)
    if known < 3:
        return None
    hits, signs = max(score("asc"), score("desc"), key=lambda t: t[0])
    return signs if hits >= 0.7 * (known - 1) else None


def _signed_amounts(table: Table, descriptions: list[str], warnings: list[str]) -> list[float | None]:
    r, rows = table.roles, table.rows
    if "debit" in r or "credit" in r:
        out: list[float | None] = []
        for row in rows:
            debit = parse_amount(_cell(row, r.get("debit")))[0]
            credit = parse_amount(_cell(row, r.get("credit")))[0]
            out.append(None if debit is None and credit is None else abs(credit or 0.0) - abs(debit or 0.0))
        return out

    idx, type_idx = r["amount"], r.get("type")
    values, hints = [], []
    for row in rows:
        v, hint = parse_amount(_cell(row, idx))
        values.append(v)
        hints.append(hint)
    if type_idx is not None:
        out = []
        for v, row in zip(values, rows):
            kind = str(_cell(row, type_idx) or "").strip().lower().rstrip(".")
            if v is None:
                out.append(None)
            elif kind in _DEBIT_WORDS or kind.startswith(("debit", "withdraw", "payment", "purchase")):
                out.append(-abs(v))
            elif kind in _CREDIT_WORDS or kind.startswith(("credit", "deposit", "receipt", "refund")):
                out.append(abs(v))
            else:
                out.append(v)
        return out
    if any(hints):
        return [None if v is None else (h * abs(v) if h else v) for v, h in zip(values, hints)]
    if any(v is not None and v < 0 for v in values):
        return values
    balances = [parse_amount(_cell(row, r.get("balance")))[0] for row in rows] if "balance" in r else []
    signs = _signs_from_balance(values, balances) if balances else None
    if signs:  # the first row has no previous balance: fall back to its description
        return [None if v is None else (s * abs(v) if s else _guess_sign(v, d))
                for v, s, d in zip(values, signs, descriptions)]
    warnings.append("Amounts carry no debit/credit sign; money in was inferred from descriptions "
                    "(salary, refunds, interest) and everything else was treated as spending.")
    return [None if v is None else _guess_sign(v, d) for v, d in zip(values, descriptions)]


def _guess_sign(value: float, description: str) -> float:
    """Unsigned amount: money in for salary / refunds / interest / deposits, otherwise spending."""
    inflow = categorize(description, 1.0) in _INFLOW_HINTS or re.search(r"(?i)\bdeposit|\bcredited\b", description)
    return abs(value) if inflow else -abs(value)


def _transactions(table: Table, warnings: list[str]) -> tuple[list[Tx], str | None, list[str]]:
    r, rows = table.roles, table.rows
    dates, date_note = parse_dates([row[r["date"]] for row in rows])
    desc_idx = _description_index(table)
    descriptions = [" ".join(str(_cell(row, desc_idx) or "").split()) for row in rows]
    amounts = _signed_amounts(table, descriptions, warnings)
    cat_idx = r.get("label") if "categor" in norm_header(table.header[r["label"]] if "label" in r else "") else None
    txs: list[Tx] = []
    skipped = 0
    for i, row in enumerate(rows):
        d, a = dates[i], amounts[i]
        if d is None or a is None or a == 0:
            if any(c is not None for c in row):
                skipped += 1
            continue
        given = str(_cell(row, cat_idx) or "").strip() if cat_idx is not None else ""
        category = given.title() if given else categorize(descriptions[i], a)
        balance = parse_amount(_cell(row, r.get("balance")))[0] if "balance" in r else None
        txs.append(Tx(d, descriptions[i] or "Transaction", round(a, 2), category, balance, i))
    if skipped:
        warnings.append(f"Skipped {skipped} row{'s' if skipped != 1 else ''} without a valid date or amount "
                        "(opening/closing lines, totals or notes).")
    return txs, date_note, descriptions


def analyze_bank(table: Table, warnings: list[str]) -> dict:
    txs, date_note, descriptions = _transactions(table, warnings)
    if date_note:
        warnings.append(date_note)
    cells = [c for row in table.rows[:400] for c in row]
    currency = guess_currency(table.header, cells, descriptions)
    if not txs:
        warnings.append("No transactions with both a date and an amount were found.")
        return {"kind": "bank_statement", "currency": currency, "period": None, "totals": None, "byMonth": [],
                "byCategory": [], "topTransactions": [], "insights": []}

    oldest_first = txs[0].date <= txs[-1].date  # same-day rows keep the statement's own order
    chronological = sorted(txs, key=lambda t: (t.date, t.order if oldest_first else -t.order))
    inflow = sum(t.amount for t in txs if t.amount > 0)
    outflow = -sum(t.amount for t in txs if t.amount < 0)
    months: dict[str, dict[str, float]] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0})
    for t in txs:
        bucket = months[t.date.strftime("%Y-%m")]
        bucket["inflow" if t.amount > 0 else "outflow"] += abs(t.amount)
    by_month = [{"month": m, "inflow": round(v["inflow"], 2), "outflow": round(v["outflow"], 2),
                 "net": round(v["inflow"] - v["outflow"], 2)} for m, v in sorted(months.items())]
    cats: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    for t in txs:
        if t.amount < 0:
            cats[t.category][0] += -t.amount
            cats[t.category][1] += 1
    by_category = [{"category": c, "amount": round(v[0], 2), "count": int(v[1])}
                   for c, v in sorted(cats.items(), key=lambda kv: -kv[1][0])]
    top = _top_transactions(txs)
    report = {
        "kind": "bank_statement",
        "currency": currency,
        "period": {"start": chronological[0].date.isoformat(), "end": chronological[-1].date.isoformat()},
        "totals": {"inflow": round(inflow, 2), "outflow": round(outflow, 2), "net": round(inflow - outflow, 2)},
        "byMonth": by_month,
        "byCategory": by_category,
        "topTransactions": [{"date": t.date.isoformat(), "description": t.description[:140], "amount": t.amount,
                             "category": t.category} for t in top],
    }
    report["insights"] = _insights(report, chronological, len(txs))
    return report


def _top_transactions(txs: list[Tx]) -> list[Tx]:
    """Largest by absolute amount, at most PER_CATEGORY_TOP per category so six salary credits don't fill it."""
    picked: list[Tx] = []
    per_category: dict[str, int] = defaultdict(int)
    for t in sorted(txs, key=lambda t: (-abs(t.amount), t.date)):
        if per_category[t.category] < PER_CATEGORY_TOP:
            picked.append(t)
            per_category[t.category] += 1
        if len(picked) >= TOP_TRANSACTIONS:
            break
    return picked


def _insights(report: dict, txs: list[Tx], count: int) -> list[str]:
    cur = report["currency"]
    totals, months, cats = report["totals"], report["byMonth"], report["byCategory"]
    inflow, outflow, net = totals["inflow"], totals["outflow"], totals["net"]
    period = period_label(report["period"]["start"], report["period"]["end"])
    out = []
    line = (f"Net cash flow for {period}: {signed_money(net, cur)} across {count:,} transactions "
            f"({money(inflow, cur)} in vs {money(outflow, cur)} out)")
    if inflow > 0:
        line += f", a savings rate of {net / inflow:.0%}"
    out.append(line + ".")
    if cats:
        top = cats[0]
        out.append(f"Biggest spending category: {top['category']} at {money(top['amount'], cur)} "
                   f"({pct(top['amount'], outflow)} of all spending, {top['count']} transaction"
                   f"{'s' if top['count'] != 1 else ''}).")
    if months:
        avg_out = sum(m["outflow"] for m in months) / len(months)
        negative = [month_label(m["month"]) for m in months if m["net"] < 0]
        burn = f"Average monthly spending (burn rate) is {money(avg_out, cur)} over {len(months)} month" \
               f"{'s' if len(months) != 1 else ''}"
        if negative:
            burn += f"; spending exceeded income in {', '.join(negative)}."
        else:
            burn += "; no month had a negative net cash flow."
        out.append(burn)
        if len(months) >= 2:
            peak = max(months, key=lambda m: m["outflow"])
            out.append(f"Highest-spending month: {month_label(peak['month'])} with {money(peak['outflow'], cur)} "
                       f"out ({signed_money(peak['net'], cur)} net).")
    outflows = [t for t in txs if t.amount < 0]
    if outflows:
        big = min(outflows, key=lambda t: t.amount)
        out.append(f"Largest single payment: {money(-big.amount, cur)} on {big.date:%d %b %Y} — "
                   f"{big.description[:70]} ({big.category}).")
    salary = [t for t in txs if t.category == "Salary"]
    if salary:
        salary_months = {t.date.strftime("%Y-%m") for t in salary}
        out.append(f"Salary credits total {money(sum(t.amount for t in salary), cur)}, about "
                   f"{money(sum(t.amount for t in salary) / len(salary_months), cur)} per month.")
    subs = next((c for c in cats if c["category"] == "Subscriptions"), None)
    if subs and months:
        out.append(f"Subscriptions cost {money(subs['amount'], cur)} in total "
                   f"(≈ {money(subs['amount'] / len(months), cur)} per month across {subs['count']} charges).")
    balances = [t for t in txs if t.balance is not None]
    if balances:
        first, last = balances[0], balances[-1]
        opening = first.balance - first.amount
        out.append(f"Account balance moved from {money(opening, cur)} to {money(last.balance, cur)} "
                   f"({signed_money(last.balance - opening, cur)}).")
    return out
