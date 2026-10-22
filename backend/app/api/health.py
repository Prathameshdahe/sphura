"""Public health check: cheap provider / search / vector-store status."""
from __future__ import annotations

import importlib.util

from fastapi import APIRouter

from app.core.config import settings
from app.llm.registry import provider_status
from app.schemas import Health, SearchHealth

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return Health(
        ok=True,
        version=settings.version,
        providers=provider_status(),
        search=SearchHealth(tavily=bool(settings.tavily_api_key),
                            duckduckgo=importlib.util.find_spec("ddgs") is not None),
        vector_store="qdrant" if settings.qdrant_url else "qdrant-local",
        embeddings=settings.embedding_model,
    ).dump()
