"""Tolerant readers for messy financial spreadsheets: rows, header detection, amounts, dates, currency.

Bank exports are rarely clean tables: preamble lines (account holder, branch), separator rows, footers,
amounts like "1,23,456.00 Cr" or "(450.00)", and day-first dates. Everything here returns None/warnings
instead of raising.
"""
from __future__ import annotations

import csv
import io
import math
import re
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from app.rag.formats import ZIP_BOMB_MESSAGE, zip_too_large

MAX_ROWS = 50_000
HEADER_SCAN_ROWS = 40
MIN_DATE = date(1990, 1, 1)
MAX_ABS_AMOUNT = 1e18  # beyond any real amount; keeps sums finite (no inf/NaN in the JSON report)

Cell = Any  # str | float | int | datetime | date | None


@dataclass
class Sheet:
    name: str
    rows: list[list[Cell]]


@dataclass
class Table:
    """A header + data rows (padded to the header width) cut out of a sheet."""

    sheet: str
    header: list[str]
    rows: list[list[Cell]]
    header_row: int
    roles: dict[str, int] = field(default_factory=dict)  # role → column index


# ── reading ──────────────────────────────────────────────────────────────────
def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _blank(value: Cell) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def read_csv_rows(path: Path) -> list[list[Cell]]:
    text = _decode(path.read_bytes())
    sample = text[:65536]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = max(",;\t|", key=sample.count) if sample else ","
    rows: list[list[Cell]] = []
    for row in csv.reader(io.StringIO(text), delimiter=delimiter):
        if any(c.strip() for c in row):
            rows.append([c.strip() for c in row])
        if len(rows) >= MAX_ROWS:
            break
    return rows


def _missing(value: Cell) -> bool:
    """Blank, NaN, NaT or pd.NA."""
    if _blank(value):
        return True
    if isinstance(value, str):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _frame_rows(df: pd.DataFrame) -> list[list[Cell]]:
    rows = []
    for values in df.astype(object).itertuples(index=False, name=None):
        row = [None if _missing(v) else (v.strip() if isinstance(v, str) else v) for v in values]
        if any(v is not None for v in row):
            rows.append(row)
        if len(rows) >= MAX_ROWS:
            break
    return rows


def _html_rows(df: pd.DataFrame) -> list[list[Cell]]:
    """read_html turns <th> cells into column names: put them back as the first row for header detection."""
    rows = _frame_rows(df)
    if not isinstance(df.columns, pd.RangeIndex):
        names = []
        for col in df.columns:
            parts = col if isinstance(col, tuple) else (col,)
            names.append(" ".join(dict.fromkeys(str(p) for p in parts if not str(p).startswith("Unnamed:"))) or None)
        if any(names):
            rows.insert(0, names)
    return rows


def read_excel_sheets(path: Path) -> list[Sheet]:
    if zip_too_large(path):  # an .xlsx "zip bomb" would be inflated fully into memory by openpyxl
        raise ValueError(ZIP_BOMB_MESSAGE)
    frames = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    return [Sheet(str(name), _frame_rows(df)) for name, df in frames.items()]


