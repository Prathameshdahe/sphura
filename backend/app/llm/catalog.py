"""Curated cloud models (ids verified against the Gemini and Groq model pages, Oct 2026) and the labels /
default preference of the local Ollama models the finance assistant ships with.

Groq retired the Llama 3.x models for free/developer-tier keys on 2026-08-16, so the Groq list
is GPT-OSS + Qwen (all tool-calling capable).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.llm.local import pretty_label
from app.schemas import ModelInfo


@dataclass(frozen=True)
class CatalogModel:
    provider: str
    name: str
    label: str
    description: str
    supports_tools: bool = True
    supports_vision: bool = False
    reasoning: bool = False  # accepts reasoning_effort


CLOUD_MODELS: list[CatalogModel] = [
    CatalogModel("groq", "openai/gpt-oss-120b", "GPT-OSS 120B", "Groq · strong reasoning, very fast", reasoning=True),
    CatalogModel("groq", "openai/gpt-oss-20b", "GPT-OSS 20B", "Groq · ultra fast", reasoning=True),
    CatalogModel("groq", "qwen/qwen3.8-27b", "Qwen 3.8 27B", "Groq · multilingual (preview)"),
    # NVIDIA API catalog: Nemotron 3 Super is NVIDIA's agentic / tool-calling flagship (120B MoE, 12B active)
    CatalogModel("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b", "Nemotron 3.5 Super VL",
                 "NVIDIA · strong reasoning, reads images", supports_vision=True, reasoning=True),
    CatalogModel("nvidia", "nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super", "NVIDIA · strong reasoning, tools",
                 reasoning=True),
    CatalogModel("nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b", "Nemotron 3.5 Lightning", "NVIDIA · fastest",
                 reasoning=True),
    CatalogModel("nvidia", "deepseek-ai/deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "NVIDIA · DeepSeek, fast, reads images",
                 supports_vision=True),
    # Flash-Lite first: it is the one a fail-over tries first, and 3.8 Flash is often at capacity (503 / 504)
    CatalogModel("gemini", "gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "Google · fastest, lightweight",
                 supports_vision=True),
    CatalogModel("gemini", "gemini-3.8-flash", "Gemini 3.8 Flash", "Google · fast and smart",
                 supports_vision=True, reasoning=True),
    CatalogModel("gemini", "gemini-3.1-pro-preview", "Gemini 3.1 Pro", "Google · most capable (preview)",
                 supports_vision=True, reasoning=True),
]

PROVIDER_LABELS = {
    "gemini": "Gemini",
    "groq": "Groq",
    "nvidia": "NVIDIA",
    "ensemble": "Sphura Ensemble",
    "ollama": "Ollama",
    "lmstudio": "LM Studio",
    "mock": "Mock",
}

KEY_ENV = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "nvidia": "NVIDIA_API_KEY"}

# Tokens of prompt we allow per request. Groq's free tier caps a model at ~8K tokens/minute and
# local servers often run a 4K context, so their budgets are deliberately small.
PROMPT_BUDGET = {"gemini": 40_000, "groq": 3_800, "nvidia": 12_000, "ollama": 3_500, "lmstudio": 3_500, "mock": 12_000}

# Local (Ollama) models of the finance build: picker labels and the default-model preference order
# groq → gemini → qwen3.5 → nemotron → sphura-fin → (other local) → mock. The fine-tuned 1.7B model is not the
# default: its Modelfile has no tool template, so it cannot call the calculators and guesses numbers instead.
LOCAL_LABELS = {
    "qwen3.5:4b": ("Qwen 3.5 4B (local)", "Ollama · local, tools + thinking"),
    "nemotron-3-nano:4b": ("NVIDIA Nemotron 3 Nano 4B (local)", "Ollama · local, NVIDIA open model"),
}
FINETUNED_PREFIX = "sphura-fin"
FINETUNED_LABEL = ("Sphura Fin 1.7B (fine-tuned)", "Ollama · Qwen3-1.7B + our finance QLoRA, no tools")
LOCAL_PREFERENCE = ("qwen3.5", "nemotron", FINETUNED_PREFIX)
DEFAULT_PROVIDER_ORDER = ("ensemble", "groq", "nvidia", "gemini", "ollama", "lmstudio", "mock")
ENSEMBLE_ID = "ensemble:sphura"


def find_cloud_model(provider: str, name: str) -> CatalogModel | None:
    return next((m for m in CLOUD_MODELS if m.provider == provider and m.name == name), None)


def local_label(name: str) -> tuple[str, str]:
    """(label, description) for an Ollama model name."""
    base = name.split("/")[-1]
    if base.startswith(FINETUNED_PREFIX):
        return FINETUNED_LABEL
    exact = LOCAL_LABELS.get(base) or LOCAL_LABELS.get(base.replace(":latest", ""))
    if exact:
        return exact
    return f"{pretty_label(name)} (local)", "Ollama · local"


def local_rank(name: str) -> int:
    """Position in LOCAL_PREFERENCE (lower is better); unknown models come after the known ones."""
    base = name.split("/")[-1].lower()
    for i, prefix in enumerate(LOCAL_PREFERENCE):
        if base.startswith(prefix):
            return i
    return len(LOCAL_PREFERENCE)


def preferred_local(names: list[str]) -> str | None:
    """The local model the warm-up keeps loaded: the first by LOCAL_PREFERENCE among those installed."""
    ranked = sorted(names, key=lambda n: (local_rank(n), n))
    return ranked[0] if ranked else None


def default_model_id(models: list[ModelInfo]) -> str | None:
    """DEFAULT_MODEL when available, else groq → gemini → qwen3.5 → nemotron → sphura-fin → … → mock."""
    available = [m for m in models if m.available]
    wanted = settings.default_model.strip()
    if wanted and any(m.id == wanted for m in available):
        return wanted
    local = sorted((m for m in available if m.provider == "ollama"), key=lambda m: (local_rank(m.id.split(":", 1)[1]), m.id))
    for provider in DEFAULT_PROVIDER_ORDER:
        if provider == "ollama":
            if local:
                return local[0].id
            continue
        first = next((m for m in available if m.provider == provider), None)
        if first:
            return first.id
    return None


def decorate(models: list[ModelInfo]) -> list[ModelInfo]:
    """Apply the finance-build labels to local models and recompute `isDefault` with the preference order."""
    for m in models:
        if m.provider == "ollama" and m.available:
            m.label, m.description = local_label(m.id.split(":", 1)[1])
    default = default_model_id(models)
    for m in models:
        m.is_default = m.id == default
    return models
