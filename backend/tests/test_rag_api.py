"""End-to-end tests for /api/documents + ingestion + hybrid search (real models, embedded Qdrant)."""
from __future__ import annotations

import asyncio
import importlib.util
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_token, hash_password
from app.db.base import session_scope
from app.db.models import Chunk, Conversation, Document, User
from app.main import app
from app.rag import ingest, store
from app.rag.service import ingest_document, search_documents
from tests.conftest import _register
from tests.test_rag_fixtures import (
    CSV_HEADER, DOCX_SENTENCES, PDF_SENTENCES, make_csv, make_docx, make_pdf, make_png, make_scanned_pdf, normalise,
)

READY_TIMEOUT_S = 300


def _make_user(client: TestClient, name: str) -> dict:
    """Register through the auth API when it exists, else create the user directly (auth built separately)."""
    if importlib.util.find_spec("app.api.auth") is not None:
        return _register(client, name)
    with session_scope() as db:
        u = User(email=f"{name.lower()}-{uuid.uuid4().hex[:8]}@example.com", name=name,
                 password_hash=hash_password("correct-horse-1"))
        db.add(u)
        db.flush()
        uid = u.id
    return {"user": {"id": uid}, "headers": {"Authorization": f"Bearer {create_token(uid)}"}}


def _upload(client: TestClient, who: dict, path_or_name: Path | str, content: bytes | None = None,
            conversation_id: str | None = None):
    name = path_or_name if isinstance(path_or_name, str) else path_or_name.name
    data = content if content is not None else Path(path_or_name).read_bytes()
    form = {"conversationId": conversation_id} if conversation_id else None
    return client.post("/api/documents", files={"file": (name, data, "application/octet-stream")}, data=form,
                       headers=who["headers"])


def _wait(client: TestClient, who: dict, doc_id: str) -> dict:
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        r = client.get(f"/api/documents/{doc_id}", headers=who["headers"])
        assert r.status_code == 200, r.text
        if r.json()["status"] in ("ready", "error"):
            return r.json()
        time.sleep(0.25)
    raise AssertionError(f"document {doc_id} not processed within {READY_TIMEOUT_S}s")


def _chunks(doc_id: str) -> list[Chunk]:
    with session_scope() as db:
        return list(db.scalars(select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.chunk_index)))


def _missing(sentences: list[str], chunks: list[Chunk]) -> list[str]:
    texts = [normalise(c.text) for c in chunks]
    return [s for s in sentences if not any(normalise(s) in t for t in texts)]


def _search(user_id: str, query: str, doc_ids: list[str] | None = None, k: int = 8):
    return asyncio.run(search_documents(user_id, query, doc_ids, k))


@pytest.fixture(scope="module")
def alice(client: TestClient) -> dict:
    return _make_user(client, "Alice")


@pytest.fixture(scope="module")
def bob(client: TestClient) -> dict:
    return _make_user(client, "Bob")


@pytest.fixture(scope="module")
def corpus(client: TestClient, alice: dict, tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict]:
    """Alice's PDF, DOCX and CSV, uploaded together and ingested in the background."""
    tmp = tmp_path_factory.mktemp("rag")
    files = {"pdf": make_pdf(tmp / "report.pdf"), "docx": make_docx(tmp / "review.docx"),
             "csv": make_csv(tmp / "weather.csv")}
    queued = {}
    for key, path in files.items():
        r = _upload(client, alice, path)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "queued" and body["filename"] == path.name and body["createdAt"].endswith("Z")
        queued[key] = body["id"]
    return {key: _wait(client, alice, doc_id) for key, doc_id in queued.items()}


def test_pdf_ingestion_pages_sections_and_no_text_lost(corpus: dict) -> None:
    info = corpus["pdf"]
    assert info["status"] == "ready", info["error"]
    assert info["pageCount"] == 3 and info["mimeType"] == "application/pdf" and info["ocrUsed"] is False
    chunks = _chunks(info["id"])
    assert info["chunkCount"] == len(chunks) and 2 <= len(chunks) <= 15
    assert not _missing(PDF_SENTENCES, chunks)
    orbit = next(c for c in chunks if "geostationary" in c.text)
    assert orbit.page_start == 3 and orbit.section.endswith("3 Orbital Mechanics")
    table = next(c for c in chunks if "Maize" in c.text)
    assert table.page_start <= 2 <= table.page_end and "|" in table.text
    assert all(1 <= c.page_start <= c.page_end <= 3 for c in chunks)
    assert store.count(document_id=info["id"]) == len(chunks)


