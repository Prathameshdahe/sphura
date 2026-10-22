"""Split a markdown answer into checkable sentences ("claims") with exact char offsets and citations.

Skipped: fenced code (``` / ~~~ / $$), headings, tables, horizontal rules, HTML-only lines, reference-list entries,
questions and very short fragments. List bullets, numbers and blockquote markers are excluded from the span, so
for every claim `content[start:end] == text` holds exactly.
"""
from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field

MAX_CLAIMS = 40
MIN_WORDS = 4
MAX_HYPOTHESIS_WORDS = 80

_FENCE = re.compile(r"^\s{0,3}(```|~~~|\$\$)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}(\s|$)")
_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_HTML_LINE = re.compile(r"^\s*<[^>]+>\s*$")
_PREFIX = re.compile(r"^\s*(?:>\s*)*(?:(?:[-*+]|\d{1,3}[.)])\s+)?(?:\[[ xX]\]\s+)?")

# [1] · [1, 2] · [1-3] (also en dash). A citation directly after the full stop belongs to that sentence.
CITATION = re.compile(r"\[(\d{1,3}(?:\s*[-–,]\s*\d{1,3})*)\]")
_CITES = r"(?:\s*\[\d{1,3}(?:\s*[-–,]\s*\d{1,3})*\])*"
_END = re.compile(r"[.!?…]+[\"'”’)\]*_]*" + _CITES + r"[\"'”’)*_]*(?=\s|$)")
_NEXT_OK = re.compile(r"[A-Z0-9\"'“‘(\[*_`]")
_ABBREVIATIONS = {
    "e.g", "i.e", "vs", "al", "dr", "mr", "mrs", "ms", "prof", "fig", "figs", "no", "nos", "approx",
    "inc", "ltd", "co", "corp", "jr", "sr", "st", "cf", "eq", "eqs", "sec", "vol", "pp", "ch", "u.s", "u.k",
    "e.u", "a.m", "p.m", "ph.d", "dept", "est", "ref", "refs",
}
_WORD_BEFORE = re.compile(r"([A-Za-z][A-Za-z.]*)$")
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARKUP = re.compile(r"\*\*|__|~~|`|\*")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")
_LETTER = re.compile(r"[A-Za-zÀ-ɏͰ-ϿЀ-ӿऀ-ॿ]")
# A checkable figure: 2+ digits (years, counts, amounts), a decimal, a percentage, a currency amount or a number
# with a magnitude word — not a lone ordinal digit ("Step 1:", "Option 2 is …", "GPT-4").
_SPECIFIC_NUMBER = re.compile(
    r"\d{2,}|\d[.,]\d|\d\s*%|[$€£₹]\s*\d|\d\s*(?:k|m|bn|million|billion|trillion|thousand|lakh|crore)\b", re.I)
_INLINE_CODE = re.compile(r"`[^`]*`")
_REFERENCE_ENTRY = re.compile(r"^\s*(?:[-*+]\s+)?\[\d{1,3}\]")  # "[1] Title — url" lines of a reference list


@dataclass
class Claim:
    text: str                      # exactly content[start:end]
    start: int
    end: int
    source_indexes: list[int] = field(default_factory=list)
    hypothesis: str = ""           # cleaned text fed to the NLI model (no markdown, no citations)

    @property
    def specific(self) -> bool:
        """States a specific fact: a figure, year, date, percentage or amount outside inline code and citations —
        lone ordinal digits ("Step 1", "Option 2") and list intros ending in ":" ("Here are 12 options:") don't."""
        prose = _INLINE_CODE.sub("", CITATION.sub("", self.text))
        return bool(_SPECIFIC_NUMBER.search(prose)) and not self.hypothesis.endswith(":")


def parse_citations(text: str) -> list[int]:
    """Citation indexes in order of appearance, deduplicated ([1, 3] and [2-4] style groups included)."""
    found: list[int] = []
    for match in CITATION.finditer(text):
        for part in match.group(1).split(","):
            part = part.strip()
            bounds = re.split(r"\s*[-–]\s*", part)
            if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                lo, hi = int(bounds[0]), int(bounds[1])
                numbers = list(range(lo, hi + 1)) if 0 < hi - lo <= 10 else [lo, hi]
            else:
                numbers = [int(part)] if part.isdigit() else []
            for n in numbers:
                if n > 0 and n not in found:
                    found.append(n)
    return found


