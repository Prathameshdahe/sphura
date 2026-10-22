"""Owner-scoped document lookups for finance analytics (the stored upload is read directly with pandas)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import Document
from app.features.finance.report import is_tabular


@dataclass
class DocFile:
    id: str
    filename: str
    path: Path
    status: str


def load_owned(user_id: str, doc_id: str) -> DocFile | None:
    with session_scope() as db:
        doc = db.get(Document, doc_id)
        if doc is None or doc.user_id != user_id:
            return None
        return DocFile(doc.id, doc.filename, Path(doc.storage_path or ""), doc.status)


def load_tabular(user_id: str, doc_ids: list[str]) -> list[DocFile]:
    """The caller's CSV/XLSX documents among `doc_ids`, in request order (others are dropped)."""
    if not doc_ids:
        return []
    with session_scope() as db:
        rows = db.scalars(select(Document).where(Document.user_id == user_id, Document.id.in_(doc_ids))).all()
        by_id = {d.id: DocFile(d.id, d.filename, Path(d.storage_path or ""), d.status) for d in rows
                 if is_tabular(d.filename)}
    return [by_id[i] for i in dict.fromkeys(doc_ids) if i in by_id]