_WORKBOOK_MAGIC = (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")  # xlsx (zip) / legacy xls (OLE2)


def read_sheets(path: Path) -> list[Sheet]:
    """All sheets of a CSV/XLSX/XLS file as row lists (raises on unreadable files).

    Many bank portals export "Excel" files that are really HTML tables or tab-separated text, so an .xls/.xlsx
    that isn't a workbook is read as HTML tables or delimited text instead."""
    if path.suffix.lower() == ".csv":
        return [Sheet("CSV", read_csv_rows(path))]
    try:
        return read_excel_sheets(path)
    except Exception:
        raw = path.read_bytes()
        head = raw[:4096]
        utf16 = head.startswith((b"\xff\xfe", b"\xfe\xff"))
        if head.startswith(_WORKBOOK_MAGIC) or (b"\x00" in head and not utf16):
            raise  # a real but broken/encrypted workbook
        text = _decode(raw)
        if re.search(r"(?i)<(table|html)\b", text[:65536]):
            frames = pd.read_html(io.StringIO(text))
            return [Sheet(f"Table {i + 1}", _html_rows(df)) for i, df in enumerate(frames)]
        rows = read_csv_rows(path)
        if len(rows) < 2:
            raise  # not a table either: report the file as unreadable
        return [Sheet("Sheet1", rows)]


# ── header roles ─────────────────────────────────────────────────────────────
def norm_header(value: Cell) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


_ROLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("type", re.compile(r"^(dr cr|cr dr|d c|c d|debit credit|credit debit|txn type|transaction type|type|dr or cr)$")),
    ("balance", re.compile(r"balance|closing bal|running bal|\bbal\b")),
    ("debit", re.compile(r"withdrawal|debit|^dr( amount| amt)?$|money out|paid out|outflow|spent|^payments?$")),
    ("credit", re.compile(r"deposit|credit|^cr( amount| amt)?$|money in|paid in|inflow|received|^receipts?$")),
    ("date", re.compile(r"(^|\b)(date|dt)(\b|$)|^(txn|tran|trans|transaction|posting|value|book) (date|dt)$")),
    ("description", re.compile(r"narration|description|particulars|details|remarks|memo|payee|merchant|"
                               r"beneficiary|^name$|^transaction$")),
    ("amount", re.compile(r"amount|^amt\b|\bamt$|^value$|^total$|^(inr|usd|eur|gbp|rs)$|^sum$")),
    # year columns of financial statements: "As at 31 March 2026", "FY 2025-26", "Year ended 31.03.2026", "2026"
    ("amount", re.compile(r"^(as (at|on)|year ended|for the year|fy)\b.*\d{2}|^(fy )?(19|20)\d{2}( (19|20)?\d{2})?$")),
    ("label", re.compile(r"categor|account|^item|line item|head|classification|group|section|sub category|"
                         r"^particulars$")),
    ("notes", re.compile(r"^(notes?|comments?|remarks?)$")),
]


def header_roles(header: list[Cell]) -> dict[str, int]:
    """Map roles (date, description, debit, credit, amount, balance, type, label, notes) to column indexes."""
    roles: dict[str, int] = {}
    secondary_date: int | None = None
    for i, cell in enumerate(header):
        h = norm_header(cell)
        if not h:
            continue
        for role, rx in _ROLE_PATTERNS:
            if rx.search(h):
                if role == "date" and h.startswith("value"):
                    secondary_date = i if secondary_date is None else secondary_date
                    break
                if role not in roles:
                    roles[role] = i
                break
    if "date" not in roles and secondary_date is not None:
        roles["date"] = secondary_date
    return roles


def _header_score(row: list[Cell]) -> int:
    if sum(1 for c in row if isinstance(c, str) and c.strip()) < 2:
        return 0
    if sum(1 for c in row if parse_amount(c)[0] is not None) > len(row) / 2:
        return 0  # a data row, not a header
    roles = header_roles(row)
    score = len(roles)
    if "date" in roles and ({"debit", "credit", "amount"} & roles.keys()):
        score += 3
    if "label" in roles and "amount" in roles:
        score += 2
    return score


def find_table(sheets: list[Sheet]) -> Table | None:
    """The best header row across sheets (scans the first rows; preamble lines are skipped)."""
    best: tuple[int, Sheet, int] | None = None
    for sheet in sheets:
        for i, row in enumerate(sheet.rows[:HEADER_SCAN_ROWS]):
            score = _header_score(row)
            if score >= 2 and (best is None or score > best[0]):
                best = (score, sheet, i)
    if best is None:
        sheet = next((s for s in sheets if s.rows), None)
        if sheet is None:
            return None
        best = (0, sheet, 0)
    _, sheet, index = best
    header = [str(c).strip() if not _blank(c) else f"column_{j + 1}" for j, c in enumerate(sheet.rows[index])]
    width = len(header)
    rows = [(r + [None] * width)[:width] for r in sheet.rows[index + 1:]]
    rows = [[None if _blank(c) else c for c in r] for r in rows]
    rows = [r for r in rows if any(c is not None for c in r) and not _separator(r)]
    return Table(sheet.name, header, rows, index, header_roles(header))


def _separator(row: list[Cell]) -> bool:
    texts = [str(c) for c in row if c is not None]
    return bool(texts) and all(re.fullmatch(r"[\s*=\-_.]+", t) for t in texts)


