"""GET /models: every known model with availability and the reason when unavailable.

Local Ollama models get the finance-build labels and the default follows the preference
sphura-fin → Groq → Gemini → qwen3.5 → nemotron → mock (app.llm.catalog.decorate).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.models import User
from app.llm.catalog import decorate
from app.llm.registry import list_models

router = APIRouter(tags=["models"])


@router.get("/models")
def models(_user: User = Depends(get_current_user)) -> list[dict]:
    return [m.dump() for m in decorate(list_models())]
