"""Page-aware PDF parsing with PyMuPDF: headings from font metrics, tables as markdown, OCR fallback."""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.rag import ocr
from app.rag.blocks import Block, ParsedDocument, ParseError, clean_text, push_heading, section_path
from app.rag.text import parse_markdown_text

log = logging.getLogger("sphura.rag.pdf")

TEXT_FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP  # ligatures expanded
MIN_PAGE_CHARS = 25          # fewer extracted chars than this on a page with images → OCR it
MAX_OCR_PAGES = 60
OCR_DPI = 150
TABLE_BUDGET_S = 20.0        # stop table detection on huge PDFs after this much time
MIN_TABLE_DRAWINGS = 4       # a ruled table needs at least a few vector lines/rects
_CAPTION_RE = re.compile(r"^(fig(ure)?|table|tab|eq(uation)?|algorithm|listing)\.?\s*\d", re.I)
_MUPDF_LOCK = threading.Lock()


@dataclass
class _Item:
    """A positioned piece of page content before it becomes a Block."""

    text: str
    size: float
    bold: bool
    lines: int
    kind: str = "text"


def _body_size(doc: pymupdf.Document, sample_pages: int = 30) -> float:
    sizes: Counter[float] = Counter()
    for page in doc.pages(0, min(sample_pages, doc.page_count)):
        for block in page.get_text("dict", flags=TEXT_FLAGS)["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    sizes[round(span["size"] * 2) / 2] += len(span["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else 11.0


def _join_lines(lines: list[str]) -> str:
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out.endswith("-") and len(out) > 1 and out[-2].isalpha() and line[:1].islower():
            out = out[:-1] + line  # de-hyphenate a word broken across lines
        else:
            out = f"{out} {line}" if out else line
    return out


def _in_any(rect: pymupdf.Rect, boxes: list[pymupdf.Rect]) -> int:
    cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
    for i, box in enumerate(boxes):
        if box.x0 - 2 <= cx <= box.x1 + 2 and box.y0 - 2 <= cy <= box.y1 + 2:
            return i
    return -1


def _has_rulings(page: pymupdf.Page) -> bool:
    """find_tables() needs vector lines and costs ~150 ms/page, so skip pages that have (almost) none."""
    try:
        return len(page.get_cdrawings()) >= MIN_TABLE_DRAWINGS
    except Exception:  # noqa: BLE001
        return False


def _find_tables(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str]]:
    if not _has_rulings(page):
        return []
    try:
        found = page.find_tables()
    except Exception as exc:  # noqa: BLE001 — table detection is best effort
        log.debug("find_tables failed on page %s: %s", page.number + 1, exc)
        return []
    tables = []
    for table in found.tables:
        try:
            md = table.to_markdown(clean=False).strip()
        except Exception:  # noqa: BLE001
            continue
        if md and table.row_count >= 2:
            tables.append((pymupdf.Rect(table.bbox), md))
    return tables


def _page_items(page: pymupdf.Page, detect_tables: bool) -> list[_Item]:
    """Text blocks in native reading order, with detected tables spliced in place of their cells."""
    tables = _find_tables(page) if detect_tables else []
    boxes = [rect for rect, _ in tables]
    placed: set[int] = set()
    items: list[_Item] = []
    for block in page.get_text("dict", flags=TEXT_FLAGS)["blocks"]:
        lines, sizes, bold_chars, chars = [], [], 0, 0
        for line in block.get("lines", []):
            hit = _in_any(pymupdf.Rect(line["bbox"]), boxes)
            if hit >= 0:
                if hit not in placed:
                    placed.add(hit)
                    items.append(_Item(tables[hit][1], 0, False, 0, "table"))
                continue
            text = "".join(span["text"] for span in line["spans"])
            if not text.strip():
                continue
            lines.append(text)
            for span in line["spans"]:
                n = len(span["text"].strip())
                chars += n
                sizes.append((span["size"], n))
                if span["flags"] & 16 or "bold" in span["font"].lower():
                    bold_chars += n
        if lines:
            size = max((s for s, n in sizes if n), default=0.0)
            items.append(_Item(_join_lines(lines), size, chars > 0 and bold_chars >= 0.9 * chars, len(lines)))
    items.extend(_Item(md, 0, False, 0, "table") for i, (_, md) in enumerate(tables) if i not in placed)
    return items


