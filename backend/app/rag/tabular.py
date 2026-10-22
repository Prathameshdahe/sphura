"""CSV / Excel parsing with pandas: a dataset overview block + row-group blocks with the header repeated."""
from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

import pandas as pd

from app.rag.blocks import Block, ParsedDocument, ParseError, md_table
from app.rag.text import read_text_file

log = logging.getLogger("sphura.rag.tabular")

ROWS_PER_BLOCK = 40
BLOCK_CHAR_BUDGET = 1600   # a row group closes early when it gets this long (wide tables)
PREVIEW_ROWS = 5
MAX_DESCRIBE_COLS = 15
WIDE_HEADER_CHARS = 600    # wider tables are written as "column: value" records so every chunk keeps its labels


def _read_csv(path: Path) -> pd.DataFrame:
    text = read_text_file(path)
    try:
        dialect = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|")
        sep = dialect.delimiter
    except csv.Error:
        sep = ","
    try:
        return pd.read_csv(io.StringIO(text), sep=sep)
    except (pd.errors.ParserError, ValueError):
        log.warning("CSV has ragged rows; re-reading with the tolerant python engine")
        return pd.read_csv(io.StringIO(text), sep=sep, engine="python", on_bad_lines="warn")


def _read_excel(path: Path) -> dict[str, pd.DataFrame]:
    try:
        return pd.read_excel(path, sheet_name=None)
    except Exception as exc:  # noqa: BLE001
        raise ParseError("This spreadsheet could not be read (it may be corrupted or password-protected)") from exc


def _fmt(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def _dtype_label(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    return "text"


def _overview(df: pd.DataFrame, title: str) -> str:
    lines = [f"Dataset overview — {title}", f"{len(df)} rows × {len(df.columns)} columns", "", "Columns:"]
    for col in df.columns:
        series = df[col]
        missing = int(series.isna().sum())
        extra = f", {missing} missing" if missing else ""
        lines.append(f"- {col} ({_dtype_label(series)}, {series.nunique(dropna=True)} distinct{extra})")
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        desc = numeric.iloc[:, :MAX_DESCRIBE_COLS].describe().T
        rows = [[name] + [_fmt(v) for v in row] for name, row in zip(desc.index, desc.values.tolist())]
        lines += ["", "Numeric summary:", md_table(["column"] + [str(c) for c in desc.columns], rows)]
    if not _is_wide(df):  # wide tables: the row records already show every value with its column name
        head = df.head(PREVIEW_ROWS)
        lines += ["", f"First {len(head)} rows:",
                  md_table([str(c) for c in df.columns], [[_fmt(v) for v in r] for r in head.values.tolist()])]
    return "\n".join(lines)


def _is_wide(df: pd.DataFrame) -> bool:
    return len(md_table([str(c) for c in df.columns], [])) > WIDE_HEADER_CHARS


def _record_groups(df: pd.DataFrame) -> list[tuple[int, int, str]]:
    """Wide tables: one "Row n: column: value; …" line per row, grouped to ~BLOCK_CHAR_BUDGET chars."""
    header = [str(c) for c in df.columns]
    groups, current, size, start = [], [], 0, 0
    for i, row in enumerate(df.values.tolist()):
        line = f"Row {i + 1}: " + "; ".join(f"{h}: {v}" for h, v in zip(header, map(_fmt, row)) if v != "")
        if current and size + len(line) > BLOCK_CHAR_BUDGET:
            groups.append((start + 1, i, "\n".join(current)))
            current, size, start = [], 0, i
        current.append(line)
        size += len(line) + 1
    if current:
        groups.append((start + 1, len(df), "\n".join(current)))
    return groups


def _row_groups(df: pd.DataFrame) -> list[tuple[int, int, str]]:
    """Split rows into markdown tables of ≤ ROWS_PER_BLOCK rows / ~BLOCK_CHAR_BUDGET chars, header repeated."""
    if _is_wide(df):
        return _record_groups(df)
    header = [str(c) for c in df.columns]
    header_len = len(md_table(header, []))
    groups, current, size, start = [], [], header_len, 0
    for i, row in enumerate(df.values.tolist()):
        cells = [_fmt(v) for v in row]
        row_len = sum(len(c) + 3 for c in cells) + 2
        if current and (len(current) >= ROWS_PER_BLOCK or size + row_len > BLOCK_CHAR_BUDGET):
            groups.append((start + 1, i, md_table(header, current)))
            current, size, start = [], header_len, i
        current.append(cells)
        size += row_len
    if current:
        groups.append((start + 1, len(df), md_table(header, current)))
    return groups


def _frame_blocks(df: pd.DataFrame, title: str, section: str) -> list[Block]:
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c) if not str(c).startswith("Unnamed:") else f"column_{i + 1}" for i, c in enumerate(df.columns)]
    if df.empty:
        return []
    blocks = [Block(_overview(df, title), None, section, "table")]
    for first, last, table in _row_groups(df):
        blocks.append(Block(f"{title} — rows {first}–{last} of {len(df)}\n\n{table}", None, section, "table"))
    return blocks


def parse_csv(path: Path, filename: str) -> ParsedDocument:
    try:
        df = _read_csv(path)
    except pd.errors.EmptyDataError:
        return ParsedDocument(blocks=[])
    except Exception as exc:  # noqa: BLE001
        raise ParseError("This CSV file could not be parsed") from exc
    return ParsedDocument(blocks=_frame_blocks(df, filename, filename))


def parse_excel(path: Path, filename: str) -> ParsedDocument:
    blocks: list[Block] = []
    for sheet, df in _read_excel(path).items():
        title = f"{filename} · sheet “{sheet}”"
        blocks.extend(_frame_blocks(df, title, f"Sheet: {sheet}"))
    return ParsedDocument(blocks=blocks)
