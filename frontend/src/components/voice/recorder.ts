/**
 * Server-side speech-to-text (FINANCE_PLAN §2/§8): record the microphone with MediaRecorder (webm/opus),
 * detect the end of the utterance from the loudness meter, and POST the clip to /api/voice/transcribe.
 * A 503 (no STT provider) surfaces as "server-unavailable" so the caller can switch to the Web Speech API.
 */
import { isAbortError } from "@/lib/api";
import { VoiceUnavailable, transcribeAudio } from "@/lib/feature-api/voice";
import { meterStream } from "./mic-level";
import type { Transcriber, TranscriberHandlers } from "./transcriber";

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

export function pickRecordingMimeType(): string | null {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return null;
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) ?? null;
}

export const serverRecordingSupported = (): boolean => pickRecordingMimeType() !== null;

export interface RecorderOptions {
  /** Silence after speech that ends the utterance. */
  silenceMs?: number;
  /** Loudness (0..1) that counts as the start of speech / as still speaking. */
  startLevel?: number;
  keepLevel?: number;
  /** Hard cap per clip (the API accepts ≤ 120 s). */
  maxMs?: number;
  /** While nobody speaks, restart the recorder so the clip never carries minutes of silence. */
  idleRestartMs?: number;
  /** Clips smaller than this are treated as "no speech" and never sent. */
  minBytes?: number;
}

const DEFAULTS: Required<RecorderOptions> = {
  silenceMs: 900,
  startLevel: 0.14,
  keepLevel: 0.07,
  maxMs: 110_000,
  idleRestartMs: 9_000,
  minBytes: 2_500,
};

/** Hands-free recogniser over MediaRecorder + the server transcriber. Needs the open microphone stream. */
export function createServerRecognizer(stream: MediaStream, handlers: TranscriberHandlers, options: RecorderOptions = {}): Transcriber {
  const o = { ...DEFAULTS, ...options };
  const mime = pickRecordingMimeType();
  let active = false;
  let rec: MediaRecorder | null = null;
  let chunks: Blob[] = [];
  let stopMeter: (() => void) | null = null;
  let spoke = false;
  let startedAt = 0;
  let lastVoiceAt = 0;
  let timer: ReturnType<typeof setInterval> | undefined;
  let inflight: AbortController | null = null;
  let generation = 0;
  /** Set by commitNow: an empty result ends the session ("" commit) instead of listening on. */
  let manualStop = false;

  const stopRecorder = (): Promise<Blob | null> =>
    new Promise((resolve) => {
      const r = rec;
      rec = null;
      if (!r) return resolve(null);
      if (r.state === "inactive") return resolve(chunks.length ? new Blob(chunks, { type: r.mimeType || mime || "audio/webm" }) : null);
      r.onstop = () => resolve(chunks.length ? new Blob(chunks, { type: r.mimeType || mime || "audio/webm" }) : null);
      try {
        r.stop();
      } catch {
        resolve(null);
      }
    });

  const teardown = () => {
    clearInterval(timer);
    timer = undefined;
    stopMeter?.();
    stopMeter = null;
  };

  const startRecorder = () => {
    chunks = [];
    spoke = false;
    startedAt = Date.now();
    lastVoiceAt = 0;
    const r = new MediaRecorder(stream, mime ? { mimeType: mime, audioBitsPerSecond: 48_000 } : undefined);
    r.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };
    rec = r;
    r.start(250);
  };

  const transcribe = async (blob: Blob, gen: number) => {
    handlers.onPhase?.("transcribing");
    const controller = new AbortController();
    inflight = controller;
    try {
      const result = await transcribeAudio(blob, controller.signal);
      if (!active || gen !== generation) return;
      const text = result.text.trim();
      if (!text) {
        if (manualStop) {
          active = false;
          handlers.onCommit("");
          return;
        }
        // Whisper heard nothing usable: keep listening instead of sending an empty turn.
        begin();
        return;
      }
      active = false;
      handlers.onCommit(text);
    } catch (e) {
      if (!active || gen !== generation || isAbortError(e)) return;
      active = false;
      if (e instanceof VoiceUnavailable) handlers.onError("server-unavailable");
      else handlers.onError("failed", (e as Error)?.message);
    } finally {
      if (inflight === controller) inflight = null;
    }
  };

  const finish = async () => {
    const gen = generation;
    teardown();
    const blob = await stopRecorder();
    if (!active || gen !== generation) return;
    if (!blob || blob.size < o.minBytes) {
      begin();
      return;
    }
    void transcribe(blob, gen);
  };

  const onLevel = (level: number) => {
    if (!active || !rec) return;
    const now = Date.now();
    if (level >= o.startLevel || (spoke && level >= o.keepLevel)) {
      spoke = true;
      lastVoiceAt = now;
    }
  };

  const tick = () => {
    if (!active || !rec) return;
    const now = Date.now();
    if (spoke && now - lastVoiceAt >= o.silenceMs) {
      void finish();
    } else if (!spoke && now - startedAt >= o.idleRestartMs) {
      // Drop the silent clip and start a fresh one (keeps the eventual upload small). Detach the data
      // handler first: stop() still flushes a final chunk, which must not land in the next clip's array
      // (a cluster from another recorder session makes the webm undecodable).
      const r = rec;
      rec = null;
      r.onstop = null;
      r.ondataavailable = null;
      try {
        r.stop();
      } catch {
        /* already stopped */
      }
      startRecorder();
    } else if (now - startedAt >= o.maxMs) {
      void finish();
    }
  };

  const begin = () => {
    if (!mime) {
      active = false;
      handlers.onError("unsupported");
      return;
    }
    generation += 1;
    try {
      startRecorder();
    } catch (e) {
      active = false;
      handlers.onError("failed", (e as Error)?.message);
      return;
    }
    stopMeter = meterStream(stream, onLevel);
    timer = setInterval(tick, 120);
    handlers.onPhase?.("listening");
    handlers.onInterim("");
  };

  const cancel = () => {
    active = false;
    generation += 1;
    teardown();
    inflight?.abort();
    inflight = null;
    const r = rec;
    rec = null;
    if (r) {
      r.onstop = null;
      r.ondataavailable = null;
      try {
        r.stop();
      } catch {
        /* already stopped */
      }
    }
    chunks = [];
  };

  /** Tap-to-send: stop recording now and transcribe whatever was captured. */
  const commitNow = () => {
    if (!active || !rec) return;
    manualStop = true;
    const gen = generation;
    teardown();
    void stopRecorder().then((blob) => {
      if (!active || gen !== generation) return;
      if (!blob || blob.size < o.minBytes) {
        active = false;
        handlers.onCommit("");
        return;
      }
      void transcribe(blob, gen);
    });
  };

  return {
    engine: "server",
    listen: () => {
      cancel();
      manualStop = false;
      active = true;
      begin();
    },
    cancel,
    commitNow,
    close: cancel,
  };
}
