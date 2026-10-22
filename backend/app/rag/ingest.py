"""Background ingestion: parse → chunk → embed → index, with status queued → processing → ready | error."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select

from app.db.base import session_scope
from app.db.models import Chunk, Document, new_id
from app.rag import embeddings, store
from app.rag.blocks import ParsedDocument, ParseError
from app.rag.chunker import ChunkDraft, chunk_blocks
from app.rag.formats import IMAGE_EXTENSIONS
from app.rag.parsers import parse_file

log = logging.getLogger("sphura.rag.ingest")

SCANNED_HINT = "Scanned document — add GEMINI_API_KEY to enable OCR"

_executor: ThreadPoolExecutor | None = None
_inflight: set[str] = set()
_inflight_lock = threading.Lock()


@dataclass
class _Job:
    document_id: str
    user_id: str
    filename: str
    path: Path
    timings: dict[str, int] = field(default_factory=dict)

    def tick(self, name: str, started: float) -> float:
        now = time.perf_counter()
        self.timings[name] = round((now - started) * 1000)
        return now


def schedule_ingestion(document_id: str) -> None:
    """Queue a document for ingestion (no-op if it is already queued/running in this process)."""
    global _executor
    with _inflight_lock:
        if document_id in _inflight:
            return
        _inflight.add(document_id)
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sphura-ingest")
        future = _executor.submit(_run, document_id)
    # also fires for jobs cancelled by shutdown(), so they can be scheduled again
    future.add_done_callback(lambda _f: _discard(document_id))


def _discard(document_id: str) -> None:
    with _inflight_lock:
        _inflight.discard(document_id)


def shutdown() -> None:
    """App shutdown: drop jobs that have not started (recover_pending() re-queues them on the next start)."""
    global _executor
    with _inflight_lock:
        pool, _executor = _executor, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def _run(document_id: str) -> None:
    try:
        ingest_document(document_id)
    except Exception:  # noqa: BLE001 — a worker must never die silently
        log.exception("ingestion crashed for %s", document_id)


def _start(document_id: str) -> _Job | None:
    with session_scope() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return None
        doc.status, doc.error = "processing", None
        return _Job(doc.id, doc.user_id, doc.filename, Path(doc.storage_path))


def _empty_message(parsed: ParsedDocument, filename: str) -> str:
    if parsed.ocr_needed:
        return SCANNED_HINT
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "No text was found in this image"
    if ext == ".pdf":
        return "No selectable text found in this PDF"
    return "No readable text found in this file"


def ingest_document(document_id: str) -> None:
    """Synchronous ingestion of one document (runs in the ingestion thread pool)."""
    job = _start(document_id)
    if job is None:
        return
    try:
        _ingest(job)
    except (ParseError, embeddings.EmbeddingUnavailable) as exc:
        _fail(job, str(exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("ingestion failed for %s", document_id)
        _fail(job, f"Could not process this file ({type(exc).__name__})")


def _ingest(job: _Job) -> None:
    if not job.path.exists():
        raise ParseError("The uploaded file is missing on the server — please upload it again")
    t = time.perf_counter()
    parsed = parse_file(job.path, job.filename)
    t = job.tick("parseMs", t)
    drafts = chunk_blocks(parsed.blocks)
    t = job.tick("chunkMs", t)
    if not drafts:
        raise ParseError(_empty_message(parsed, job.filename))
    vectors = embeddings.embed_passages([d.embed_text for d in drafts])
    t = job.tick("embedMs", t)
    chunk_ids = [new_id() for _ in drafts]
    store.delete_by_document(job.document_id)  # idempotent re-ingest
    store.upsert([
        store.VectorPoint(cid, vec, {
            "user_id": job.user_id, "document_id": job.document_id, "chunk_id": cid, "chunk_index": i,
            "page": d.page_start, "filename": job.filename, "section": d.section,
        })
        for i, (cid, vec, d) in enumerate(zip(chunk_ids, vectors, drafts))
    ])
    job.tick("indexMs", t)
    _finish(job, parsed, drafts, chunk_ids)


def _finish(job: _Job, parsed: ParsedDocument, drafts: list[ChunkDraft], chunk_ids: list[str]) -> None:
    with session_scope() as db:
        doc = db.get(Document, job.document_id)
        if doc is None:  # deleted while we were working: drop what we wrote
            _cleanup_orphan(job)
            return
        db.execute(delete(Chunk).where(Chunk.document_id == job.document_id))
        db.add_all([
            Chunk(id=cid, document_id=job.document_id, user_id=job.user_id, chunk_index=i, text=d.text,
                  page_start=d.page_start, page_end=d.page_end, section=d.section, token_count=d.token_count)
            for i, (cid, d) in enumerate(zip(chunk_ids, drafts))
        ])
        doc.status, doc.error = "ready", None
        doc.page_count, doc.chunk_count, doc.ocr_used = parsed.page_count, len(drafts), parsed.ocr_used
        doc.meta = {**(doc.meta or {}), "ingestId": uuid.uuid4().hex, "timings": job.timings,
                    "chars": parsed.char_count, "blocks": len(parsed.blocks), "warnings": parsed.warnings}
    log.info("ingested %s (%s): pages=%s blocks=%d chunks=%d ocr=%s | parse %sms chunk %sms embed %sms index %sms",
             job.document_id, job.filename, parsed.page_count, len(parsed.blocks), len(drafts), parsed.ocr_used,
             job.timings.get("parseMs"), job.timings.get("chunkMs"), job.timings.get("embedMs"),
             job.timings.get("indexMs"))


def _fail(job: _Job, message: str) -> None:
    try:
        store.delete_by_document(job.document_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not clean vectors for %s: %s", job.document_id, exc)
    with session_scope() as db:
        db.execute(delete(Chunk).where(Chunk.document_id == job.document_id))
        doc = db.get(Document, job.document_id)
        gone = doc is None
        if doc is not None:
            doc.status, doc.error, doc.chunk_count = "error", message[:500], 0
            doc.meta = {**(doc.meta or {}), "timings": job.timings}
    if gone:
        _unlink(job.path)
    log.info("ingestion of %s (%s) failed: %s", job.document_id, job.filename, message)


def _cleanup_orphan(job: _Job) -> None:
    store.delete_by_document(job.document_id)
    _unlink(job.path)  # on Windows the delete request may have failed while the parser held the file open


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("could not delete %s: %s", path, exc)


def delete_document_artifacts(document_id: str, storage_path: str | Path | None = None) -> None:
    """Remove a document's chunks, vectors and stored file.

    Callers should delete the row first and pass its `storage_path`, so an ingestion finishing concurrently
    sees the row gone and cleans up after itself instead of leaving orphaned vectors.
    """
    with session_scope() as db:
        if storage_path is None:
            doc = db.get(Document, document_id)
            storage_path = doc.storage_path if doc is not None else None
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
    try:
        store.delete_by_document(document_id)
    except Exception as exc:  # noqa: BLE001 — never block a delete on the vector store
        log.warning("vector cleanup failed for %s: %s", document_id, exc)
    if storage_path:
        _unlink(Path(storage_path))


def recover_pending() -> int:
    """Re-queue documents left queued/processing by a previous run; returns how many."""
    with session_scope() as db:
        ids = list(db.scalars(select(Document.id).where(Document.status.in_(("queued", "processing")))))
    for document_id in ids:
        schedule_ingestion(document_id)
    if ids:
        log.info("re-queued %d pending document(s)", len(ids))
    return len(ids)
