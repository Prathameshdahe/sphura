from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

_ALGO = "HS256"
_ISSUER = "sphura"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except ValueError:
        return False


# Used to keep login timing constant when the email does not exist.
DUMMY_HASH = hash_password("sphura-timing-equaliser")


def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iss": _ISSUER,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expire_hours),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def decode_token(token: str) -> str | None:
    """Return the user id, or None if the token is invalid/expired."""
    try:
        data = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGO],
            issuer=_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    if data.get("typ") != "access":
        return None
    return str(data["sub"])
