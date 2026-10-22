"""Test setup: isolated temp data dir + SQLite + embedded Qdrant, deterministic mock LLM.

Env vars MUST be set before `app` is imported (settings are read at import time).
"""
from __future__ import annotations

import os
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="sphura-test-")
os.environ["DATA_DIR"] = _TMP
os.environ["DATABASE_URL"] = ""
os.environ["QDRANT_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["SPHURA_ENABLE_MOCK"] = "1"
os.environ["DEFAULT_MODEL"] = "mock:sphura-mock"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""
os.environ["CURATED_MODELS"] = "0"   # tests see the full catalog; tests/test_ensemble.py opts in
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_PUBLISHABLE_KEY"] = ""
os.environ["ADMIN_EMAILS"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9/v1"   # unreachable on purpose
os.environ["LMSTUDIO_BASE_URL"] = "http://127.0.0.1:9/v1"
os.environ["SPHURA_WINDOWS_OCR"] = "0"   # "no OCR engine" by default; tests opt in (tests/test_e2e_fixes.py)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _register(client: TestClient, name: str = "Tester") -> dict:
    email = f"{name.lower()}-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correct-horse-1", "name": name})
    assert r.status_code == 200, r.text
    token = client.cookies.get("sphura_session")
    client.cookies.clear()
    assert token, "register must set the sphura_session cookie"
    return {"email": email, "password": "correct-horse-1", "user": r.json(),
            "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def user(client: TestClient) -> dict:
    """A fresh registered user. Use `user['headers']` for authenticated calls."""
    return _register(client, "Alice")


@pytest.fixture
def other_user(client: TestClient) -> dict:
    return _register(client, "Bob")


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse a full SSE body into [(event, data), ...]; ignores comments/heartbeats."""
    import json

    events: list[tuple[str, dict]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name, data_lines = "message", []
        for line in block.split("\n"):
            if not line or line.startswith(":"):
                continue
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            events.append((name, json.loads("\n".join(data_lines))))
    return events
