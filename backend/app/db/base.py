from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_is_sqlite = settings.sqlalchemy_url.startswith("sqlite")
# Supabase's pooler (Supavisor) drops idle client connections, so every checkout is pinged and connections are
# recycled after a minute; the pool stays small to keep within the free tier's pooler limits.
engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    **({} if _is_sqlite else {"pool_size": 5, "max_overflow": 5, "pool_recycle": 60}),
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(conn, _record):  # noqa: ANN001
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """For background jobs / streaming: short-lived session, commit on success."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app.db import models  # noqa: F401  (register tables)

    Base.metadata.create_all(bind=engine)
