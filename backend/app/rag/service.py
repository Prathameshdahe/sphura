"""Public interface of the document-intelligence engine (see docs/CONTRACT.md → Backend internal interfaces)."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.core.config import settings
from app.db.models import Document
from app.rag import embeddings, ocr, store
from app.rag.ingest import delete_document_artifacts, ingest_document, recover_pending, schedule_ingestion
from app.rag.ingest import shutdown as _shutdown_ingestion
from app.rag.retriever import RetrievedChunk, invalidate_cache, search_documents

log = logging.getLogger("sphura.rag")

__all__ = [
    "RetrievedChunk", "search_documents", "schedule_ingestion", "delete_document_artifacts", "recover_pending",
    "ingest_document", "document_path", "vector_store_kind", "embedding_model_name", "ocr_engine", "on_startup",
    "on_shutdown",
]


def document_path(doc: Document) -> Path:
    """Absolute path of a stored upload (e.g. to send an image attachment to a vision model)."""
    return Path(doc.storage_path)


def vector_store_kind() -> str:
    """Vector store kind for /api/health: qdrant (server) or qdrant-local (embedded)."""
    return store.kind()


def embedding_model_name() -> str:
    return settings.embedding_model


def ocr_engine() -> str | None:
    """Active OCR engine: rapidocr, gemini, or None when OCR is unavailable."""
    return ocr.engine_name()


def on_startup() -> None:
    """Called from the documents router lifespan: resume pending ingestion and warm the models."""
    try:
        recover_pending()
    except Exception as exc:  # noqa: BLE001 — never block API startup
        log.warning("could not recover pending documents: %s", exc)
    invalidate_cache()
    if not settings.sphura_enable_mock:  # tests load models on demand
        threading.Thread(target=_warmup, name="sphura-rag-warmup", daemon=True).start()


def on_shutdown() -> None:
    """Called from the documents router lifespan: cancel queued jobs so Ctrl+C does not wait for them."""
    _shutdown_ingestion()


def _warmup() -> None:
    try:
        embeddings.warmup()
    except Exception as exc:  # noqa: BLE001
        log.warning("model warmup failed (will retry on first use): %s", exc)