def clean_hypothesis(text: str) -> str:
    """Plain sentence for NLI: drop citations, links and emphasis markers; collapse whitespace."""
    text = CITATION.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _MARKUP.sub("", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", " ".join(text.split()))
    words = text.split()
    return " ".join(words[:MAX_HYPOTHESIS_WORDS]) if len(words) > MAX_HYPOTHESIS_WORDS else text


def _table_lines(lines: list[str]) -> set[int]:
    """Indexes of lines that belong to a GFM table (header, separator and body rows)."""
    rows: set[int] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") or (stripped.endswith("|") and stripped.count("|") >= 2):
            rows.add(i)
        elif _TABLE_SEP.match(line) and "-" in line and i > 0 and "|" in lines[i - 1]:
            rows.update((i - 1, i))
            j = i + 1
            while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                rows.add(j)
                j += 1
    return rows


def _is_boundary(segment: str, match: re.Match[str]) -> bool:
    """A sentence end unless it follows an abbreviation/initial or the next word starts lower-case."""
    if segment[match.start()] == ".":
        before = _WORD_BEFORE.search(segment[: match.start()])
        if before:
            word = before.group(1).lower().rstrip(".")
            if word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha()):
                return False
    rest = segment[match.end():].lstrip()
    return not rest or bool(_NEXT_OK.match(rest))


def _sentences_in(segment: str) -> list[tuple[int, int]]:
    """(start, end) spans of the sentences in one line segment (relative to the segment)."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _END.finditer(segment):
        if match.end() <= start or not _is_boundary(segment, match):
            continue
        spans.append((start, match.end()))
        start = match.end()
    if start < len(segment):
        spans.append((start, len(segment)))
    out: list[tuple[int, int]] = []
    for s, e in spans:
        piece = segment[s:e]
        lead = len(piece) - len(piece.lstrip())
        trail = len(piece) - len(piece.rstrip())
        if e - trail > s + lead:
            out.append((s + lead, e - trail))
    return out


def split_sentences(content: str) -> list[Claim]:
    """Every prose sentence of `content` (no cap), with exact offsets, citations and NLI hypothesis."""
    lines = content.split("\n")
    tables = _table_lines(lines)
    claims: list[Claim] = []
    offset = 0
    in_fence: str | None = None
    for i, line in enumerate(lines):
        line_start, offset = offset, offset + len(line) + 1
        fence = _FENCE.match(line)
        if in_fence:
            if fence and fence.group(1) == in_fence:
                in_fence = None
            continue
        if fence:
            in_fence = fence.group(1)
            continue
        if (not line.strip() or i in tables or _HEADING.match(line) or _HR.match(line)
                or _HTML_LINE.match(line) or _REFERENCE_ENTRY.match(line)):
            continue
        prefix = _PREFIX.match(line)
        seg_start = line_start + (prefix.end() if prefix else 0)
        segment = content[seg_start: line_start + len(line)].rstrip("\r")
        for s, e in _sentences_in(segment):
            text = segment[s:e]
            hypothesis = clean_hypothesis(text)
            if (len(hypothesis.split()) < MIN_WORDS or not _LETTER.search(hypothesis)
                    or hypothesis.rstrip("\"'”’)*_ ").endswith("?")):
                continue
            claims.append(Claim(text=text, start=seg_start + s, end=seg_start + e,
                                source_indexes=parse_citations(text), hypothesis=hypothesis))
    return claims


def extract_claims(content: str, limit: int = MAX_CLAIMS, skip_sources: Collection[int] = ()) -> list[Claim]:
    """Up to `limit` sentences in reading order; cited and number-bearing ones win when there are too many.
    Sentences citing only `skip_sources` (e.g. code files, which an NLI model can't judge) are left out."""
    skip = set(skip_sources)
    claims = [c for c in split_sentences(content) if not (skip and c.source_indexes and set(c.source_indexes) <= skip)]
    if len(claims) <= limit:
        return claims
    ranked = sorted(range(len(claims)),
                    key=lambda i: (not claims[i].source_indexes, not claims[i].specific, i))
    keep = sorted(ranked[:limit])
    return [claims[i] for i in keep]