# ── amounts ──────────────────────────────────────────────────────────────────
_CURRENCY_TOKENS = re.compile(r"(?i)\b(rs|inr|usd|eur|gbp|aed|sgd|jpy)\b\.?|rs\.|[₹$€£¥]")
_EURO_DECIMAL = re.compile(r"^\d{1,3}(\.\d{3})+,\d{1,2}$|^\d+,\d{1,2}$")  # "1.234,56" / "12,50"
# (a thousands group always has 3 digits — even Indian lakh grouping ends in one — so ",dd" is a decimal)


def parse_amount(value: Cell) -> tuple[float | None, int]:
    """(amount, sign hint) — hint is +1 for a 'CR' suffix, -1 for 'DR', 0 otherwise. None when not a number."""
    if value is None or isinstance(value, bool):
        return None, 0
    if isinstance(value, (int, float)):
        number = float(value)
        return (number, 0) if math.isfinite(number) and abs(number) <= MAX_ABS_AMOUNT else (None, 0)
    if isinstance(value, (datetime, date)):
        return None, 0
    s = str(value).strip().replace("−", "-").replace(" ", " ")
    if not s or s.lower() in {"-", "--", "nan", "none", "null", "n/a", "na", "nil"}:
        return None, 0
    hint = 0
    m = re.search(r"(?i)\s*\b(cr|dr)\.?\s*$", s)
    if m:
        hint = 1 if m.group(1).lower() == "cr" else -1
        s = s[: m.start()].strip()
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    s = _CURRENCY_TOKENS.sub("", s).strip()
    if s.endswith("-"):
        negative, s = True, s[:-1].strip()
    if s.startswith("-"):
        negative, s = True, s[1:].strip()
    s = s.lstrip("+").replace(" ", "")
    if _EURO_DECIMAL.match(s):
        s = s.replace(".", "").replace(",", ".")
    s = s.replace(",", "").replace("'", "")
    if not re.fullmatch(r"\d+(\.\d+)?|\.\d+", s):
        return None, 0
    number = float(s)
    if abs(number) > MAX_ABS_AMOUNT:  # "9999…" (hundreds of digits) → inf would break the JSON report
        return None, 0
    return (-number if negative else number), hint


def numeric_share(values: list[Cell]) -> float:
    present = [v for v in values if v is not None]
    if not present:
        return 0.0
    return sum(1 for v in present if parse_amount(v)[0] is not None) / len(present)


# ── dates ────────────────────────────────────────────────────────────────────
_ISO = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


def _plausible(d: date | None, today: date) -> date | None:
    if d is None or d < MIN_DATE or d > today + timedelta(days=366):
        return None
    return d


def _monotonic_share(values: list[date | None]) -> float:
    seq = [v for v in values if v is not None]
    if len(seq) < 3:
        return 1.0
    ups = sum(1 for a, b in zip(seq, seq[1:]) if b >= a)
    downs = sum(1 for a, b in zip(seq, seq[1:]) if b <= a)
    return max(ups, downs) / (len(seq) - 1)


def parse_dates(values: list[Cell], today: date | None = None) -> tuple[list[date | None], str | None]:
    """Parse a date column (day-first when ambiguous, with sanity checks). Returns (dates, note)."""
    today = today or date.today()
    out: list[date | None] = [None] * len(values)
    text_idx: list[int] = []
    for i, v in enumerate(values):
        if v is None:
            continue
        if isinstance(v, datetime):
            out[i] = _plausible(v.date(), today)
        elif isinstance(v, date):
            out[i] = _plausible(v, today)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            if 20_000 <= float(v) <= 80_000:  # Excel serial day numbers
                out[i] = _plausible(date(1899, 12, 30) + timedelta(days=int(v)), today)
        else:
            text_idx.append(i)
    if not text_idx:
        return out, None
    texts = pd.Series([str(values[i]).strip() for i in text_idx], dtype=object)
    dates, dayfirst = _parse_explicit(texts, today)
    if dates is None:
        dates, dayfirst = _parse_mixed(texts, today)
    for i, d in zip(text_idx, dates):
        out[i] = d
    return out, ("Dates were read day-first (DD/MM/YYYY)." if dayfirst else None)