def test_docx_and_csv_ingestion(corpus: dict) -> None:
    docx_info, csv_info = corpus["docx"], corpus["csv"]
    assert docx_info["status"] == "ready" and csv_info["status"] == "ready"
    assert not _missing(DOCX_SENTENCES, _chunks(docx_info["id"]))
    rows = _chunks(csv_info["id"])
    assert len(rows) >= 1 + 300 // 40
    header = "| " + " | ".join(CSV_HEADER) + " |"
    assert all(header in c.text for c in rows), "CSV header must be repeated in every chunk"
    assert "300 rows × 4 columns" in rows[0].text
    for i in (1, 150, 217, 300):
        assert any(f"\n| {i} | " in c.text for c in rows), f"row {i} lost"


@pytest.mark.parametrize("query, key, needle", [
    ("At what wavelength was the chlorophyll absorption peak measured?", "pdf", "680 nanometers"),
    ("How high above the equator does the relay satellite orbit?", "pdf", "35786"),
    ("What was the maize crop yield?", "pdf", "Maize"),
    ("How many machine learning engineers will the company hire?", "docx", "forty two"),
    ("rainfall recorded in Zanzibar", "csv", "Zanzibar"),
])
def test_search_ranks_the_right_chunk_first(corpus: dict, alice: dict, query: str, key: str, needle: str) -> None:
    results = _search(alice["user"]["id"], query, k=5)
    assert results, "no results"
    top = results[0]
    assert top.doc_id == corpus[key]["id"] and needle in top.text, (query, top)
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
    assert 0 <= top.score <= 1 and top.filename == corpus[key]["filename"]
    if key == "pdf":
        assert top.page in (2, 3)


def test_search_respects_doc_filter(corpus: dict, alice: dict) -> None:
    only_docx = _search(alice["user"]["id"], "chlorophyll absorption peak", [corpus["docx"]["id"]])
    assert all(r.doc_id == corpus["docx"]["id"] for r in only_docx)
    assert _search(alice["user"]["id"], "   ") == []


def test_user_isolation(client: TestClient, corpus: dict, alice: dict, bob: dict) -> None:
    doc_id = corpus["pdf"]["id"]
    assert client.get(f"/api/documents/{doc_id}", headers=bob["headers"]).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=bob["headers"]).status_code == 404
    assert doc_id not in [d["id"] for d in client.get("/api/documents", headers=bob["headers"]).json()]
    assert _search(bob["user"]["id"], "chlorophyll absorption peak") == []
    assert _search(bob["user"]["id"], "chlorophyll absorption peak", [doc_id]) == []
    assert client.get(f"/api/documents/{doc_id}").status_code == 401
    mine = client.get("/api/documents", headers=alice["headers"]).json()
    assert {corpus[k]["id"] for k in corpus} <= {d["id"] for d in mine}
    times = [d["createdAt"] for d in mine]
    assert times == sorted(times, reverse=True)


def test_reingest_is_idempotent(corpus: dict) -> None:
    doc_id = corpus["docx"]["id"]
    before = len(_chunks(doc_id))
    ingest_document(doc_id)
    assert len(_chunks(doc_id)) == before == store.count(document_id=doc_id)


def test_delete_removes_row_chunks_vectors_and_file(client: TestClient, alice: dict) -> None:
    text = "Delete me. " + " ".join(f"Temporary fact {i} about the archive." for i in range(60))
    r = _upload(client, alice, "temp.txt", text.encode())
    assert r.status_code == 200, r.text
    info = _wait(client, alice, r.json()["id"])
    assert info["status"] == "ready" and info["chunkCount"] >= 1
    with session_scope() as db:
        path = Path(db.get(Document, info["id"]).storage_path)
    assert path.exists() and store.count(document_id=info["id"]) == info["chunkCount"]

    assert client.delete(f"/api/documents/{info['id']}", headers=alice["headers"]).status_code == 204
    assert client.get(f"/api/documents/{info['id']}", headers=alice["headers"]).status_code == 404
    assert not path.exists()
    assert store.count(document_id=info["id"]) == 0 and _chunks(info["id"]) == []