def _is_heading(item: _Item, body: float) -> bool:
    text = item.text.strip()
    if item.kind != "text" or not (2 <= len(text) <= 150) or item.lines > 3:
        return False
    if not re.search(r"[A-Za-zऀ-ॿ]", text) or _CAPTION_RE.match(text):
        return False
    if item.size >= body * 1.15:
        return True
    return item.bold and item.lines == 1 and item.size >= body * 0.95 and not text.endswith((".", ",", ";"))


@dataclass
class _Extracted:
    page_count: int
    body: float
    per_page: dict[int, list[_Item]]
    scanned: list[int]
    images: list[bytes]  # PNG renders of the first MAX_OCR_PAGES scanned pages (only when OCR is available)


def _extract(doc: pymupdf.Document) -> _Extracted:
    """All MuPDF work for one document: positioned items per page, scanned-page detection and renders."""
    per_page: dict[int, list[_Item]] = {}
    scanned: list[int] = []
    started = time.perf_counter()
    for page in doc:
        detect = time.perf_counter() - started < TABLE_BUDGET_S
        items = _page_items(page, detect_tables=detect)
        per_page[page.number] = items
        if sum(len(i.text) for i in items) < MIN_PAGE_CHARS and page.get_images(full=False):
            scanned.append(page.number)
    images = ([doc[p].get_pixmap(dpi=OCR_DPI).tobytes("png") for p in scanned[:MAX_OCR_PAGES]]
              if scanned and ocr.available() else [])
    return _Extracted(doc.page_count, _body_size(doc), per_page, scanned, images)


def parse_pdf(path: Path) -> ParsedDocument:
    with _MUPDF_LOCK:  # PyMuPDF is not thread-safe and ingestion runs two workers; OCR calls happen outside
        try:
            doc = pymupdf.open(path)
        except Exception as exc:  # noqa: BLE001
            raise ParseError("This PDF could not be opened (it may be corrupted)") from exc
        with doc:
            if doc.needs_pass:
                raise ParseError("This PDF is password-protected")
            ex = _extract(doc)
    ocr_text = dict(zip(ex.scanned, ocr.transcribe_many(ex.images))) if ex.images else {}
    return _assemble(ex, ocr_text)


def _assemble(ex: _Extracted, ocr_text: dict[int, str]) -> ParsedDocument:
    body, per_page, scanned = ex.body, ex.per_page, ex.scanned
    stack: list[tuple[float, str]] = []
    parsed = ParsedDocument(blocks=[], page_count=ex.page_count)
    parsed.ocr_needed = bool(scanned) and not ocr.available()
    if len(scanned) > MAX_OCR_PAGES and ocr.available():
        parsed.warnings.append(f"OCR limited to the first {MAX_OCR_PAGES} scanned pages")

    for pno in range(ex.page_count):
        page_no = pno + 1
        if ocr_text.get(pno, "").strip():
            parsed.ocr_used = True
            parsed.blocks.extend(parse_markdown_text(ocr_text[pno], page=page_no, stack=stack))
            continue
        for item in per_page[pno]:
            text = clean_text(item.text)
            if not text:
                continue
            if _is_heading(item, body):
                push_heading(stack, item.size + (0.5 if item.bold else 0), text)
                parsed.blocks.append(Block(text, page_no, section_path(stack), "heading"))
            else:
                kind = "table" if item.kind == "table" else "text"
                parsed.blocks.append(Block(text, page_no, section_path(stack), kind))
    return parsed