# (strptime format, True when it is the day-first reading of an ambiguous numeric date)
_FORMATS: list[tuple[str, bool]] = [
    ("%d/%m/%y", True), ("%d/%m/%Y", True), ("%d-%m-%Y", True), ("%d-%m-%y", True), ("%d.%m.%Y", True),
    ("%d.%m.%y", True), ("%m/%d/%Y", False), ("%m/%d/%y", False), ("%m-%d-%Y", False),
    ("%Y-%m-%d", False), ("%Y/%m/%d", False), ("%Y-%m-%d %H:%M:%S", False), ("%d/%m/%Y %H:%M:%S", True),
    ("%d-%b-%Y", False), ("%d-%b-%y", False), ("%d %b %Y", False), ("%d %b %y", False), ("%d %B %Y", False),
    ("%b %d, %Y", False), ("%d-%B-%Y", False),
]


def _to_dates(parsed: pd.Series, today: date) -> list[date | None]:
    return [_plausible(ts.date(), today) if not pd.isna(ts) else None for ts in parsed]


def _parse_explicit(texts: pd.Series, today: date) -> tuple[list[date | None] | None, bool]:
    """Fast vectorised parse with the single format that fits most values (ties: chronological order, then
    day-first). None when no explicit format covers ≥ 90% of the values."""
    best: tuple[tuple[int, float, int], list[date | None], bool] | None = None
    for rank, (fmt, dayfirst) in enumerate(_FORMATS):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(texts, format=fmt, errors="coerce")
        valid = int(parsed.notna().sum())
        if not valid or (best is not None and valid < best[0][0]):
            continue
        dates = _to_dates(parsed, today)
        key = (sum(d is not None for d in dates), _monotonic_share(dates), -rank)
        if best is None or key > best[0]:
            best = (key, dates, dayfirst)
    if best is None or best[0][0] < 0.9 * len(texts):
        return None, False
    return best[1], best[2]


def _parse_mixed(texts: pd.Series, today: date) -> tuple[list[date | None], bool]:
    """dateutil per value; tries day-first and month-first and keeps the more plausible reading."""
    iso_share = texts.map(lambda s: bool(_ISO.match(s))).mean()
    options = [False] if iso_share > 0.5 else [True, False]
    best: tuple[tuple[int, float, int], list[date | None], bool] | None = None
    for dayfirst in options:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(texts, errors="coerce", dayfirst=dayfirst, format="mixed")
        dates = _to_dates(parsed, today)
        key = (sum(d is not None for d in dates), _monotonic_share(dates), int(dayfirst))
        if best is None or key > best[0]:
            best = (key, dates, dayfirst)
    assert best is not None
    return best[1], best[2] and len(options) == 2 and best[0][0] > 0


# ── currency ─────────────────────────────────────────────────────────────────
_CURRENCY_HINTS = [
    ("INR", re.compile(r"₹|\binr\b|\brs\.?(?=[\s\d)\]/,:-]|$)|rupee", re.I)),
    ("USD", re.compile(r"\busd\b|us\$|\$", re.I)),
    ("EUR", re.compile(r"€|\beur\b", re.I)),
    ("GBP", re.compile(r"£|\bgbp\b", re.I)),
    ("JPY", re.compile(r"¥|\bjpy\b", re.I)),
    ("AED", re.compile(r"\baed\b", re.I)),
    ("SGD", re.compile(r"\bsgd\b", re.I)),
]
_INDIAN_RAILS = re.compile(r"\b(upi|neft|imps|rtgs|nach|ach d|paytm|phonepe|gpay)\b|@(ok|yb|ybl|axl|ibl|paytm)",
                           re.I)


def guess_currency(header: list[str], cells: list[Cell], descriptions: list[str]) -> str | None:
    head = " ".join(header)
    for code, rx in _CURRENCY_HINTS:
        if rx.search(head):
            return code
    sample = " ".join(str(c) for c in cells[:400] if isinstance(c, str))
    for code, rx in _CURRENCY_HINTS:
        if rx.search(sample):
            return code
    rails = sum(1 for d in descriptions[:400] if _INDIAN_RAILS.search(d or ""))
    if descriptions and rails >= max(2, len(descriptions[:400]) * 0.1):
        return "INR"
    return None
