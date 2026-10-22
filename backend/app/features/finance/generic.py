"""Fallback for any other table: describe the numeric columns and group by a low-cardinality text column."""
from __future__ import annotations

from collections import OrderedDict

from app.features.finance.parsing import Table, guess_currency, numeric_share, parse_amount

MAX_COLUMNS_DESCRIBED = 5


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}"


def analyze_table(table: Table, warnings: list[str]) -> dict:
    width = len(table.header)
    columns = [[row[i] for row in table.rows] for i in range(width)]
    numeric = [i for i in range(width) if numeric_share(columns[i]) >= 0.8 and any(v is not None for v in columns[i])]
    text = [i for i in range(width) if i not in numeric and any(v is not None for v in columns[i])]
    insights = [f"{len(table.rows):,} rows × {width} columns"
                + (f" in sheet “{table.sheet}”" if table.sheet != "CSV" else "") + "."]
    for i in numeric[:MAX_COLUMNS_DESCRIBED]:
        values = [v for v in (parse_amount(c)[0] for c in columns[i]) if v is not None]
        if not values:
            continue
        total, mean = sum(values), sum(values) / len(values)
        insights.append(f"{table.header[i]}: total {_fmt(total)}, average {_fmt(mean)}, "
                        f"range {_fmt(min(values))} to {_fmt(max(values))} ({len(values):,} values).")
    by_category: list[dict] = []
    if numeric:
        value_idx = numeric[0]
        for i in text:
            distinct = {str(v).strip() for v in columns[i] if v is not None}
            if 2 <= len(distinct) <= 30:
                groups: OrderedDict[str, list[float]] = OrderedDict()
                for row in table.rows:
                    amount = parse_amount(row[value_idx])[0]
                    if row[i] is None or amount is None:
                        continue
                    bucket = groups.setdefault(str(row[i]).strip(), [0.0, 0])
                    bucket[0] += amount
                    bucket[1] += 1
                by_category = [{"category": k, "amount": round(v[0], 2), "count": int(v[1])}
                               for k, v in sorted(groups.items(), key=lambda kv: -abs(kv[1][0]))][:15]
                if by_category:
                    top = by_category[0]
                    insights.append(f"Largest {table.header[i]} by {table.header[value_idx]}: {top['category']} "
                                    f"({_fmt(top['amount'])} across {top['count']} rows).")
                break
    if not numeric:
        warnings.append("No numeric columns were found, so there is little to analyse.")
    cells = [c for row in table.rows[:400] for c in row]
    return {"kind": "table", "currency": guess_currency(table.header, cells, []), "period": None, "totals": None,
            "byMonth": [], "byCategory": by_category, "topTransactions": [], "balanceSheet": None,
            "insights": insights}
