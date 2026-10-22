"""Balance sheet analytics: classify line items, total them and compute liquidity / leverage ratios."""
from __future__ import annotations

import re
from collections import OrderedDict

from app.features.finance.money import money, pct
from app.features.finance.parsing import Table, guess_currency, numeric_share, parse_amount

_NONCURRENT = re.compile(r"non[\s-]?current|long[\s-]?term|fixed asset")
_LIABILITY = re.compile(r"liabilit|payable|accrued|borrowing|\bdebt\b|\bloans?\b|overdraft|deferred revenue|"
                        r"unearned|provision|credit line|notes payable|financing|creditor|outstanding|"
                        r"duties and taxes")
# Indian proprietorship / partnership sheets put capital, net profit and drawings on the liabilities side
_EQUITY = re.compile(r"equity|retained|reserves?\b|surplus|share ?holder|stockholder|common stock|preferred stock|"
                     r"paid[\s-]?in|treasury|share capital|owner'?s capital|^capital$|capital account|"
                     r"partners?'? capital|proprietor'?s? capital|drawings|net (profit|loss) for the (year|period)")
_ASSET = re.compile(r"asset|cash|\bbank\b|receivable|inventor|prepaid|investment|\bppe\b|property|plant|"
                    r"equipment|land|building|intangible|goodwill|depreciation|deposit|hardware|software|"
                    r"vehicle|furniture|finished goods|raw material|debtor|closing stock|stock in hand|"
                    r"loans and advances|capital work[\s-]in[\s-]progress|\bcwip\b")
_CURRENT_ASSET = re.compile(r"\bcurrent\b|cash|\bbank\b|receivable|inventor|prepaid|short[\s-]?term|marketable|"
                            r"finished goods|raw material|debtor|closing stock|stock in hand")
_CURRENT_LIABILITY = re.compile(r"\bcurrent\b|short[\s-]?term|payable|accrued|overdraft|credit line|creditor|"
                                r"outstanding|duties and taxes")
_INVENTORY = re.compile(r"inventor|finished goods|raw material|work in progress|\bwip\b|stock[\s-]in[\s-]trade|"
                        r"closing stock|stock in hand")
_NOT_AMOUNT = re.compile(r"\bnote|\bsch(edule)?\b|\b(s|sl|sr)\.? ?no")
_YEAR = re.compile(r"(?:19|20)\d{2}")
SIDE = {"current_asset": "asset", "noncurrent_asset": "asset", "asset": "asset", "current_liability": "liability",
        "noncurrent_liability": "liability", "liability": "liability", "equity": "equity"}
_PREPAID = re.compile(r"prepaid")
_TOTAL = re.compile(r"\b(sub)?total\b|\bnet total\b")


def classify(text: str, strict: bool = True) -> str | None:
    """'current_asset' | 'noncurrent_asset' | 'current_liability' | 'noncurrent_liability' | 'equity' | None.

    strict: a bare "Assets" / "Liabilities" is ambiguous (None) so a more specific cell can decide.
    """
    t = text.lower().strip()
    if not t:
        return None
    noncurrent = bool(_NONCURRENT.search(t))
    if re.search(r"\basset", t):
        if noncurrent:
            return "noncurrent_asset"
        if _CURRENT_ASSET.search(t):
            return "current_asset"
        return None if strict else "noncurrent_asset"
    if re.search(r"liabilit", t):
        if noncurrent:
            return "noncurrent_liability"
        if re.search(r"\bcurrent\b|short[\s-]?term", t):
            return "current_liability"
        if strict:
            return None
    if _EQUITY.search(t) and not re.search(r"capital work", t):
        return "equity"
    if _ASSET.search(t) and re.search(r"loans and advances|debtor|capital work|\bcwip\b", t):
        return "noncurrent_asset" if noncurrent or not _CURRENT_ASSET.search(t) else "current_asset"
    if _LIABILITY.search(t):
        return "noncurrent_liability" if noncurrent or not _CURRENT_LIABILITY.search(t) else "current_liability"
    if _ASSET.search(t):
        return "noncurrent_asset" if noncurrent or not _CURRENT_ASSET.search(t) else "current_asset"
    return None


def _amount_column(table: Table) -> int | None:
    """The amount column: an explicit "Amount" header, else the numeric column of the latest year in the header
    ("As at 31 March 2026" beats "As at 31 March 2025"), else the leftmost numeric column. Note / schedule /
    serial-number columns are never amounts."""
    if "amount" in table.roles:
        return table.roles["amount"]
    candidates = []
    for i, head in enumerate(table.header):
        if _NOT_AMOUNT.search(str(head or "").lower()):
            continue
        if numeric_share([row[i] for row in table.rows]) >= 0.6:
            years = [int(y) for y in _YEAR.findall(str(head or ""))]
            candidates.append((max(years) if years else -1, -i, i))
    return max(candidates)[2] if candidates else None


