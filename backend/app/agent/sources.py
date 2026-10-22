"""SourceRegistry: one stable 1-based index per web result / page / document chunk in a turn."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.schemas import Source

SNIPPET_CHARS = 400
_MIN_SHARE = 150


@dataclass
class _Entry:
    source: Source
    context: str  # what the model reads (page text / chunk text / snippet)


def _norm_url(url: str) -> str:
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), path, p.query, ""))


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut).rstrip() + "…"


def _snippet(text: str) -> str:
    return _clip(" ".join(text.split()), SNIPPET_CHARS)


class SourceRegistry:
    def __init__(self) -> None:
        self._entries: list[_Entry] = []
        self._keys: dict[str, int] = {}
        self.version = 0

    def __len__(self) -> int:
        return len(self._entries)

    def _add(self, key: str, source: Source, context: str) -> int:
        self._entries.append(_Entry(source, context))
        self._keys[key] = source.index
        self.version += 1
        return source.index

    def add_web(self, url: str, title: str, snippet: str, domain: str, score: float | None = None) -> int:
        key = "web:" + _norm_url(url)
        if key in self._keys:
            return self._keys[key]
        src = Source(index=len(self) + 1, type="web", title=title.strip() or domain, url=url, domain=domain,
                     snippet=_snippet(snippet), score=score)
        return self._add(key, src, snippet)

    def add_page(self, url: str, title: str, text: str, domain: str) -> int:
        """A fully read page: enrich the matching search result, or add a new source."""
        key = "web:" + _norm_url(url)
        if key in self._keys:
            entry = self._entries[self._keys[key] - 1]
            if len(text) > len(entry.context):
                entry.context = text  # richer context for the model; the client-visible source is unchanged
                if not entry.source.snippet:
                    entry.source.snippet = _snippet(text)
                    self.version += 1
            return entry.source.index
        src = Source(index=len(self) + 1, type="web", title=title.strip() or domain, url=url, domain=domain,
                     snippet=_snippet(text))
        return self._add(key, src, text)

    def add_doc(self, chunk: Any) -> int:
        """`chunk` is an app.rag.service.RetrievedChunk (duck-typed)."""
        key = f"doc:{chunk.doc_id}:{chunk.chunk_index}"
        if key in self._keys:
            return self._keys[key]
        title = chunk.filename + (f" — {chunk.section}" if getattr(chunk, "section", None) else "")
        score = getattr(chunk, "score", None)
        src = Source(index=len(self) + 1, type="doc", title=title[:300], doc_id=chunk.doc_id, filename=chunk.filename,
                     page=chunk.page, snippet=_snippet(chunk.text),
                     score=float(score) if score is not None else None)
        return self._add(key, src, chunk.text)

    def url_for(self, index: int) -> str | None:
        if 1 <= index <= len(self):
            return self._entries[index - 1].source.url
        return None

    def context_for(self, index: int) -> str | None:
        """Full text the model saw for source [index] (page text / chunk text / snippet)."""
        if 1 <= index <= len(self):
            return self._entries[index - 1].context
        return None

    def sources(self) -> list[dict[str, Any]]:
        return [e.source.dump() for e in self._entries]

    def render(self, budget_chars: int) -> str:
        """Compact numbered context block; long texts share whatever budget short ones leave."""
        if not self._entries:
            return ""
        alloc: dict[int, int] = {}
        remaining, left = max(budget_chars, _MIN_SHARE * len(self)), len(self)
        for e in sorted(self._entries, key=lambda e: len(e.context)):
            share = max(_MIN_SHARE, remaining // left)
            alloc[e.source.index] = min(len(e.context), share)
            remaining -= alloc[e.source.index]
            left -= 1
        blocks = []
        for e in self._entries:
            s = e.source
            if s.type == "web":
                head = f"[{s.index}] {s.title} — {s.domain} ({s.url})"
            else:
                head = f"[{s.index}] {s.title}" + (f" (page {s.page})" if s.page else "")
            blocks.append(f"{head}\n{_clip(e.context, alloc[s.index]) or s.snippet}")
        return "\n\n".join(blocks)
