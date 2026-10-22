"""File → ParsedDocument dispatch. Every parser returns page-aware blocks {text, page, section, kind}."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.rag import ocr
from app.rag.blocks import Block, ParsedDocument, ParseError, clean_text
from app.rag.formats import ZIP_BOMB_MESSAGE, mime_for, zip_too_large
from app.rag.office import parse_docx
from app.rag.pdf import parse_pdf
from app.rag.tabular import parse_csv, parse_excel
from app.rag.text import parse_markdown_text, read_text_file

log = logging.getLogger("sphura.rag.parsers")

JSON_GROUP_CHARS = 1200
JSON_KEY_SECTIONS = 40


def _parse_text(path: Path) -> ParsedDocument:
    return ParsedDocument(blocks=parse_markdown_text(read_text_file(path)))


def _dump(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _group_block(group: dict) -> Block:
    keys = [str(k) for k in group]
    label = keys[0] if len(keys) == 1 else f"{keys[0]} … {keys[-1]}"
    return Block(_dump(group), None, label[:200], "code")


def _dict_blocks(data: dict) -> list[Block]:
    """One section per top-level key; objects with many keys are grouped (else 3k keys → 3k tiny chunks)."""
    if len(data) <= JSON_KEY_SECTIONS:
        return [Block(_dump({key: value}), None, str(key)[:200], "code") for key, value in data.items()]
    blocks, group, size = [], {}, 0
    for key, value in data.items():
        text = _dump({key: value})
        if group and size + len(text) > JSON_GROUP_CHARS:
            blocks.append(_group_block(group))
            group, size = {}, 0
        group[key] = value
        size += len(text)
    if group:
        blocks.append(_group_block(group))
    return blocks


def _json_blocks(data: object) -> list[Block]:
    """Top-level keys (objects) or item groups (arrays) become sections of pretty-printed JSON."""
    if isinstance(data, dict):
        return _dict_blocks(data)
    if isinstance(data, list):
        blocks, group, size, start = [], [], 0, 0
        for i, item in enumerate(data):
            text = json.dumps(item, indent=2, ensure_ascii=False, default=str)
            if group and size + len(text) > JSON_GROUP_CHARS:
                blocks.append(Block("[\n" + ",\n".join(group) + "\n]", None, f"items {start + 1}–{i}", "code"))
                group, size, start = [], 0, i
            group.append(text)
            size += len(text)
        if group:
            blocks.append(Block("[\n" + ",\n".join(group) + "\n]", None, f"items {start + 1}–{len(data)}", "code"))
        return blocks
    return [Block(json.dumps(data, ensure_ascii=False), None, None, "code")]


def _parse_json(path: Path) -> ParsedDocument:
    raw = read_text_file(path)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        try:  # JSON Lines
            data = [json.loads(ln) for ln in lines]
        except json.JSONDecodeError:
            log.info("invalid JSON; indexing it as plain text")
            return ParsedDocument(blocks=parse_markdown_text(raw))
    return ParsedDocument(blocks=_json_blocks(data))


def _parse_html(path: Path) -> ParsedDocument:
    html = read_text_file(path)
    title, markdown = None, None
    try:
        import trafilatura

        markdown = trafilatura.extract(html, output_format="markdown", include_tables=True,
                                       include_formatting=True, favor_recall=True, include_comments=False)
    except Exception as exc:  # noqa: BLE001
        log.info("trafilatura failed (%s); using BeautifulSoup", exc)
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        title = clean_text(soup.title.string)[:200] or None
    if not markdown or len(markdown) < 0.2 * len(soup.get_text(" ", strip=True)):
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        markdown = soup.get_text("\n", strip=True)
    stack = [(10.0, title)] if title else []
    return ParsedDocument(blocks=parse_markdown_text(markdown, stack=stack))


def _parse_image(path: Path) -> ParsedDocument:
    if not ocr.available():
        return ParsedDocument(blocks=[], page_count=1, ocr_needed=True)
    text = ocr.transcribe(path.read_bytes(), mime_for(path.suffix))
    return ParsedDocument(blocks=parse_markdown_text(text, page=1), page_count=1, ocr_used=bool(text.strip()))


def parse_file(path: Path, filename: str) -> ParsedDocument:
    """Parse a stored upload. Raises ParseError with a user-facing message on failure."""
    ext = Path(filename).suffix.lower()
    if ext in (".docx", ".xlsx") and zip_too_large(path):
        raise ParseError(ZIP_BOMB_MESSAGE)
    if ext == ".pdf":
        return parse_pdf(path)
    if ext == ".docx":
        return parse_docx(path)
    if ext in (".txt", ".md"):
        return _parse_text(path)
    if ext == ".csv":
        return parse_csv(path, filename)
    if ext in (".xlsx", ".xls"):
        return parse_excel(path, filename)
    if ext == ".json":
        return _parse_json(path)
    if ext == ".html":
        return _parse_html(path)
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        return _parse_image(path)
    raise ParseError(f"Unsupported file type '{ext}'")