def _section(text: str) -> str | None:
    """The kind (or just the side) a heading row such as "Current liabilities" or "ASSETS" sets for the items
    below it; None for "EQUITY AND LIABILITIES" and other mixed headings."""
    t = " ".join(text.lower().split())
    if not t or ("equity" in t and "liabilit" in t):
        return None
    if re.fullmatch(r"(total\s+)?assets?|property and assets|application of funds", t):
        return "asset"
    if re.fullmatch(r"liabilities|capital and liabilities|liabilities and capital|sources of funds", t):
        return "liability"
    return classify(t, strict=False)


def _resolve(own: str | None, section: str | None, text: str) -> str | None:
    """An item's kind from its own wording and the heading it sits under (the heading wins on the side)."""
    if section is None:
        return own
    side = SIDE[section]
    if own == "equity" and side == "liability":
        return own  # capital / profit / drawings on the liabilities side of a proprietorship sheet
    if side == "equity":
        return "equity"
    if section in ("asset", "liability"):  # only the side is known: the item's wording decides current or not
        if own is not None and SIDE[own] == side:
            return own
        current = (_CURRENT_ASSET if side == "asset" else _CURRENT_LIABILITY).search(text.lower())
        return f"{'current' if current else 'noncurrent'}_{side}"
    return section


def _text_columns(table: Table, amount_idx: int) -> list[int]:
    cols = []
    for i in range(len(table.header)):
        if i == amount_idx or table.roles.get("notes") == i:
            continue
        values = [row[i] for row in table.rows if row[i] is not None]
        if values and numeric_share(values) < 0.5:
            cols.append(i)
    return cols


