import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { MicOpenError, openMic, type MicHandle } from "./mic-level";
import { serverRecordingSupported } from "./recorder";
import { browserSttSupported, createTranscriber, pickEngine, type Transcriber, type TranscriberHandlers } from "./transcriber";
import { getVoiceStatus } from "@/lib/feature-api/voice";
import { useSpeech } from "@/stores/speech";

export type VoiceInputState = "idle" | "recording" | "transcribing";

/** Whether this browser can do in-chat voice input at all (mic + server recording or Web Speech). */
export const voiceInputSupported = (): boolean =>
  typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && (serverRecordingSupported() || browserSttSupported());

const MIC_ERRORS: Record<string, string> = {
  denied: "Microphone access is blocked. Allow it in your browser to talk to Sphura.",
  "no-mic": "No microphone was found.",
  insecure: "Voice needs a secure page (https or localhost).",
  network: "Voice input needs a network connection.",
  unsupported: "Voice input isn't supported in this browser.",
  failed: "Voice input stopped unexpectedly.",
};

/**
 * Tap-to-talk for the chat composer: open the mic → record (server Whisper first, browser speech as fallback) →
 * stop on silence or on a second tap → hand the transcript to `onText`. Exposes a live level and a seconds counter.
 */
export function useVoiceInput(onText: (text: string) => void) {
  const [state, setState] = useState<VoiceInputState>("idle");
  const [level, setLevel] = useState(0);
  const [seconds, setSeconds] = useState(0);
  const mic = useRef<MicHandle | null>(null);
  const transcriber = useRef<Transcriber | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const onTextRef = useRef(onText);
  useEffect(() => {
    onTextRef.current = onText;
  });

  const release = useCallback(() => {
    transcriber.current?.close();
    transcriber.current = null;
    clearInterval(timer.current);
    timer.current = undefined;
    mic.current?.close();
    mic.current = null;
    setLevel(0);
  }, []);

  useEffect(() => release, [release]);

  const start = useCallback(async () => {
    if (transcriber.current || mic.current) return;
    useSpeech.getState().stop();
    setState("recording");
    setSeconds(0);
    let handle: MicHandle;
    try {
      // Level metering lives on the same stream the recorder uses.
      let last = 0;
      handle = await openMic((v) => {
        const now = performance.now();
        if (now - last > 60) {
          last = now;
          setLevel(v);
        }
      });
    } catch (e) {
      setState("idle");
      toast.error(MIC_ERRORS[e instanceof MicOpenError ? e.code : "failed"]);
      return;
    }
    mic.current = handle;
    await getVoiceStatus(); // no server speech-to-text → the browser recogniser, without a failed upload first
    if (mic.current !== handle) return;
    const engine = pickEngine(true);
    if (!engine) {
      release();
      setState("idle");
      toast.error(MIC_ERRORS.unsupported);
      return;
    }

    const handlers: TranscriberHandlers = {
      onInterim: () => undefined,
      onPhase: (phase) => setState(phase === "transcribing" ? "transcribing" : "recording"),
      onCommit: (text) => {
        release();
        setState("idle");
        const said = text.trim();
        if (!said) {
          toast("Didn't catch that. Tap the mic and try again.");
          return;
        }
        onTextRef.current(said);
      },
      onError: (error) => {
        // No server speech-to-text configured: carry on with the browser's recogniser.
        if (error === "server-unavailable" && browserSttSupported() && mic.current) {
          transcriber.current?.close();
          transcriber.current = createTranscriber("browser", null, handlers);
          transcriber.current.listen();
          return;
        }
        release();
        setState("idle");
        toast.error(MIC_ERRORS[error] ?? MIC_ERRORS.failed);
      },
    };
    const t = createTranscriber(engine, handle.stream, handlers);
    transcriber.current = t;
    t.listen();
    const began = Date.now();
    timer.current = setInterval(() => setSeconds(Math.floor((Date.now() - began) / 1000)), 250);
  }, [release]);

  /** Second tap: stop and send what was said. */
  const stop = useCallback(() => {
    if (!transcriber.current) return;
    clearInterval(timer.current);
    setState("transcribing");
    transcriber.current.commitNow();
  }, []);

  const cancel = useCallback(() => {
    release();
    setState("idle");
  }, [release]);

  const toggle = useCallback(() => {
    if (state === "idle") void start();
    else if (state === "recording") stop();
  }, [start, state, stop]);

  return { state, level, seconds, toggle, cancel };
}
