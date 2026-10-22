/**
 * One interface over the two speech-to-text engines (FINANCE_PLAN §2): the server transcriber
 * (MediaRecorder → POST /api/voice/transcribe, Groq Whisper) and the browser's Web Speech API.
 * Voice mode starts with the server and falls back to the browser when the server answers 503.
 */
import { serverSttLikely } from "@/lib/feature-api/voice";
import { createServerRecognizer, serverRecordingSupported } from "./recorder";
import { createRecognizer, recognitionCtor, type RecognizerError } from "./recognizer";

export type Engine = "server" | "browser";
export type TranscriberPhase = "listening" | "transcribing";
export type TranscriberError = RecognizerError | "server-unavailable";

export interface TranscriberHandlers {
  /** Live transcript of the current utterance (browser engine only; the server engine sends ""). */
  onInterim: (text: string) => void;
  /** "transcribing" while a clip is on its way to the server. */
  onPhase?: (phase: TranscriberPhase) => void;
  /** The finished utterance. Recognition stops; call listen() again for the next one. */
  onCommit: (text: string) => void;
  onError: (error: TranscriberError, detail?: string) => void;
}

export interface Transcriber {
  engine: Engine;
  listen: () => void;
  /** Stop without committing. */
  cancel: () => void;
  /** Stop now and commit what was said so far (tap-to-send); commits "" when nothing usable was heard. */
  commitNow: () => void;
  /** Release everything (leaving voice mode). */
  close: () => void;
}

export const browserSttSupported = (): boolean => !!recognitionCtor();

/** Which engine voice mode should start with, given an open microphone stream (null = none works here). */
export function pickEngine(hasStream: boolean): Engine | null {
  if (hasStream && serverSttLikely() && serverRecordingSupported()) return "server";
  if (browserSttSupported()) return "browser";
  return null;
}

export function createTranscriber(engine: Engine, stream: MediaStream | null, handlers: TranscriberHandlers): Transcriber {
  if (engine === "server" && stream) return createServerRecognizer(stream, handlers);
  const rec = createRecognizer({
    onInterim: handlers.onInterim,
    onCommit: handlers.onCommit,
    onError: handlers.onError,
  });
  return {
    engine: "browser",
    listen: () => {
      handlers.onPhase?.("listening");
      rec.listen();
    },
    cancel: rec.cancel,
    commitNow: rec.commitNow,
    close: rec.cancel,
  };
}

export const ENGINE_LABEL: Record<Engine, string> = {
  server: "Whisper · server",
  browser: "Browser speech",
};