def analyze_balance_sheet(table: Table, warnings: list[str]) -> dict | None:
    """None when the table doesn't look like a balance sheet (no assets plus liabilities/equity)."""
    amount_idx = _amount_column(table)
    if amount_idx is None:
        return None
    text_cols = _text_columns(table, amount_idx)
    if not text_cols:
        return None
    category_idx = table.roles.get("label") if table.roles.get("label") in text_cols else text_cols[0]
    notes_idx = table.roles.get("notes")
    sums = dict.fromkeys(("current_asset", "noncurrent_asset", "current_liability", "noncurrent_liability",
                          "equity"), 0.0)
    seen: set[str] = set()
    inventory = prepaid = 0.0
    groups: OrderedDict[str, list[float]] = OrderedDict()
    items: list[tuple[str, float, str]] = []
    flagged: list[str] = []
    unclassified = subtotals = 0
    section: str | None = None
    for row in table.rows:
        amount = parse_amount(row[amount_idx])[0]
        cells = [str(row[i]).strip() for i in text_cols if row[i] is not None]
        joined = " ".join(cells)
        if amount is None:
            if joined and not _TOTAL.search(joined.lower()):
                section = _section(joined)
            continue
        if _TOTAL.search(joined.lower()):
            subtotals += 1
            continue
        own = next((k for k in (classify(c) for c in cells) if k), None) or classify(joined, strict=False)
        kind = _resolve(own, section, joined)
        if kind is None:
            unclassified += 1
            continue
        sums[kind] += amount
        seen.add(kind)
        if kind == "current_asset" and _INVENTORY.search(joined.lower()):
            inventory += amount
        if kind == "current_asset" and _PREPAID.search(joined.lower()):
            prepaid += amount
        group = str(row[category_idx]).strip() if row[category_idx] is not None else kind.replace("_", " ").title()
        bucket = groups.setdefault(group, [0.0, 0])
        bucket[0] += amount
        bucket[1] += 1
        name = cells[-1] if cells else group
        items.append((name, amount, kind))
        note = str(row[notes_idx]).strip() if notes_idx is not None and row[notes_idx] is not None else ""
        if note:
            flagged.append(f"{name} ({note})")

    has_assets = bool({"current_asset", "noncurrent_asset"} & seen)
    has_claims = bool({"current_liability", "noncurrent_liability", "equity"} & seen)
    if not (has_assets and has_claims):
        return None
    if subtotals:
        warnings.append(f"Ignored {subtotals} subtotal/total row{'s' if subtotals != 1 else ''} "
                        "(totals were recomputed from the line items).")
    if unclassified:
        warnings.append(f"{unclassified} line item{'s' if unclassified != 1 else ''} could not be classified as "
                        "an asset, liability or equity and were left out.")

    ca, nca = sums["current_asset"], sums["noncurrent_asset"]
    cl, ncl = sums["current_liability"], sums["noncurrent_liability"]
    total_assets = ca + nca if has_assets else None
    has_liabilities = bool({"current_liability", "noncurrent_liability"} & seen)
    total_liabilities = cl + ncl if has_liabilities else None
    equity: float | None = sums["equity"] if "equity" in seen else None
    if equity is None and total_assets is not None and total_liabilities is not None:
        equity = total_assets - total_liabilities
        warnings.append("No equity lines were found; equity was derived as total assets − total liabilities.")
    has_cl = "current_liability" in seen and cl > 0
    current_ratio = round(ca / cl, 3) if has_cl and "current_asset" in seen else None
    quick_ratio = round((ca - inventory - prepaid) / cl, 3) if has_cl and "current_asset" in seen else None
    debt_to_equity = (round(total_liabilities / equity, 3)
                      if total_liabilities is not None and equity is not None and equity > 0 else None)
    if total_assets is not None and total_liabilities is not None and equity is not None and "equity" in seen:
        gap = total_assets - (total_liabilities + equity)
        if abs(gap) > max(1.0, abs(total_assets) * 0.005):
            warnings.append(f"The sheet does not balance: assets differ from liabilities + equity by {gap:,.2f}.")

    cells = [c for row in table.rows for c in row]
    currency = guess_currency(table.header, cells, [])
    sheet = {
        "totalAssets": _r(total_assets), "totalLiabilities": _r(total_liabilities), "equity": _r(equity),
        "currentRatio": current_ratio, "quickRatio": quick_ratio, "debtToEquity": debt_to_equity,
    }
    by_category = [{"category": g, "amount": round(v[0], 2), "count": int(v[1])} for g, v in groups.items()]
    report = {"kind": "balance_sheet", "currency": currency, "period": None, "totals": None, "byMonth": [],
              "byCategory": by_category, "topTransactions": [], "balanceSheet": sheet}
    report["insights"] = _insights(sheet, sums, inventory, items, flagged, currency)
    return report


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _insights(sheet: dict, sums: dict, inventory: float, items: list[tuple[str, float, str]],
              flagged: list[str], cur: str | None) -> list[str]:
    out = []
    ta, tl, eq = sheet["totalAssets"], sheet["totalLiabilities"], sheet["equity"]
    if ta is not None:
        parts = [f"Total assets {money(ta, cur)}"]
        if tl is not None:
            parts.append(f"total liabilities {money(tl, cur)}")
        if eq is not None:
            parts.append(f"equity {money(eq, cur)}")
        out.append(", ".join(parts) + ".")
    cr, qr, de = sheet["currentRatio"], sheet["quickRatio"], sheet["debtToEquity"]
    if cr is not None:
        verdict = ("strong short-term liquidity" if cr >= 2 else "healthy liquidity" if cr >= 1.2
                   else "tight liquidity" if cr >= 1 else "current liabilities exceed current assets")
        out.append(f"Current ratio {cr:.2f} ({money(sums['current_asset'], cur)} current assets vs "
                   f"{money(sums['current_liability'], cur)} current liabilities) — {verdict}.")
    if qr is not None:
        out.append(f"Quick ratio {qr:.2f} after excluding {money(inventory, cur)} of inventory"
                   f"{' — can cover short-term obligations without selling stock' if qr >= 1 else ''}.")
    if de is not None:
        verdict = ("conservatively financed" if de < 0.5 else "moderately leveraged" if de <= 1.5
                   else "highly leveraged")
        out.append(f"Debt-to-equity {de:.2f} (total liabilities ÷ equity) — {verdict}.")
    assets = [i for i in items if i[2].endswith("asset") and i[1] > 0]
    if assets and ta:
        name, amount, _ = max(assets, key=lambda i: i[1])
        out.append(f"Largest asset: {name} at {money(amount, cur)} ({pct(amount, ta)} of total assets).")
    liabilities = [i for i in items if i[2].endswith("liability") and i[1] > 0]
    if liabilities and tl:
        name, amount, _ = max(liabilities, key=lambda i: i[1])
        out.append(f"Largest obligation: {name} at {money(amount, cur)} ({pct(amount, tl)} of liabilities).")
    if flagged:
        out.append("Notes on line items: " + "; ".join(flagged[:4]) + ".")
    return out

