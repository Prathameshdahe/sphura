"""POST /voice/transcribe (Groq Whisper), POST /voice/speak (Groq Orpheus → Gemini TTS), GET /voice/status.
503 when no provider can serve (missing key, terms not accepted, quota used up): the browser voice takes over."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import Field

from app.api.deps import get_current_user
from app.db.models import User
from app.features.voice import service
from app.schemas import CamelModel

log = logging.getLogger("sphura.api.voice")
router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakIn(CamelModel):
    text: str = Field(min_length=1, max_length=service.MAX_TEXT_CHARS)
    voice: str | None = Field(default=None, max_length=40)


class TranscriptOut(CamelModel):
    text: str
    language: str | None = None
    provider: str


class VoiceStatusOut(CamelModel):
    stt: bool
    tts: bool
    tts_provider: str | None = None


@router.get("/status")
async def voice_status(_user: User = Depends(get_current_user)) -> dict:
    """Which directions the server can do right now; when `tts` is false the client speaks with the browser voice
    without trying the server for every sentence."""
    return VoiceStatusOut(stt=service.stt_available(), tts=service.tts_available(),
                          tts_provider=service.tts_provider()).dump()


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str | None = Form(default=None),
                     _user: User = Depends(get_current_user)) -> dict:
    if not service.stt_available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No speech-to-text available")
    mime = (audio.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if not mime.startswith("audio/") and mime not in service.AUDIO_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Send an audio file (webm/opus, wav, mp3, m4a)")
    data = await audio.read(service.MAX_AUDIO_BYTES + 1)
    if len(data) > service.MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio must be 25 MB or smaller")
    try:
        result = await service.transcribe(data, audio.filename or "audio.webm", mime,
                                          (language or "").strip()[:8] or None)
    except service.VoiceUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    except service.VoiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    return TranscriptOut.model_validate(result).dump()


@router.post("/speak")
async def speak(body: SpeakIn, _user: User = Depends(get_current_user)) -> Response:
    if not service.tts_available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No text-to-speech available")
    try:
        wav = await service.speak(body.text, body.voice)
    except service.VoiceUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    except service.VoiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})
