// Voice API (FINANCE_PLAN §8): server-side STT/TTS with a remembered 503 so the browser fallbacks take over at once.
import { ApiError, request, requestBlob } from "@/lib/api";
import type { TranscribeResult } from "@/lib/feature-types";

/** After a 503 the server has no STT/TTS provider; don't retry it for a while (the key may be added later). */
const UNAVAILABLE_FOR_MS = 5 * 60_000;
const unavailableUntil = { transcribe: 0, speak: 0 };

export const isUnavailableError = (e: unknown) => e instanceof ApiError && e.status === 503;

export const serverSttLikely = () => Date.now() >= unavailableUntil.transcribe;
export const serverTtsLikely = () => Date.now() >= unavailableUntil.speak;

export class VoiceUnavailable extends Error {
  constructor(what: "transcribe" | "speak") {
    super(`Server ${what === "transcribe" ? "transcription" : "speech"} is not configured`);
    this.name = "VoiceUnavailable";
  }
}

function mark(what: "transcribe" | "speak") {
  unavailableUntil[what] = Date.now() + UNAVAILABLE_FOR_MS;
}

/** POST /api/voice/transcribe (multipart `audio`, webm/opus or wav, ≤ 25 MB / ≤ 120 s). Throws VoiceUnavailable on 503. */
export async function transcribeAudio(audio: Blob, signal?: AbortSignal): Promise<TranscribeResult> {
  if (!serverSttLikely()) throw new VoiceUnavailable("transcribe");
  const form = new FormData();
  const ext = audio.type.includes("wav") ? "wav" : audio.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audio, `utterance.${ext}`);
  try {
    return await request<TranscribeResult>("/voice/transcribe", { method: "POST", form, signal });
  } catch (e) {
    if (isUnavailableError(e)) {
      mark("transcribe");
      throw new VoiceUnavailable("transcribe");
    }
    throw e;
  }
}

/** GET /api/voice/status: which server voices work right now. */
export interface VoiceStatus {
  stt: boolean;
  tts: boolean;
  ttsProvider: "orpheus" | "gemini" | null;
}

const STATUS_TTL_MS = 60_000;
let statusCache: { at: number; value: Promise<VoiceStatus> } | null = null;

/**
 * Cached voice status (refreshed at most once a minute, or when `force`). When the server has no text-to-speech
 * (tts: false) the browser voice is used straight away, without a doomed POST per sentence. A failed status call
 * counts as "unknown": the server is tried and a 503 still switches to the browser voice.
 */
export function getVoiceStatus(force = false): Promise<VoiceStatus> {
  if (!force && statusCache && Date.now() - statusCache.at < STATUS_TTL_MS) return statusCache.value;
  const value = request<Partial<VoiceStatus>>("/voice/status")
    .then((s) => {
      const status: VoiceStatus = { stt: s.stt !== false, tts: s.tts !== false, ttsProvider: s.ttsProvider ?? null };
      if (!status.tts) mark("speak");
      else unavailableUntil.speak = 0;
      if (!status.stt) mark("transcribe");
      else unavailableUntil.transcribe = 0;
      return status;
    })
    .catch((): VoiceStatus => ({ stt: true, tts: serverTtsLikely(), ttsProvider: null }));
  statusCache = { at: Date.now(), value };
  return value;
}

export const SPEAK_MAX_CHARS = 2000;

/** POST /api/voice/speak → audio/wav bytes. Throws VoiceUnavailable on 503. */
export async function speakText(text: string, voice?: string, signal?: AbortSignal): Promise<Blob> {
  if (!serverTtsLikely()) throw new VoiceUnavailable("speak");
  try {
    return await requestBlob("/voice/speak", {
      method: "POST",
      body: { text: text.slice(0, SPEAK_MAX_CHARS), ...(voice ? { voice } : {}) },
      accept: "audio/wav, audio/*",
      signal,
    });
  } catch (e) {
    if (isUnavailableError(e)) {
      mark("speak");
      throw new VoiceUnavailable("speak");
    }
    throw e;
  }
}
