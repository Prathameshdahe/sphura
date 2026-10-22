"""/api/voice: 503 without providers (the client falls back to Web Speech / speechSynthesis), shapes with fakes."""
from __future__ import annotations

from app.features.voice import service


def test_voice_endpoints_503_without_keys(client, user):
    h = user["headers"]
    r = client.post("/api/voice/transcribe", files={"audio": ("clip.webm", b"\x1aE\xdf\xa3", "audio/webm")}, headers=h)
    assert r.status_code == 503 and r.json() == {"detail": "No speech-to-text available"}
    r = client.post("/api/voice/speak", json={"text": "What is a SIP?"}, headers=h)
    assert r.status_code == 503 and r.json() == {"detail": "No text-to-speech available"}
    assert client.post("/api/voice/speak", json={"text": "hi"}).status_code == 401
    assert not service.stt_available() and not service.tts_available()


def test_transcribe_with_a_fake_provider(client, user, monkeypatch):
    seen = {}

    async def fake_transcribe(data, filename, mime_type, language=None):
        seen.update(size=len(data), filename=filename, mime=mime_type, language=language)
        return {"text": "EMI for 25 lakh home loan", "language": "en", "provider": "groq"}

    monkeypatch.setattr(service, "stt_available", lambda: True)
    monkeypatch.setattr(service, "transcribe", fake_transcribe)
    h = user["headers"]
    r = client.post("/api/voice/transcribe", files={"audio": ("clip.webm", b"abc", "audio/webm;codecs=opus")},
                    data={"language": "en"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "EMI for 25 lakh home loan", "language": "en", "provider": "groq"}
    assert seen == {"size": 3, "filename": "clip.webm", "mime": "audio/webm", "language": "en"}
    r = client.post("/api/voice/transcribe", files={"audio": ("x.txt", b"abc", "text/plain")}, headers=h)
    assert r.status_code == 415

    async def too_long(*args, **kwargs):
        raise service.VoiceError("Transcription took too long; try a shorter clip")

    monkeypatch.setattr(service, "transcribe", too_long)
    r = client.post("/api/voice/transcribe", files={"audio": ("clip.wav", b"abc", "audio/wav")}, headers=h)
    assert r.status_code == 502 and r.json()["detail"].startswith("Transcription took too long")


def test_speak_with_a_fake_provider(client, user, monkeypatch):
    async def fake_speak(text, voice=None):
        return service.pcm_to_wav(b"\x00\x00" * 2400)

    monkeypatch.setattr(service, "tts_available", lambda: True)
    monkeypatch.setattr(service, "speak", fake_speak)
    r = client.post("/api/voice/speak", json={"text": "Your EMI is 21,696 rupees"}, headers=user["headers"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/wav")
    assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WAVE" and len(r.content) == 44 + 4800
    assert service.wav_duration_s(r.content) == 0.1
    r = client.post("/api/voice/speak", json={"text": ""}, headers=user["headers"])
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    r = client.post("/api/voice/speak", json={"text": "x" * 2001}, headers=user["headers"])
    assert r.status_code == 422
