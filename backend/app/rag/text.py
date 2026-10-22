"""Plain text / Markdown parsing (also used for OCR output and HTML converted to Markdown)."""
from __future__ import annotations

import re
from pathlib import Path

from app.rag.blocks import Block, clean_text, push_heading, section_path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def read_text_file(path: Path) -> str:
    """Decode a text file: BOM-aware UTF-8/16, then Windows-1252, then Latin-1 (never fails)."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _flush(buf: list[str], kind: str, page: int | None, section: str | None, out: list[Block]) -> None:
    text = "\n".join(buf).strip("\n")
    text = text if kind == "code" else clean_text(text)
    if text.strip():
        out.append(Block(text, page, section, kind))  # type: ignore[arg-type]
    buf.clear()


def parse_markdown_text(
    text: str,
    page: int | None = None,
    stack: list[tuple[float, str]] | None = None,
) -> list[Block]:
    """Split Markdown/plain text into heading, paragraph, table and code blocks.

    `stack` carries the heading hierarchy across calls (e.g. page by page for OCR).
    """
    stack = stack if stack is not None else []
    blocks: list[Block] = []
    buf: list[str] = []
    kind = "text"
    in_fence = False
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _FENCE_RE.match(line):
            if in_fence:
                buf.append(line)
                _flush(buf, "code", page, section_path(stack), blocks)
                in_fence, kind = False, "text"
                continue
            _flush(buf, kind, page, section_path(stack), blocks)
            in_fence, kind = True, "code"
            buf.append(line)
            continue
        if in_fence:
            buf.append(line)
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            _flush(buf, kind, page, section_path(stack), blocks)
            title = heading.group(2).strip()
            push_heading(stack, 7 - len(heading.group(1)), title)
            blocks.append(Block(title, page, section_path(stack), "heading"))
            kind = "text"
            continue
        is_table_row = line.lstrip().startswith("|")
        if not line.strip() or (is_table_row != (kind == "table") and buf):
            _flush(buf, kind, page, section_path(stack), blocks)
        if line.strip():
            kind = "table" if is_table_row else "text"
            buf.append(line)
    _flush(buf, "code" if in_fence else kind, page, section_path(stack), blocks)
    return blocks
