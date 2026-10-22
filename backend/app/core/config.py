"""Central settings. Every value can be overridden by an env var or the repo-root `.env`."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sphura"
    version: str = "1.0.0"
    environment: str = "development"  # "production" refuses to start with insecure defaults

    data_dir: Path = BACKEND_DIR / "data"
    database_url: str = ""  # empty → sqlite file in data_dir
    # Supabase: Auth for "Continue with Google" (URL + publishable / anon key, both public by design)
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    # Accounts with these emails are admins (on sign-up, login and Google sign-in). ADMIN_PASSWORD, when set,
    # creates / resets the first admin's email-and-password login at start-up.
    admin_emails: str = ""
    admin_password: str = ""

    # auth
    jwt_secret: str = ""  # empty → generated once and persisted in data_dir/.jwt_secret
    jwt_expire_hours: int = 24 * 7
    cookie_name: str = "sphura_session"
    cookie_secure: bool = False
    # "lax" when the frontend reaches the API through its own origin (Vite proxy, nginx, a Vercel rewrite);
    # "none" when it calls the API on another domain (VITE_API_URL), which browsers only accept with Secure.
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # llm providers (all OpenAI-compatible)
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # NVIDIA API catalog (build.nvidia.com): OpenAI-compatible, free developer credits, key "nvapi-…"
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    # One best model per provider (CURATED_MODELS=1): the picker offers these three plus "Sphura Ensemble", which
    # asks all of them and merges the answers. When the NVIDIA model fails, NVIDIA_FAST_MODEL (Nemotron Lightning,
    # 3B active parameters) and then NVIDIA_FALLBACK_MODEL are tried before another provider.
    curated_models: bool = True
    groq_model: str = "openai/gpt-oss-120b"
    nvidia_model: str = "nvidia/nemotron-3.5-super-vl-120b-a12b"
    nvidia_fast_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    nvidia_fallback_model: str = "deepseek-ai/deepseek-v4.1-flash"
    local_model: str = "qwen3.5:4b"
    ollama_base_url: str = "http://localhost:11434/v1"
    lmstudio_base_url: str = "http://localhost:1234/v1"
    default_model: str = ""  # e.g. "groq:llama-3.3-70b-versatile"; empty → first available
    sphura_enable_mock: bool = False  # deterministic fake model for tests

    # web
    tavily_api_key: str = ""

    # rag
    qdrant_url: str = ""  # empty → embedded local Qdrant in data_dir/qdrant
    qdrant_api_key: str = ""
    qdrant_collection: str = "sphura_chunks"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    reranker_enabled: bool = True
    max_upload_mb: int = 25

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def sqlalchemy_url(self) -> str:
        """DATABASE_URL as SQLAlchemy wants it: a Supabase / Postgres "postgresql://" or "postgres://" URL is
        pointed at the psycopg 3 driver; empty → the SQLite file in data_dir."""
        url = self.database_url.strip()
        if not url:
            return f"sqlite:///{(self.data_dir / 'sphura.db').as_posix()}"
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def google_login_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def session_cookie_secure(self) -> bool:
        """SameSite=None cookies are dropped by browsers unless they are Secure."""
        return self.cookie_secure or self.cookie_samesite == "none"


def _ensure_jwt_secret(s: Settings) -> None:
    if s.jwt_secret:
        if s.environment == "production" and len(s.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters in production")
        return
    if s.environment == "production":
        raise RuntimeError("JWT_SECRET must be set in production")
    path = s.data_dir / ".jwt_secret"
    if path.exists():
        s.jwt_secret = path.read_text(encoding="utf-8").strip()
    else:
        s.jwt_secret = secrets.token_urlsafe(48)
        path.write_text(s.jwt_secret, encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    _ensure_jwt_secret(s)
    return s


settings = get_settings()
