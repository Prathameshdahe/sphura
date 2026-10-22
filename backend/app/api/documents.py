"""Document upload / list / get / delete (docs/CONTRACT.md → /api/documents). Ingestion runs in the background."""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import Path
from typing import BinaryIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.base import get_db
from app.db.models import Chunk, Conversation, Document, User
from app.rag import service
from app.rag.formats import SUPPORTED_EXTENSIONS, mime_for, sniff_ok
from app.schemas import DocumentInfo

log = logging.getLogger("sphura.api.documents")

COPY_CHUNK = 1024 * 1024
SNIFF_BYTES = 2048


@asynccontextmanager
async def _lifespan(_app: object) -> AsyncIterator[None]:
    # Runs after the app's own startup handlers (init_db), because included lifespans nest inside them.
    service.on_startup()
    try:
        yield
    finally:
        service.on_shutdown()


router = APIRouter(prefix="/documents", tags=["documents"], lifespan=_lifespan)


class _TooLarge(Exception):
    pass


def _info(doc: Document) -> DocumentInfo:
    info = DocumentInfo.model_validate(doc)
    if info.created_at.tzinfo is None:  # SQLite drops tzinfo; values are stored in UTC
        info.created_at = info.created_at.replace(tzinfo=timezone.utc)
    return info


def _safe_filename(raw: str | None) -> str:
    name = re.sub(r"[\x00-\x1f\x7f]", "", (raw or "").replace("\\", "/").split("/")[-1]).strip()
    if len(name) > 200:
        stem, ext = Path(name).stem, Path(name).suffix[:20]
        name = stem[: 200 - len(ext)] + ext
    return name or "upload"


def _save_stream(src: BinaryIO, dest: Path, limit: int) -> tuple[int, str, bytes]:
    """Copy in chunks while hashing; raises _TooLarge as soon as `limit` bytes are exceeded."""
    digest, size, head = hashlib.sha256(), 0, b""
    with dest.open("wb") as out:
        while chunk := src.read(COPY_CHUNK):
            size += len(chunk)
            if size > limit:
                raise _TooLarge
            if len(head) < SNIFF_BYTES:
                head += chunk[: SNIFF_BYTES - len(head)]
            digest.update(chunk)
            out.write(chunk)
    return size, digest.hexdigest(), head


def _owned_document(db: Session, document_id: str, user: User) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


def _check_conversation(db: Session, conversation_id: str | None, user: User) -> str | None:
    if not conversation_id:
        return None
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv.id


@router.post("", response_model=DocumentInfo)
def upload_document(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None, alias="conversationId"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentInfo:
    filename = _safe_filename(file.filename)
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        shown = ext or "(no extension)"
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"Unsupported file type {shown}. Supported: {' '.join(SUPPORTED_EXTENSIONS)}")
    conv_id = _check_conversation(db, conversation_id, user)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.upload_dir / f"{uuid.uuid4()}{ext}"
    try:
        size, sha256, head = _save_stream(file.file, dest, settings.max_upload_mb * 1024 * 1024)
    except _TooLarge:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            f"File is larger than the {settings.max_upload_mb} MB limit") from None
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty")
    if not sniff_ok(ext, head):
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"The file content does not match its {ext} extension")

    doc = Document(user_id=user.id, conversation_id=conv_id, filename=filename, mime_type=mime_for(ext),
                   size_bytes=size, sha256=sha256, storage_path=str(dest.resolve()), status="queued")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    service.schedule_ingestion(doc.id)
    log.info("upload %s (%s, %d bytes) queued", doc.id, ext, size)
    return _info(doc)


@router.get("", response_model=list[DocumentInfo])
def list_documents(
    conversation_id: str | None = Query(default=None, alias="conversationId"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentInfo]:
    stmt = select(Document).where(Document.user_id == user.id)
    if conversation_id:
        stmt = stmt.where(Document.conversation_id == conversation_id)
    stmt = stmt.order_by(Document.created_at.desc())
    return [_info(d) for d in db.scalars(stmt)]


@router.get("/{document_id}", response_model=DocumentInfo)
def get_document(document_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DocumentInfo:
    return _info(_owned_document(db, document_id, user))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_document(document_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    doc = _owned_document(db, document_id, user)
    doc_id, storage_path = doc.id, doc.storage_path
    # Row first: an ingestion finishing concurrently then finds it gone and removes its own vectors.
    db.execute(delete(Chunk).where(Chunk.document_id == doc_id))  # bulk, instead of an ORM cascade load
    db.delete(doc)
    db.commit()
    service.delete_document_artifacts(doc_id, storage_path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
