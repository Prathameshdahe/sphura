from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import User


def _email(prefix: str = "auth") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def test_register_sets_httponly_cookie_and_returns_camel_user(client):
    email = _email().upper()
    r = client.post("/api/auth/register", json={"email": email, "password": "correct-horse-1", "name": "Ada"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"id", "email", "name", "isAdmin", "createdAt"}
    assert body["email"] == email.lower()
    assert body["createdAt"].endswith("Z")
    cookie = r.headers["set-cookie"].lower()
    assert "sphura_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie

    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["id"] == body["id"]

    out = client.post("/api/auth/logout")
    assert out.status_code == 200 and out.json() == {"ok": True}
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()


def test_first_registered_user_is_the_only_admin(client, user, other_user):
    with session_scope() as db:
        users = db.scalars(select(User).order_by(User.created_at)).all()
        assert users[0].is_admin
        assert not any(u.is_admin for u in users[1:])


def test_duplicate_email_is_409_case_insensitive(client, user):
    r = client.post("/api/auth/register",
                    json={"email": user["email"].upper(), "password": "another-pass-9", "name": "Dup"})
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str)


def test_login_success_and_generic_failures(client, user):
    ok = client.post("/api/auth/login", json={"email": user["email"].upper(), "password": user["password"]})
    assert ok.status_code == 200 and ok.json()["id"] == user["user"]["id"]
    assert "sphura_session=" in ok.headers["set-cookie"]
    client.cookies.clear()

    wrong = client.post("/api/auth/login", json={"email": user["email"], "password": "nope-nope-nope"})
    missing = client.post("/api/auth/login", json={"email": _email("ghost"), "password": "whatever-123"})
    for r in (wrong, missing):
        assert r.status_code == 401
        assert r.json() == {"detail": "Invalid email or password"}


def test_validation_errors_are_flat_strings(client):
    r = client.post("/api/auth/register", json={"email": "not-an-email", "password": "short", "name": ""})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]


def test_bearer_token_and_unauthenticated_access(client, user):
    assert client.get("/api/auth/me", headers=user["headers"]).json()["email"] == user["email"]
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_login_rate_limit(client, user):
    for _ in range(10):
        r = client.post("/api/auth/login", json={"email": user["email"], "password": "wrong-password"})
        assert r.status_code == 401
    blocked = client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})
    assert blocked.status_code == 429
    assert isinstance(blocked.json()["detail"], str)
    client.cookies.clear()


def test_cross_site_cookie_mode_marks_the_session_cookie_secure(client, monkeypatch):
    """COOKIE_SAMESITE=none (frontend on another domain via VITE_API_URL) must also send Secure."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "cookie_samesite", "none")
    email = f"cross-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correct-horse-1", "name": "Cross"})
    client.cookies.clear()
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "samesite=none" in cookie and "secure" in cookie and "httponly" in cookie
