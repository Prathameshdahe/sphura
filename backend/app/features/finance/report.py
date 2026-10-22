"""Build a FinanceReport for a stored CSV/XLSX file, plus a compact Markdown summary for the chat agent.

Never raises on messy input: anything unexpected becomes a warning and a simpler report.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path, PurePosixPath
from typing import Any

from app.features.finance.balance import analyze_balance_sheet
from app.features.finance.bank import analyze_bank, looks_like_bank
from app.features.finance.generic import analyze_table
from app.features.finance.money import money, month_label, pct, period_label
from app.features.finance.pnl import analyze_pnl, link_balance_sheet, looks_like_pnl, pnl_insights
from app.features.finance.parsing import find_table, guess_currency, read_sheets
from app.features.finance.schemas import FinanceReport

log = logging.getLogger("sphura.finance")

TABULAR_EXTENSIONS = (".csv", ".xlsx", ".xls")
KIND_LABELS = {"bank_statement": "bank statement", "balance_sheet": "balance sheet", "table": "table"}


def is_tabular(filename: str) -> bool:
    return PurePosixPath(filename.lower()).suffix in TABULAR_EXTENSIONS


def _empty(doc_id: str, filename: str) -> dict[str, Any]:
    return {"docId": doc_id, "filename": filename, "kind": "table", "currency": None, "period": None,
            "totals": None, "byMonth": [], "byCategory": [], "topTransactions": [], "balanceSheet": None,
            "profitLoss": None, "amountUnit": None, "insights": [], "warnings": []}


def _finish(report: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    report["warnings"] = list(dict.fromkeys([*report.get("warnings", []), *warnings]))
    return FinanceReport.model_validate(report).dump()


def analyze_file(path: Path, filename: str, doc_id: str) -> dict[str, Any]:
    """Deterministic analytics (no LLM): bank statement, balance sheet or generic table."""
    report = _empty(doc_id, filename)
    warnings: list[str] = []
    try:
        sheets = read_sheets(path)
    except Exception as exc:  # noqa: BLE001
        log.info("finance: could not read %s: %s", filename, exc)
        warnings.append("This file could not be read as a spreadsheet (it may be corrupted, password-protected "
                        "or not really a CSV/Excel file).")
        return _finish(report, warnings)
    table = find_table(sheets)
    if table is None or not table.rows:
        warnings.append("The file has no data rows to analyse.")
        return _finish(report, warnings)
    if table.header_row:
        warnings.append(f"Skipped {table.header_row} line{'s' if table.header_row != 1 else ''} above the "
                        "table header (account details / preamble).")
    pnl_table = _pnl_table(sheets, table)
    used = [table.sheet] + ([pnl_table.sheet] if pnl_table is not None and pnl_table.sheet != table.sheet else [])
    if len([s for s in sheets if s.rows]) > len(used):
        names = " and ".join(f"“{n}”" for n in used)
        warnings.append(f"Analysed sheet{'s' if len(used) > 1 else ''} {names} of a workbook with {len(sheets)} sheets.")
    try:
        if looks_like_bank(table):
            part = analyze_bank(table, warnings)
        elif pnl_table is table:
            part = analyze_table(table, warnings)
        else:
            part = analyze_balance_sheet(table, warnings) or analyze_table(table, warnings)
    except Exception:  # noqa: BLE001
        log.exception("finance analysis failed for %s", filename)
        warnings.append("Part of the analysis failed on this file's layout, so only a basic summary is shown.")
        try:
            part = analyze_table(table, warnings)
        except Exception:  # noqa: BLE001
            part = {}
    report.update(part)
    unit = _units_from_preamble(report, sheets, table, warnings) if table.header_row else None
    report["amountUnit"] = unit
    if pnl_table is not None:
        _add_pnl(report, pnl_table, unit)
    return _finish(report, warnings)


def _pnl_table(sheets: list[Any], main: Any) -> Any:
    """The profit and loss table: the main table itself, else the best table of another sheet that is one."""
    if looks_like_pnl(main) and not looks_like_bank(main):
        return main
    for sheet in sheets:
        if sheet.name == main.sheet or not sheet.rows:
            continue
        candidate = find_table([sheet])
        if candidate is not None and candidate.rows and looks_like_pnl(candidate):
            return candidate
    return None


def _add_pnl(report: dict[str, Any], table: Any, unit: str | None) -> None:
    try:
        pnl = analyze_pnl(table)
    except Exception:  # noqa: BLE001 — the rest of the report stands
        log.exception("P&L analysis failed for %s", report.get("filename"))
        return
    if pnl is None:
        return
    link_balance_sheet(pnl, report.get("balanceSheet"))
    report["profitLoss"] = pnl
    report["insights"] = [*pnl_insights(pnl, report.get("currency"), unit), *report.get("insights", [])]


_SCALE_NOTE = re.compile(r"\b(crores?|lakhs?|lacs?|millions?|thousands?|'?000s?)\b", re.I)


def _units_from_preamble(report: dict[str, Any], sheets: list[Any], table: Any, warnings: list[str]) -> str | None:
    """Statements often say "(All amounts in ₹ crore)" above the table: take the currency from there when the
    table itself has none, and repeat the unit so "3.4K" is not read as rupees."""
    sheet = next((s for s in sheets if s.name == table.sheet), None)
    lines = [" ".join(str(c) for c in row if c is not None) for row in (sheet.rows[:table.header_row] if sheet else [])]
    if not report.get("currency"):
        report["currency"] = guess_currency([], lines, [])
    unit = next((m.group(1).lower() for line in lines for m in [_SCALE_NOTE.search(line)] if m), None)
    if unit:
        warnings.append(f"Amounts are in {unit}, as stated above the table.")
    return unit


# ── markdown for the chat agent ──────────────────────────────────────────────
def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(c.replace("|", "/") for c in row) + " |" for row in rows]
    return "\n".join(out)


def summary_markdown(report: dict[str, Any], max_rows: int = 12) -> str:
    """Exact computed figures, most important first (the context budget may clip the tail)."""
    cur = report.get("currency")
    kind = KIND_LABELS.get(report.get("kind", "table"), "table")
    if report.get("kind") == "table" and report.get("profitLoss"):
        kind = "profit and loss statement"
    elif report.get("profitLoss"):
        kind += " with a profit and loss statement"
    head = f"Computed financial analysis of {report['filename']} ({kind}"
    if cur:
        head += f", currency {cur}"
    if report.get("period"):
        head += f", {period_label(report['period']['start'], report['period']['end'])}"
    parts = [head + "). Figures computed exactly with pandas by Sphura."]
    totals = report.get("totals")
    if totals:
        parts.append(f"Totals: money in {money(totals['inflow'], cur)}; money out {money(totals['outflow'], cur)}; "
                     f"net {money(totals['net'], cur)}.")
    pnl = report.get("profitLoss")
    if pnl:
        label = f" ({pnl['period']})" if pnl.get("period") else ""
        rows = [[name, money(pnl[key], cur) if "Margin" not in key and "return" not in key else _share(pnl[key])]
                for name, key in (("Revenue", "revenue"), ("Other income", "otherIncome"),
                                  ("Total expenses", "totalExpenses"), ("EBITDA", "ebitda"),
                                  ("Finance costs", "financeCosts"), ("Profit before tax", "profitBeforeTax"),
                                  ("Tax", "tax"), ("Net profit", "netProfit"), ("Net margin", "netMargin"),
                                  ("EBITDA margin", "ebitdaMargin"), ("Return on equity", "returnOnEquity"),
                                  ("Return on assets", "returnOnAssets"))
                if pnl.get(key) is not None]
        if pnl.get("revenueGrowth") is not None:
            rows.append([f"Revenue growth vs {pnl.get('previousPeriod') or 'previous year'}", _share(pnl["revenueGrowth"])])
        if pnl.get("profitGrowth") is not None:
            rows.append(["Net profit growth", _share(pnl["profitGrowth"])])
        if pnl.get("interestCoverage") is not None:
            rows.append(["Interest coverage", f"{pnl['interestCoverage']:.2f}x"])
        parts.append(f"Profit and loss{label}:\n" + _table(["Line", "Value"], rows))
    sheet = report.get("balanceSheet")
    if sheet:
        rows = [["Total assets", money(sheet["totalAssets"], cur)],
                ["Total liabilities", money(sheet["totalLiabilities"], cur)],
                ["Equity", money(sheet["equity"], cur)],
                ["Current ratio", _ratio(sheet["currentRatio"])],
                ["Quick ratio", _ratio(sheet["quickRatio"])],
                ["Debt-to-equity", _ratio(sheet["debtToEquity"])]]
        parts.append("Balance sheet:\n" + _table(["Metric", "Value"], rows))
    if report.get("insights"):
        parts.append("Key findings:\n" + "\n".join(f"- {i}" for i in report["insights"]))
    if report.get("byMonth"):
        rows = [[month_label(m["month"]), money(m["inflow"], cur), money(m["outflow"], cur), money(m["net"], cur)]
                for m in report["byMonth"][-max_rows:]]
        parts.append("By month:\n" + _table(["Month", "In", "Out", "Net"], rows))
    if report.get("byCategory"):
        if report.get("kind") == "bank_statement":
            whole = sum(abs(c["amount"]) for c in report["byCategory"]) or 0
            rows = [[c["category"], money(c["amount"], cur), pct(abs(c["amount"]), whole), str(c["count"])]
                    for c in report["byCategory"][:max_rows]]
            parts.append("Spending by category:\n" + _table(["Category", "Amount", "Share", "Count"], rows))
        else:
            rows = [[c["category"], money(c["amount"], cur), str(c["count"])]
                    for c in report["byCategory"][:max_rows]]
            parts.append("By category:\n" + _table(["Category", "Amount", "Items"], rows))
    if report.get("topTransactions"):
        rows = [[t["date"], t["description"][:60], money(t["amount"], cur), t["category"]]
                for t in report["topTransactions"][:8]]
        parts.append("Largest transactions:\n" + _table(["Date", "Description", "Amount", "Category"], rows))
    if report.get("warnings"):
        parts.append("Data notes: " + " ".join(report["warnings"]))
    return "\n\n".join(parts)


def _share(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _ratio(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"
