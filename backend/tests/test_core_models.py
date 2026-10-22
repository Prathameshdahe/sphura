from __future__ import annotations

import pytest

from app.llm import registry
from app.llm.types import LLMError


def test_models_lists_mock_and_unavailable_providers(client, user):
    assert client.get("/api/models").status_code == 401
    r = client.get("/api/models", headers=user["headers"])
    assert r.status_code == 200
    models = {m["id"]: m for m in r.json()}

    mock = models["mock:sphura-mock"]
    assert mock["available"] and mock["isDefault"] and mock["supportsTools"]
    assert sum(m["isDefault"] for m in models.values()) == 1
    assert set(mock) == {"id", "provider", "label", "description", "available", "reason", "supportsTools",
                         "supportsVision", "isDefault"}

    groq = [m for m in models.values() if m["provider"] == "groq"]
    gemini = [m for m in models.values() if m["provider"] == "gemini"]
    assert groq and gemini
    assert all(not m["available"] and m["reason"] == "Add GROQ_API_KEY to .env" for m in groq)
    assert all(not m["available"] and m["reason"] == "Add GEMINI_API_KEY to .env" for m in gemini)
    ollama = [m for m in models.values() if m["provider"] == "ollama"]
    assert len(ollama) == 1 and not ollama[0]["available"] and ollama[0]["reason"].startswith("Start")
    assert not [m for m in models.values() if m["provider"] == "lmstudio"]  # an unused LM Studio isn't listed


def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    h = r.json()
    assert h["ok"] is True and h["version"]
    assert h["providers"] == {"gemini": False, "groq": False, "nvidia": False, "ollama": False, "lmstudio": False}
    assert h["search"] == {"tavily": False, "duckduckgo": True}
    assert h["vectorStore"] == "qdrant-local" and h["embeddings"]


def test_resolve_model_rules():
    assert registry.resolve_model(None).id == "mock:sphura-mock"
    m = registry.resolve_model("ollama:qwen2.5:7b")  # split on the first colon only
    assert (m.provider, m.name) == ("ollama", "qwen2.5:7b")
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        registry.resolve_model("gemini:gemini-3.8-flash")
    with pytest.raises(LLMError):
        registry.resolve_model("openai:gpt-5")


def test_resolve_default_prefers_groq_then_gemini(monkeypatch):
    monkeypatch.setattr(registry.settings, "default_model", "")
    monkeypatch.setattr(registry.settings, "gemini_api_key", "g-key")
    assert registry.resolve_model(None).provider == "gemini"
    monkeypatch.setattr(registry.settings, "groq_api_key", "q-key")
    assert registry.resolve_model(None).id == "groq:openai/gpt-oss-120b"
    monkeypatch.setattr(registry.settings, "default_model", "gemini:gemini-3.5-flash-lite")
    assert registry.resolve_model(None).id == "gemini:gemini-3.5-flash-lite"
    assert registry.fallback_models("groq:openai/gpt-oss-120b", "rate_limit")[0].startswith("groq:")
    assert registry.fallback_models("groq:openai/gpt-oss-120b", "auth")[0].startswith("gemini:")
