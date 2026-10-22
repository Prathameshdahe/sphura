"""DOCX parsing with python-docx: heading styles → sections, tables → markdown, page breaks → pages."""
from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.rag.blocks import Block, ParsedDocument, ParseError, clean_text, md_table, push_heading, section_path

_P, _TBL, _SDT, _SDT_CONTENT = qn("w:p"), qn("w:tbl"), qn("w:sdt"), qn("w:sdtContent")
_HEADING_STYLE_RE = re.compile(r"^heading\s*(\d)", re.I)
_BREAK_XPATH = './/w:br[@w:type="page"]'
_RENDERED_XPATH = ".//w:lastRenderedPageBreak"


def _heading_level(paragraph: Paragraph) -> int | None:
    name = (paragraph.style.name if paragraph.style is not None else "") or ""
    if name.lower() == "title":
        return 0
    match = _HEADING_STYLE_RE.match(name)
    return int(match.group(1)) if match else None


def _table_markdown(table: Table) -> str:
    rows: list[list[str]] = []
    for row in table.rows:
        cells, seen = [], set()
        for cell in row.cells:
            if id(cell._tc) in seen:  # horizontally merged cells repeat the same element
                continue
            seen.add(id(cell._tc))
            cells.append(clean_text(cell.text).replace("\n", " "))
        rows.append(cells)
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return ""
    return md_table(rows[0], rows[1:])


def _paragraph_text(paragraph: Paragraph) -> str:
    text = clean_text(paragraph.text)
    style = (paragraph.style.name if paragraph.style is not None else "") or ""
    if text and style.lower().startswith("list"):
        return f"• {text}"
    return text


def _iter_body(document: DocxDocument) -> Iterator[Paragraph | Table]:
    """Body paragraphs and tables in order, including those wrapped in content controls (w:sdt), which
    python-docx's iter_inner_content() skips (templates often put the whole report inside them)."""
    parent = document._body

    def walk(element: BaseOxmlElement) -> Iterator[Paragraph | Table]:
        for child in element.iterchildren():
            if child.tag == _P:
                yield Paragraph(child, parent)  # type: ignore[arg-type]
            elif child.tag == _TBL:
                yield Table(child, parent)  # type: ignore[arg-type]
            elif child.tag == _SDT:
                content = child.find(_SDT_CONTENT)
                if content is not None:
                    yield from walk(content)

    yield from walk(document.element.body)


def parse_docx(path: Path) -> ParsedDocument:
    try:
        document = docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ParseError("This Word document could not be opened (it may be corrupted or not a .docx)") from exc

    blocks: list[Block] = []
    stack: list[tuple[float, str]] = []
    page, saw_break = 1, False
    for item in _iter_body(document):
        if isinstance(item, Table):
            md = _table_markdown(item)
            if md:
                blocks.append(Block(md, page, section_path(stack), "table"))
            continue
        hard = bool(item._p.xpath(_BREAK_XPATH))
        rendered = bool(item._p.xpath(_RENDERED_XPATH))
        text = _paragraph_text(item)
        if rendered or (hard and not text):  # the paragraph starts on a new page
            page, saw_break = page + 1, True
        if text:
            level = _heading_level(item)
            if level is not None:
                push_heading(stack, 7 - level, text)
                blocks.append(Block(text, page, section_path(stack), "heading"))
            else:
                _add_text(blocks, text, page, section_path(stack))
        if hard and text and not rendered:  # explicit break after this paragraph's text
            page, saw_break = page + 1, True

    if not saw_break:
        for block in blocks:
            block.page = None
    return ParsedDocument(blocks=blocks, page_count=page if saw_break else None)


def _add_text(blocks: list[Block], text: str, page: int, section: str | None) -> None:
    """Append a paragraph; consecutive list items are kept together as one block."""
    prev = blocks[-1] if blocks else None
    if (prev and prev.kind == "text" and text.startswith("• ") and prev.text.split("\n")[-1].startswith("• ")
            and prev.page == page and prev.section == section):
        prev.text += "\n" + text
    else:
        blocks.append(Block(text, page, section, "text"))
