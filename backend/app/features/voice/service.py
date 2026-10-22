"""STT via Groq `whisper-large-v3-turbo` (openai SDK, Groq base URL); TTS via Groq Orpheus, then Gemini.

TTS latency: Orpheus answers a sentence in well under a second, Gemini in about 3 s, so Orpheus is tried first
for short text (the client sends the answer sentence by sentence and plays one while the next is made). A
provider that refuses (terms not accepted, key, quota) is skipped for a while instead of costing every sentence
a failed round trip, and recent clips are cached. Both directions raise `VoiceUnavailable` when no provider can
serve, so the API answers 503 and the browser falls back to Web Speech / speechSynthesis.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import struct
import time
from collections import OrderedDict
from typing import Any

from app.core.config import settings

log = logging.getLogger("sphura.voice")

STT_MODEL = "whisper-large-v3-turbo"
TTS_MODEL = "gemini-3.8-flash-lite-tts"
DEFAULT_VOICE = "Kore"
ORPHEUS_MODEL = "canopylabs/orpheus-v1-english"
ORPHEUS_VOICE = "diana"
ORPHEUS_VOICES = ("autumn", "diana", "hannah", "austin", "daniel", "troy")
ORPHEUS_MAX_CHARS = 200   # longer text goes to Gemini in one request
ORPHEUS_TIMEOUT_S = 15.0
SKIP_AFTER_FAILURE_S = 600.0
MAX_SKIP_S = 12 * 3600.0  # a daily quota says "retry in 9h": believe it, up to half a day
_RETRY_IN = re.compile(r"retry(?:delay'?:?\s*'?| in )(\d+(?:\.\d+)?)(h|m|s)", re.I)
CACHE_ITEMS = 64
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_TEXT_CHARS = 2000
STT_TIMEOUT_S = 60.0
TTS_TIMEOUT_S = 60.0
PCM_RATE = 24_000  # Gemini TTS returns 24 kHz 16-bit mono PCM
AUDIO_TYPES = ("audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/mp4",
               "audio/m4a", "audio/x-m4a", "audio/flac", "audio/aac", "application/octet-stream", "video/webm")


class VoiceUnavailable(Exception):
    """No provider for this direction (missing key or SDK); the client should use the browser engine."""


class VoiceError(Exception):
    """The provider answered with an error (short, user-facing message)."""


def stt_available() -> bool:
    return bool(settings.groq_api_key)


_skip_until: dict[str, float] = {}
_cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()


def _skipped(provider: str) -> bool:
    return _skip_until.get(provider, 0.0) > time.monotonic()


def _skip(provider: str, reason: str, seconds: float = SKIP_AFTER_FAILURE_S) -> None:
    seconds = min(max(seconds, SKIP_AFTER_FAILURE_S), MAX_SKIP_S)
    log.info("TTS: skipping %s for %.0f s (%s)", provider, seconds, reason)
    _skip_until[provider] = time.monotonic() + seconds


def _retry_after(message: str) -> float:
    """Seconds from "Please retry in 9h23m9s" / "retryDelay': '33789s'", else 0."""
    m = _RETRY_IN.search(message)
    if not m:
        return 0.0
    return float(m.group(1)) * {"h": 3600, "m": 60, "s": 1}[m.group(2).lower()]


def tts_provider() -> str | None:
    """The provider the next sentence would use (None: the browser should speak)."""
    return "orpheus" if _orpheus_ready() else "gemini" if _gemini_ready() else None


def _gemini_ready() -> bool:
    if not settings.gemini_api_key or _skipped("gemini"):
        return False
    try:
        import google.genai  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _orpheus_ready() -> bool:
    return bool(settings.groq_api_key) and not _skipped("orpheus")


def tts_available() -> bool:
    return _orpheus_ready() or _gemini_ready()


async def transcribe(data: bytes, filename: str, mime_type: str, language: str | None = None) -> dict[str, Any]:
    """{text, language, provider}. Raises VoiceUnavailable without a Groq key, VoiceError on provider errors."""
    if not stt_available():
        raise VoiceUnavailable("No speech-to-text available")
    if not data:
        raise VoiceError("The audio file is empty")
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url, max_retries=1,
                         timeout=STT_TIMEOUT_S)
    kwargs: dict[str, Any] = {"model": STT_MODEL, "file": (filename or "audio.webm", data, mime_type or "audio/webm"),
                              "response_format": "verbose_json", "temperature": 0.0}
    if language:
        kwargs["language"] = language
    try:
        result = await asyncio.wait_for(client.audio.transcriptions.create(**kwargs), STT_TIMEOUT_S + 5)
    except asyncio.TimeoutError:
        raise VoiceError("Transcription took too long; try a shorter clip") from None
    except Exception as exc:  # noqa: BLE001
        log.warning("Groq transcription failed: %s", exc)
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            raise VoiceError("Groq rejected the API key for speech-to-text") from exc
        if status == 429:
            raise VoiceError("Groq rate limit reached for speech-to-text; try again in a minute") from exc
        raise VoiceError("Speech-to-text failed; please try again") from exc
    text = (getattr(result, "text", None) or "").strip()
    lang = getattr(result, "language", None)
    return {"text": text, "language": str(lang) if lang else None, "provider": "groq"}


def pcm_to_wav(pcm: bytes, rate: int = PCM_RATE, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw little-endian PCM in a RIFF/WAVE header."""
    byte_rate = rate * channels * sample_width
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, channels, rate,
                         byte_rate, channels * sample_width, sample_width * 8, b"data", len(pcm))
    return header + pcm


