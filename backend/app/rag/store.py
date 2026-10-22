"""Qdrant vector store: remote server when QDRANT_URL is set, else embedded on-disk Qdrant in data_dir."""
from __future__ import annotations

import atexit
import logging
import threading
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from app.core.config import settings
from app.rag import embeddings

log = logging.getLogger("sphura.rag.store")

# Embedded Qdrant is a single-process store guarded by a file lock; serialise access to it.
_lock = threading.RLock()
_client: QdrantClient | None = None
_collection: str | None = None


@dataclass
class VectorPoint:
    id: str              # chunk id (UUID) — also the Qdrant point id
    vector: list[float]
    payload: dict


def kind() -> str:
    return "qdrant" if settings.qdrant_url else "qdrant-local"


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        if settings.qdrant_url:
            _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=30)
        else:
            path = settings.data_dir / "qdrant"
            path.mkdir(parents=True, exist_ok=True)
            _client = QdrantClient(path=str(path))
        log.info("vector store: %s", kind())
    return _client


def _ensure_collection() -> str:
    """Create the collection (cosine, embedding dim) and payload indexes if missing; returns its name."""
    global _collection
    if _collection is not None:
        return _collection
    client, dim = _get_client(), embeddings.dimension()
    name = settings.qdrant_collection
    if client.collection_exists(name):
        size = client.get_collection(name).config.params.vectors.size  # type: ignore[union-attr]
        if size != dim:  # embedding model changed: keep old vectors untouched, use a sized collection
            log.warning("collection %s has dim %s but model gives %s; using %s_%s", name, size, dim, name, dim)
            name = f"{name}_{dim}"
    if not client.collection_exists(name):
        client.create_collection(name, vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE))
        if settings.qdrant_url:  # payload indexes are a no-op (with a warning) in embedded mode
            for field in ("user_id", "document_id"):
                client.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)
        log.info("created collection %s (dim=%s)", name, dim)
    _collection = name
    return name


def _user_filter(user_id: str | None = None, doc_ids: list[str] | None = None) -> models.Filter:
    must: list[models.Condition] = []
    if user_id is not None:
        must.append(models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)))
    if doc_ids is not None:
        must.append(models.FieldCondition(key="document_id", match=models.MatchAny(any=list(doc_ids))))
    return models.Filter(must=must)


def upsert(points: list[VectorPoint], batch: int = 256) -> None:
    with _lock:
        name = _ensure_collection()
        client = _get_client()
        for i in range(0, len(points), batch):
            client.upsert(name, points=[models.PointStruct(id=p.id, vector=p.vector, payload=p.payload)
                                        for p in points[i:i + batch]], wait=True)


def search(vector: list[float], user_id: str, doc_ids: list[str] | None, limit: int = 30) -> list[models.ScoredPoint]:
    """Dense top-`limit`, filtered by owner (and documents) inside Qdrant."""
    with _lock:
        name = _ensure_collection()
        result = _get_client().query_points(name, query=vector, query_filter=_user_filter(user_id, doc_ids),
                                            limit=limit, with_payload=True)
    return list(result.points)


def delete_by_document(document_id: str) -> None:
    with _lock:
        name = _ensure_collection()
        _get_client().delete(name, points_selector=models.FilterSelector(filter=_user_filter(doc_ids=[document_id])),
                             wait=True)


@atexit.register
def close() -> None:
    """Release the client (and the embedded store's file lock) before interpreter teardown."""
    global _client, _collection
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:  # noqa: BLE001 — best effort at shutdown
                pass
        _client, _collection = None, None


def count(document_id: str | None = None, user_id: str | None = None) -> int:
    with _lock:
        name = _ensure_collection()
        doc_ids = [document_id] if document_id else None
        return _get_client().count(name, count_filter=_user_filter(user_id, doc_ids), exact=True).count
