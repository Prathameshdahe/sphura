"""Register / login / logout / me, plus "Continue with Google" through Supabase Auth.

The JWT lives in an httpOnly cookie (Bearer also accepted). Google sign-in happens in the browser with Supabase;
the frontend then posts the Supabase access token to /auth/oauth/supabase, which checks it against Supabase
(`GET /auth/v1/user`), finds or creates the local account with that email and sets the same session cookie.
Emails listed in ADMIN_EMAILS are admins however they sign in.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import deque

import httpx

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.store import to_utc
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import DUMMY_HASH, create_token, hash_password, verify_password
from app.db.base import get_db
from app.db.models import User
from app.schemas import CamelModel, LoginIn, RegisterIn, UserOut

log = logging.getLogger("sphura.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

SUPABASE_TIMEOUT_S = 10.0
PROVIDERS_TTL_S = 60.0
_providers_cache: dict[str, object] = {"at": 0.0, "google": False}


class SupabaseTokenIn(CamelModel):
    access_token: str

LOGIN_LIMIT = 10
LOGIN_WINDOW_S = 300.0
_failures: dict[str, deque[float]] = {}
_failures_lock = threading.Lock()


def _user_out(user: User) -> dict:
    return UserOut(id=user.id, email=user.email, name=user.name, is_admin=user.is_admin,
                   created_at=to_utc(user.created_at)).dump()


def _set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        settings.cookie_name, create_token(user_id), max_age=settings.jwt_expire_hours * 3600, path="/",
        httponly=True, samesite=settings.cookie_samesite, secure=settings.session_cookie_secure,
    )


def _limit_key(request: Request, email: str) -> str:
    return f"{request.client.host if request.client else '?'}|{email}"


def _too_many(key: str) -> bool:
    now = time.monotonic()
    with _failures_lock:
        hits = _failures.get(key)
        while hits and now - hits[0] > LOGIN_WINDOW_S:
            hits.popleft()
        return bool(hits) and len(hits) >= LOGIN_LIMIT


def _record_failure(key: str) -> None:
    now = time.monotonic()
    with _failures_lock:
        if len(_failures) > 10_000:  # forget keys whose failures have all expired
            for stale in [k for k, hits in _failures.items() if not hits or now - hits[-1] > LOGIN_WINDOW_S]:
                del _failures[stale]
        _failures.setdefault(key, deque()).append(now)


@router.post("/register")
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    is_first = not db.scalar(select(func.count(User.id)))
    user = User(email=email, name=body.name.strip() or email.split("@")[0], password_hash=hash_password(body.password),
                is_admin=_starts_as_admin(email, is_first))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists") from None
    _set_session_cookie(response, user.id)
    return _user_out(user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    key = _limit_key(request, email)
    if _too_many(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts. Try again in a few minutes.")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    # Always run bcrypt so response time doesn't reveal whether the email exists.
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid:
        _record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    with _failures_lock:
        _failures.pop(key, None)
    _promote_if_listed(db, user)
    _set_session_cookie(response, user.id)
    return _user_out(user)


def _starts_as_admin(email: str, is_first: bool) -> bool:
    """ADMIN_EMAILS decides when it is set; without it the first account on a fresh database is the admin."""
    return email in settings.admin_email_set if settings.admin_email_set else is_first


def _promote_if_listed(db: Session, user: User) -> None:
    """An ADMIN_EMAILS account that was created before the list named it becomes an admin on its next sign-in."""
    if not user.is_admin and user.email.lower() in settings.admin_email_set:
        user.is_admin = True
        db.commit()


def _google_enabled() -> bool:
    """True when Supabase is configured and its Google provider is switched on (checked at most once a minute)."""
    if not settings.google_login_enabled:
        return False
    now = time.monotonic()
    if now - float(_providers_cache["at"]) < PROVIDERS_TTL_S:
        return bool(_providers_cache["google"])
    try:
        r = httpx.get(f"{settings.supabase_url.rstrip('/')}/auth/v1/settings",
                      headers={"apikey": settings.supabase_publishable_key}, timeout=SUPABASE_TIMEOUT_S)
        enabled = r.status_code == 200 and bool((r.json().get("external") or {}).get("google"))
    except (httpx.HTTPError, ValueError) as exc:
        log.info("could not read Supabase auth settings: %s", exc)
        enabled = False
    _providers_cache.update(at=now, google=enabled)
    return enabled


@router.get("/providers")
def providers() -> dict:
    """Which sign-in methods the login page offers. The Supabase URL and publishable key are public by design."""
    enabled = _google_enabled()
    return {"google": {"enabled": enabled,
                       "supabaseUrl": settings.supabase_url.rstrip("/") if enabled else None,
                       "anonKey": settings.supabase_publishable_key if enabled else None}}


@router.post("/oauth/supabase")
def oauth_supabase(body: SupabaseTokenIn, response: Response, db: Session = Depends(get_db)) -> dict:
    """Exchange a Supabase access token (after Google sign-in) for a Sphura session."""
    if not settings.google_login_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google sign-in isn't configured on this server")
    try:
        r = httpx.get(f"{settings.supabase_url.rstrip('/')}/auth/v1/user", timeout=SUPABASE_TIMEOUT_S,
                      headers={"apikey": settings.supabase_publishable_key,
                               "Authorization": f"Bearer {body.access_token}"})
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Couldn't reach Supabase to check the sign-in") from None
    if r.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google sign-in expired or was rejected. Please try again.")
    info = r.json()
    email = str(info.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your Google account didn't share an email address")
    meta = info.get("user_metadata") or {}
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        is_first = not db.scalar(select(func.count(User.id)))
        name = str(meta.get("full_name") or meta.get("name") or email.split("@")[0])[:120]
        # no usable password: this account signs in with Google (an admin can still be given one via ADMIN_PASSWORD)
        user = User(email=email, name=name, password_hash=hash_password(secrets.token_urlsafe(32)),
                    is_admin=_starts_as_admin(email, is_first))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(func.lower(User.email) == email))
            if user is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Couldn't create the account; try again") from None
    else:
        _promote_if_listed(db, user)
    _set_session_cookie(response, user.id)
    return _user_out(user)


def bootstrap_admin() -> None:
    """ADMIN_PASSWORD set → the first ADMIN_EMAILS address gets an admin account with that password (created, or
    its password and role brought in line). Runs at start-up; the password itself is never logged."""
    if not settings.admin_password or not settings.admin_email_set:
        return
    from app.db.base import session_scope

    email = settings.admin_emails.split(",")[0].strip().lower()
    with session_scope() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            db.add(User(email=email, name=email.split("@")[0], password_hash=hash_password(settings.admin_password),
                        is_admin=True))
            log.info("admin account created for %s", email)
            return
        if not verify_password(settings.admin_password, user.password_hash):
            user.password_hash = hash_password(settings.admin_password)
        user.is_admin = True


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(settings.cookie_name, path="/", httponly=True, samesite=settings.cookie_samesite,
                           secure=settings.session_cookie_secure)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return _user_out(user)
