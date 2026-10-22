"""Shared parse types and small text helpers used by every parser."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["heading", "text", "table", "code"]

_WS_RE = re.compile(r"[ \t\f\v ]+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")


@dataclass
class Block:
    """One structural unit of a document, in reading order."""

    text: str
    page: int | None = None
    section: str | None = None
    kind: BlockKind = "text"


@dataclass
class ParsedDocument:
    blocks: list[Block]
    page_count: int | None = None
    ocr_used: bool = False
    ocr_needed: bool = False  # had image-only content but no OCR engine was available
    warnings: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return sum(len(b.text) for b in self.blocks)


class ParseError(Exception):
    """A user-facing parse failure (message is shown in the UI)."""


def clean_text(text: str) -> str:
    """Normalise whitespace inside lines, drop control chars, keep line structure."""
    text = _CTRL_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def md_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def md_table(header: list[str], rows: list[list[object]]) -> str:
    """Render a GitHub-flavoured markdown table (no external deps)."""
    width = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
    head = [md_cell(h) for h in header] + [""] * (width - len(header))
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * width]
    for row in rows:
        cells = [md_cell(c) for c in row] + [""] * (width - len(row))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def section_path(stack: list[tuple[float, str]], limit: int = 300) -> str | None:
    """Join a heading stack into "Parent › Child", trimmed to the DB column size."""
    if not stack:
        return None
    path = " › ".join(title for _, title in stack)
    while len(path) > limit and len(stack) > 1:
        stack = stack[1:]
        path = "… › " + " › ".join(title for _, title in stack)
    return path[:limit]


def push_heading(stack: list[tuple[float, str]], rank: float, title: str) -> None:
    """Heading stack update; a larger rank means a higher-level heading."""
    while stack and stack[-1][0] <= rank:
        stack.pop()
    stack.append((rank, title.strip()[:200]))
