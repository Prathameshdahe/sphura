"""Google sign-in through Supabase, the providers endpoint and ADMIN_EMAILS."""
from __future__ import annotations

import httpx

from app.api import auth as auth_api
from app.core.config import settings


class _Resp:
    def __init__(self, status: int, data: dict) -> None:
        self.status_code = status
        self._data = data

    def json(self) -> dict:
        return self._data


def _configure(monkeypatch, google: bool = True) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_publishable_key", "sb_publishable_test")
    monkeypatch.setattr(auth_api, "_providers_cache", {"at": 0.0, "google": False})

    def fake_get(url, headers=None, timeout=None):  # noqa: ANN001
        if url.endswith("/auth/v1/settings"):
            return _Resp(200, {"external": {"google": google, "email": True}})
        if headers and headers.get("Authorization") == "Bearer good-token":
            return _Resp(200, {"email": "Prathamesh@Example.com", "user_metadata": {"full_name": "Prathamesh D"}})
        return _Resp(401, {"msg": "invalid JWT"})

    monkeypatch.setattr(auth_api.httpx, "get", fake_get)


def test_providers_hide_google_until_supabase_enables_it(client, monkeypatch):
    assert client.get("/api/auth/providers").json() == {"google": {"enabled": False, "supabaseUrl": None,
                                                                   "anonKey": None}}
    _configure(monkeypatch, google=False)
    assert client.get("/api/auth/providers").json()["google"]["enabled"] is False
    _configure(monkeypatch, google=True)
    google = client.get("/api/auth/providers").json()["google"]
    assert google == {"enabled": True, "supabaseUrl": "https://example.supabase.co", "anonKey": "sb_publishable_test"}


def test_supabase_token_signs_in_and_admin_emails_are_admins(client, monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "admin_emails", "prathamesh@example.com")
    assert client.post("/api/auth/oauth/supabase", json={"accessToken": "bad"}).status_code == 401
    r = client.post("/api/auth/oauth/supabase", json={"accessToken": "good-token"})
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "prathamesh@example.com" and me["name"] == "Prathamesh D" and me["isAdmin"] is True
    assert client.get("/api/auth/me").json()["id"] == me["id"]
    again = client.post("/api/auth/oauth/supabase", json={"accessToken": "good-token"}).json()
    assert again["id"] == me["id"]  # same account on the next Google sign-in


def test_google_sign_in_is_404_when_supabase_is_not_configured(client):
    assert client.post("/api/auth/oauth/supabase", json={"accessToken": "x"}).status_code == 404


def test_supabase_unreachable_is_a_502(client, monkeypatch):
    _configure(monkeypatch)

    def boom(*_a, **_k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(auth_api.httpx, "get", boom)
    assert client.post("/api/auth/oauth/supabase", json={"accessToken": "good-token"}).status_code == 502


def test_admin_emails_replace_the_first_user_rule(client, monkeypatch):
    from app.api.auth import _starts_as_admin

    monkeypatch.setattr(settings, "admin_emails", "")
    assert _starts_as_admin("a@example.com", True) and not _starts_as_admin("a@example.com", False)
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    assert not _starts_as_admin("a@example.com", True)  # only the listed email, even on an empty database
    assert _starts_as_admin("boss@example.com", False)