def test_delete_during_ingestion_leaves_nothing_behind(alice: dict) -> None:
    """The row is deleted while the worker is embedding: the worker must remove its own vectors and file."""
    path = settings.upload_dir / f"{uuid.uuid4()}.txt"
    path.write_text("Ephemeral notes about the vanishing ledger. " * 60, "utf-8")
    with session_scope() as db:
        doc = Document(user_id=alice["user"]["id"], filename="gone.txt", mime_type="text/plain",
                       size_bytes=path.stat().st_size, sha256="0" * 64, storage_path=str(path), status="queued")
        db.add(doc)
        db.flush()
        doc_id = doc.id
    job = ingest._start(doc_id)
    assert job is not None
    with session_scope() as db:
        db.delete(db.get(Document, doc_id))
    ingest._ingest(job)
    assert store.count(document_id=doc_id) == 0 and _chunks(doc_id) == [] and not path.exists()


def test_ingestion_pool_restarts_after_shutdown(client: TestClient, alice: dict) -> None:
    ingest.shutdown()
    r = _upload(client, alice, "after.txt", b"Uploaded after the ingestion pool was shut down.")
    assert r.status_code == 200, r.text
    assert _wait(client, alice, r.json()["id"])["status"] == "ready"


def test_rejects_unsupported_mismatched_empty_and_oversized(client: TestClient, alice: dict,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    before = set(settings.upload_dir.iterdir())
    r = _upload(client, alice, "tool.exe", b"MZ\x90\x00")
    assert r.status_code == 415 and ".exe" in r.json()["detail"]
    r = _upload(client, alice, "fake.pdf", b"just some text pretending to be a pdf")
    assert r.status_code == 415 and isinstance(r.json()["detail"], str)
    assert _upload(client, alice, "empty.txt", b"").status_code == 400

    monkeypatch.setattr(settings, "max_upload_mb", 1)
    r = _upload(client, alice, "big.txt", b"a" * (1024 * 1024 + 10))
    assert r.status_code == 413 and "1 MB" in r.json()["detail"]
    assert set(settings.upload_dir.iterdir()) == before, "rejected uploads must not leave files behind"


def test_conversation_must_belong_to_user(client: TestClient, alice: dict, bob: dict) -> None:
    with session_scope() as db:
        mine = Conversation(user_id=alice["user"]["id"], title="Mine")
        theirs = Conversation(user_id=bob["user"]["id"], title="Theirs")
        db.add_all([mine, theirs])
        db.flush()
        mine_id, theirs_id = mine.id, theirs.id
    body = b"Notes attached to a conversation."
    assert _upload(client, alice, "n.txt", body, conversation_id=theirs_id).status_code == 404
    assert _upload(client, alice, "n.txt", body, conversation_id=str(uuid.uuid4())).status_code == 404
    r = _upload(client, alice, "n.txt", body, conversation_id=mine_id)
    assert r.status_code == 200 and r.json()["conversationId"] == mine_id
    listed = client.get("/api/documents", params={"conversationId": mine_id}, headers=alice["headers"]).json()
    assert [d["id"] for d in listed] == [r.json()["id"]]
    _wait(client, alice, r.json()["id"])


def test_scanned_pdf_and_image_without_ocr_fail_helpfully(client: TestClient, alice: dict, tmp_path: Path) -> None:
    for path in (make_scanned_pdf(tmp_path / "scan.pdf"), make_png(tmp_path / "photo.png")):
        r = _upload(client, alice, path)
        assert r.status_code == 200, r.text
        info = _wait(client, alice, r.json()["id"])
        assert info["status"] == "error" and "GEMINI_API_KEY" in info["error"] and info["chunkCount"] == 0


def test_pending_documents_resume_at_startup(alice: dict) -> None:
    """The documents router's lifespan (merged into the app by main.py) re-queues stuck documents."""
    path = settings.upload_dir / f"{uuid.uuid4()}.md"
    path.write_text("# Recovery\n\nThis document was stuck in the queue when the server stopped.", "utf-8")
    with session_scope() as db:
        doc = Document(user_id=alice["user"]["id"], filename="stuck.md", mime_type="text/markdown",
                       size_bytes=path.stat().st_size, sha256="0" * 64, storage_path=str(path), status="processing")
        db.add(doc)
        db.flush()
        doc_id = doc.id
    with TestClient(app) as fresh:  # runs the app lifespan again → recover_pending()
        info = _wait(fresh, alice, doc_id)
    assert info["status"] == "ready" and info["chunkCount"] == 1
