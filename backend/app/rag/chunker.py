"""Structure-aware chunking.

Rules: sections are hard boundaries; text is split paragraph → sentence → word only when it has to be;
~TARGET_CHARS per chunk (≈350 tokens) with ~15% sentence overlap; hard max 2× target; tables stay whole
when they fit (otherwise split by rows with the header repeated); no text is ever dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.rag.blocks import Block

TARGET_CHARS = 1400
OVERLAP_RATIO = 0.15
CHARS_PER_TOKEN = 4

# a sentence ends at terminal punctuation (+ closing quotes/brackets) before a capitalised start, or at a newline
_ABBREV = "".join(rf"(?<!\b{a})" for a in ("Dr", "Mr", "Ms", "Mrs", "Prof", "Fig", "Figs", "Eq", "No", "vs",
                                              "al", "St", "Jr", "Sr", "Inc", "Ltd", "Co", "Sec", "Vol", "pp"))
_SENTENCE_END_RE = re.compile(_ABBREV + r"[.!?…。।]+[\"'”’)\]]*(?=\s+[\"'“‘(\[]?[A-Z0-9ऀ-ॿ])|\n+")


@dataclass
class ChunkDraft:
    text: str            # what the user sees (cited snippet)
    embed_text: str      # what gets embedded: "Section: …" context + text
    page_start: int | None
    page_end: int | None
    section: str | None
    token_count: int


@dataclass
class _Piece:
    text: str
    page: int | None
    kind: str
    block_id: int
    is_sentence: bool = False


@dataclass
class _Acc:
    pieces: list[_Piece] = field(default_factory=list)
    overlap: str = ""
    overlap_block: int = -1

    def text(self) -> str:
        out, prev_block = self.overlap, (self.overlap_block if self.overlap else None)
        for piece in self.pieces:
            if not out:
                out = piece.text
            elif piece.is_sentence and prev_block == piece.block_id:
                out += " " + piece.text
            else:
                out += "\n\n" + piece.text
            prev_block = piece.block_id
        return out

    def size(self) -> int:
        return len(self.text())


def split_sentences(text: str) -> list[str]:
    """Split on sentence ends without losing any characters (only whitespace between sentences)."""
    out, start = [], 0
    for match in _SENTENCE_END_RE.finditer(text):
        piece = text[start:match.end()].strip()
        if piece:
            out.append(piece)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def _split_words(text: str, limit: int) -> list[str]:
    """Last resort for run-on text: windows of whole words, hard-cutting words longer than `limit`."""
    out, cur = [], ""
    for word in text.split():
        while len(word) > limit:
            if cur:
                out.append(cur)
                cur = ""
            out.append(word[:limit])
            word = word[limit:]
        if cur and len(cur) + 1 + len(word) > limit:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        out.append(cur)
    return out


def _split_table(text: str, target: int, max_chars: int) -> list[str]:
    """Split an oversized markdown table by rows, repeating its header (and a short caption).

    A long preamble is emitted once rather than repeated, and a header too wide to repeat falls back to
    line splitting, so every line survives.
    """
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")), None)
    if start is None:
        return _split_lines(text, target)
    out: list[str] = []
    if len("\n".join(lines[:start])) > target // 4:
        out.extend(_split_lines("\n".join(lines[:start]).strip("\n"), target))
        lines, start = lines[start:], 0
    has_sep = len(lines) > start + 1 and set(lines[start + 1].replace("|", "").strip()) <= set("-: ")
    head = lines[: start + (2 if has_sep else 1)]
    head_text = "\n".join(head)
    if len(head_text) > target // 2:
        return out + _split_lines("\n".join(lines), target)
    cur, header_out = list(head), False
    for line in lines[len(head):]:
        too_big = len(head_text) + 1 + len(line) > max_chars  # a single monster row
        if (len(cur) > len(head) and len("\n".join(cur)) + 1 + len(line) > target) or (too_big and not header_out):
            out.append("\n".join(cur))
            cur, header_out = list(head), True
        if too_big:
            out.extend(_split_words(line, target))
            continue
        cur.append(line)
    if len(cur) > len(head) or not header_out:
        out.append("\n".join(cur))
    return out


def _split_lines(text: str, target: int) -> list[str]:
    out, cur = [], ""
    for line in text.split("\n"):
        if len(line) > target:
            if cur:
                out.append(cur)
                cur = ""
            out.extend(_split_words(line, target))
            continue
        if cur and len(cur) + 1 + len(line) > target:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def _pieces(block: Block, block_id: int, target: int, max_chars: int) -> list[_Piece]:
    text = block.text.strip()
    if not text:
        return []
    if (block.kind == "heading" and len(text) <= max_chars) or len(text) <= target:
        return [_Piece(text, block.page, block.kind, block_id)]
    if block.kind == "table":
        if len(text) <= max_chars:
            return [_Piece(text, block.page, "table", block_id)]
        return [_Piece(t, block.page, "table", block_id) for t in _split_table(text, target, max_chars)]
    if block.kind == "code":
        return [_Piece(t, block.page, "code", block_id) for t in _split_lines(text, target)]
    out: list[_Piece] = []
    for sentence in split_sentences(text):
        parts = [sentence] if len(sentence) <= target else _split_words(sentence, target)
        out.extend(_Piece(p, block.page, "text", block_id, is_sentence=True) for p in parts)
    return out


def _overlap_tail(acc: _Acc, budget: int) -> str:
    """Trailing whole sentences of the last prose piece, up to `budget` chars."""
    last = acc.pieces[-1] if acc.pieces else None
    if last is None or last.kind != "text":
        return ""
    tail: list[str] = []
    for sentence in reversed(split_sentences(last.text)):
        if sum(len(s) + 1 for s in tail) + len(sentence) > budget:
            break
        tail.insert(0, sentence)
    if len(tail) == len(split_sentences(last.text)) and len(acc.pieces) == 1:
        return ""  # never repeat a whole one-piece chunk
    return " ".join(tail)


def _emit(acc: _Acc, section: str | None, out: list[ChunkDraft]) -> None:
    text = acc.text().strip()
    if not text:
        return
    pages = [p.page for p in acc.pieces if p.page is not None]
    embed = f"Section: {section}\n\n{text}" if section else text
    out.append(ChunkDraft(text=text, embed_text=embed, page_start=min(pages) if pages else None,
                          page_end=max(pages) if pages else None, section=section,
                          token_count=max(1, len(text) // CHARS_PER_TOKEN)))


def _pack_section(pieces: list[_Piece], section: str | None, target: int, max_chars: int,
                  out: list[ChunkDraft]) -> None:
    overlap_budget = int(target * OVERLAP_RATIO)
    acc = _Acc()
    for piece in pieces:
        if acc.pieces:
            joined = acc.size() + 2 + len(piece.text)
            fits = joined <= target or (acc.size() < target // 2 and joined <= max_chars)
            if not fits:
                tail = _overlap_tail(acc, overlap_budget)
                _emit(acc, section, out)
                keep = len(tail) + 2 + len(piece.text) <= max_chars
                acc = _Acc(overlap=tail if keep else "", overlap_block=acc.pieces[-1].block_id)
        acc.pieces.append(piece)
    _emit(acc, section, out)


def chunk_blocks(blocks: list[Block], target: int = TARGET_CHARS) -> list[ChunkDraft]:
    """Turn parsed blocks into retrieval chunks (see module docstring for the rules)."""
    max_chars = target * 2
    runs: list[tuple[str | None, list[_Piece]]] = []
    for i, block in enumerate(blocks):
        pieces = _pieces(block, i, target, max_chars)
        if not pieces:
            continue
        if runs and runs[-1][0] == block.section and block.kind != "heading":
            runs[-1][1].extend(pieces)
        else:
            runs.append((block.section, pieces))

    chunks: list[ChunkDraft] = []
    carry: list[_Piece] = []  # a heading-only run is folded into the next section instead of standing alone
    for idx, (section, pieces) in enumerate(runs):
        if all(p.kind == "heading" for p in pieces) and idx + 1 < len(runs):
            carry.extend(pieces)
            continue
        _pack_section(carry + pieces, section, target, max_chars, chunks)
        carry = []
    return chunks