async def speak(text: str, voice: str | None = None) -> bytes:
    """WAV bytes for `text` (<= MAX_TEXT_CHARS): Orpheus for short text, else (or when it fails) Gemini."""
    clean = " ".join((text or "").split())[:MAX_TEXT_CHARS]
    if not clean:
        raise VoiceError("Nothing to say")
    key = (clean, voice or "")
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    wav: bytes | None = None
    error: VoiceError | None = None
    if _orpheus_ready() and len(clean) <= ORPHEUS_MAX_CHARS:
        try:
            wav = await _speak_orpheus(clean, voice)
        except VoiceError as exc:
            error = exc
    if wav is None and _gemini_ready():
        try:
            wav = await _speak_gemini(clean, voice)
        except VoiceError as exc:
            error = exc
    if wav is None:
        if not tts_available():  # every provider refused: the browser voice is the answer, not an error
            raise VoiceUnavailable("No text-to-speech available")
        raise error or VoiceUnavailable("No text-to-speech available")
    _cache[key] = wav
    while len(_cache) > CACHE_ITEMS:
        _cache.popitem(last=False)
    return wav


async def _speak_orpheus(clean: str, voice: str | None) -> bytes:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url, max_retries=0,
                         timeout=ORPHEUS_TIMEOUT_S)
    name = voice if voice in ORPHEUS_VOICES else ORPHEUS_VOICE
    try:
        resp = await asyncio.wait_for(client.audio.speech.create(model=ORPHEUS_MODEL, voice=name, input=clean,
                                                                 response_format="wav"), ORPHEUS_TIMEOUT_S + 2)
    except asyncio.TimeoutError:
        raise VoiceError("Text-to-speech took too long") from None
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status_code", None)
        message = str(exc).lower()
        if status in (401, 403, 404) or "terms" in message or "decommissioned" in message:
            _skip("orpheus", "terms not accepted" if "terms" in message else f"HTTP {status}")
        elif status == 429:
            _skip("orpheus", "rate limit")
        else:
            log.warning("Groq Orpheus TTS failed: %s", exc)
        raise VoiceError("Text-to-speech failed; please try again") from exc
    data = resp.read() if hasattr(resp, "read") else bytes(resp.content)
    if not data:
        raise VoiceError("Text-to-speech returned no audio")
    return data


async def _speak_gemini(clean: str, voice: str | None) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=voice if voice and voice not in ORPHEUS_VOICES else DEFAULT_VOICE))),
    )
    try:
        resp = await asyncio.wait_for(
            client.aio.models.generate_content(model=TTS_MODEL, contents=clean, config=config),
            TTS_TIMEOUT_S)
    except asyncio.TimeoutError:
        raise VoiceError("Text-to-speech took too long") from None
    except Exception as exc:  # noqa: BLE001
        log.warning("Gemini TTS failed: %s", exc)
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if code in (401, 403):
            _skip("gemini", f"HTTP {code}")
            raise VoiceError("Gemini rejected the API key for text-to-speech") from exc
        if code == 429:
            _skip("gemini", "quota", _retry_after(str(exc)))
            raise VoiceError("Gemini rate limit reached for text-to-speech; try again in a minute") from exc
        raise VoiceError("Text-to-speech failed; please try again") from exc
    pcm = b""
    for candidate in getattr(resp, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            blob = getattr(part, "inline_data", None)
            if blob is not None and getattr(blob, "data", None):
                pcm += blob.data
    if not pcm:
        raise VoiceError("Text-to-speech returned no audio")
    if pcm[:4] == b"RIFF":
        return pcm
    return pcm_to_wav(pcm)


def wav_duration_s(wav: bytes) -> float:
    """Approximate duration of a 16-bit mono 24 kHz WAV (for logging)."""
    return max(0.0, (len(wav) - 44) / (PCM_RATE * 2))


__all__ = ["transcribe", "speak", "stt_available", "tts_available", "VoiceUnavailable", "VoiceError",
           "MAX_AUDIO_BYTES", "MAX_TEXT_CHARS", "AUDIO_TYPES", "pcm_to_wav", "io"]
