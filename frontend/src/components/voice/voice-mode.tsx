import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { Cloud, Globe, Mic, MicOff, Square, X } from "lucide-react";
import { SphuraOrb } from "@/components/ui/sphura-orb";
import { MicOpenError, openMic, type MicHandle } from "@/components/voice/mic-level";
import {
  ENGINE_LABEL,
  browserSttSupported,
  createTranscriber,
  pickEngine,
  type Engine,
  type Transcriber,
  type TranscriberError,
} from "@/components/voice/transcriber";
import { speakableText, ttsSupported } from "@/components/voice/tts";
import type { SendChatResult } from "@/lib/chat-runner";
import { clip, uid } from "@/lib/format";
import { PHASE_PROGRAM } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { ChatStream } from "@/stores/chat-store";
import { getVoiceStatus } from "@/lib/feature-api/voice";
import { useSpeech, type LiveSpeech } from "@/stores/speech";

type VoiceState = "starting" | "listening" | "transcribing" | "thinking" | "speaking" | "paused" | "error";

interface VoiceModeProps {
  open: boolean;
  onClose: () => void;
  /** Sends `text` as a normal chat message in the current conversation; null when it couldn't start. */
  onSend: (text: string) => Promise<SendChatResult | null>;
  /** Live stream of the current conversation (status label + orb program while thinking). */
  stream?: ChatStream | null;
}

const ERRORS: Record<string, string> = {
  denied: "Microphone access is blocked. Allow it from the address bar, then try again.",
  "no-mic": "No microphone was found. Plug one in and try again.",
  insecure: "Voice needs a secure page (https or localhost) to use the microphone.",
  network: "Speech recognition lost its connection. Check your internet and try again.",
  unsupported: "Neither the server nor this browser can transcribe speech here. Add a GROQ_API_KEY for Whisper, or use Chrome, Edge or Safari.",
  "server-unavailable": "Server transcription isn't configured (no GROQ_API_KEY) and this browser can't recognise speech.",
  failed: "Speech recognition stopped unexpectedly. Try again.",
};

/** Full-screen hands-free conversation: listen → transcribe → send → speak the answer → listen again. */
export function VoiceMode(props: VoiceModeProps) {
  return createPortal(<AnimatePresence>{props.open && <VoiceOverlay key="voice" {...props} />}</AnimatePresence>, document.body);
}

function VoiceOverlay({ onClose, onSend, stream }: VoiceModeProps) {
  const [state, setState] = useState<VoiceState>("starting");
  const [engine, setEngine] = useState<Engine | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("");
  const [orbSize] = useState(() => Math.round(Math.min(300, Math.max(184, window.innerWidth * 0.55))));
  const ttsEngine = useSpeech((s) => s.engine);
  const stateRef = useRef<VoiceState>("starting");
  const alive = useRef(true);
  const recRef = useRef<Transcriber | null>(null);
  const micRef = useRef<MicHandle | null>(null);
  const sendRef = useRef(onSend);
  const closeRef = useRef(onClose);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    sendRef.current = onSend;
    closeRef.current = onClose;
  });

  const level = useMotionValue(0);
  const smooth = useSpring(level, { stiffness: 260, damping: 22, mass: 0.6 });
  const scale = useTransform(smooth, [0, 1], [1, 1.32]);
  const glow = useTransform(smooth, [0, 1], [0.35, 0.95]);

  const current = useCallback(() => stateRef.current, []);
  const go = useCallback((next: VoiceState) => {
    stateRef.current = next;
    setState(next);
  }, []);

  const listen = useCallback(() => {
    if (!alive.current || !recRef.current) return;
    setHeard("");
    go("listening");
    recRef.current.listen();
  }, [go]);

  const fail = useCallback(
    (code: TranscriberError | MicOpenError["code"], detail?: string) => {
      recRef.current?.cancel();
      setError(detail && code === "failed" ? `Speech recognition failed: ${detail}` : (ERRORS[code] ?? ERRORS.failed));
      go("error");
    },
    [go],
  );

  // Which server voices work right now (no doomed /voice/speak calls when TTS is off).
  useEffect(() => {
    void getVoiceStatus(true);
  }, []);

  // The reply is spoken while it is being written: finished sentences go to the voice as they stream in.
  const liveRef = useRef<LiveSpeech | null>(null);
  const streamText = stream?.text ?? "";
  const streamId = stream?.assistantMessageId ?? null;
  useEffect(() => {
    if (state !== "thinking" || !streamText || !streamId || !ttsSupported()) return;
    if (!liveRef.current) liveRef.current = useSpeech.getState().speakLive(streamId);
    liveRef.current.feed(streamText);
  }, [state, streamText, streamId]);

  const commit = useCallback(
    async (text: string) => {
      if (!alive.current) return;
      liveRef.current = null;
      setHeard(text);
      setReply("");
      setError(null);
      go("thinking");
      const res = await sendRef.current(text);
      if (!alive.current || stateRef.current !== "thinking") return;
      if (!res) {
        setError("Sphura is still busy with the previous answer.");
        listen();
        return;
      }
      // (set by the stream effect while we awaited the answer)
      const speaking = liveRef.current as LiveSpeech | null;
      liveRef.current = null;
      if (res.status === "done" && res.text.trim()) {
        setReply(res.text);
        if (!ttsSupported()) {
          listen();
          return;
        }
        go("speaking");
        if (speaking) await speaking.finish(res.text);
        else await useSpeech.getState().speak(res.message?.id ?? `voice:${uid()}`, res.text);
        if (alive.current && current() === "speaking") listen();
        return;
      }
      if (speaking) useSpeech.getState().stop();
      if (res.status === "error") setError(res.error ?? "Something went wrong while answering.");
      listen();
    },
    [current, go, listen],
  );

  // Latest startEngine for async callbacks (mic open, the server → browser fallback).
  const startEngineRef = useRef<(next: Engine) => void>(() => undefined);

  /** Build (or rebuild, after a fallback) the transcriber for `next`, then start listening. */
  const startEngine = useCallback(
    (next: Engine) => {
      recRef.current?.close();
      setEngine(next);
      recRef.current = createTranscriber(next, micRef.current?.stream ?? null, {
        onInterim: (t) => alive.current && setHeard(t),
        onPhase: (p) => {
          if (!alive.current) return;
          if (p === "transcribing" && stateRef.current === "listening") go("transcribing");
          else if (p === "listening" && stateRef.current === "transcribing") go("listening");
        },
        onCommit: (t) => void commit(t),
        onError: (code, detail) => {
          if (!alive.current) return;
          // The server has no STT provider: hand over to the browser's recogniser and keep going.
          if (code === "server-unavailable" && next === "server" && browserSttSupported()) {
            startEngineRef.current("browser");
            return;
          }
          fail(code, detail);
        },
      });
      listen();
    },
    [commit, fail, go, listen],
  );
  useLayoutEffect(() => {
    startEngineRef.current = startEngine;
  });

  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    useSpeech.getState().stop();
    openMic((v) => level.set(stateRef.current === "listening" ? v : 0))
      .then((handle) => {
        if (cancelled) {
          handle.close();
          return;
        }
        micRef.current = handle;
        const next = pickEngine(true);
        if (!next) fail("unsupported");
        else startEngineRef.current(next);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const code = e instanceof MicOpenError ? e.code : "failed";
        // Without our own stream the server engine is out; the browser recogniser opens the mic itself.
        if (code === "failed" && browserSttSupported()) startEngineRef.current("browser");
        else fail(code);
      });
    return () => {
      cancelled = true;
      alive.current = false;
      recRef.current?.close();
      recRef.current = null;
      micRef.current?.close();
      micRef.current = null;
      useSpeech.getState().stop();
    };
  }, [fail, level]);

  // Esc exits (captured first so the chat page doesn't also stop the answer); focus stays inside the dialog.
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const focusables = () =>
      [...(dialogRef.current?.querySelectorAll<HTMLElement>("button:not([disabled]), [href]") ?? [])];
    (primaryRef.current && !primaryRef.current.disabled ? primaryRef.current : focusables()[0])?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Tab") {
        const items = focusables();
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        const active = document.activeElement;
        if (!dialogRef.current?.contains(active) || (e.shiftKey ? active === first : active === last)) {
          e.preventDefault();
          (e.shiftKey ? last : first).focus();
        }
        return;
      }
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      closeRef.current();
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      prev?.focus?.();
    };
  }, []);

  const primary = () => {
    if (state === "listening" || state === "transcribing") {
      recRef.current?.cancel();
      go("paused");
    } else if (state === "speaking") {
      go("paused");
      useSpeech.getState().stop();
      listen();
    } else if (state === "thinking") {
      stream?.controller.abort();
    } else if (state === "paused" || state === "error") {
      setError(null);
      if (!micRef.current) {
        go("starting");
        openMic((v) => level.set(stateRef.current === "listening" ? v : 0))
          .then((h) => {
            if (!alive.current) return h.close();
            micRef.current = h;
            const next = pickEngine(true);
            if (!next) fail("unsupported");
            else startEngine(next);
          })
          .catch((e: unknown) => {
            const code = e instanceof MicOpenError ? e.code : "failed";
            if (code === "failed" && browserSttSupported()) startEngine("browser");
            else fail(code);
          });
        return;
      }
      if (!recRef.current) {
        const next = pickEngine(true);
        if (!next) return fail("unsupported");
        startEngine(next);
        return;
      }
      listen();
    }
  };

  const program =
    state === "listening" ? 2 : state === "speaking" ? 3 : state === "thinking" ? PHASE_PROGRAM[stream?.phase ?? "thinking"] : state === "transcribing" ? 1 : 0;
  const live = stream?.text ? clip(speakableText(stream.text).slice(-600), 260) : "";
  const answer = state === "thinking" ? live : reply ? clip(speakableText(reply), 260) : "";

  const statusText =
    state === "starting"
      ? "Starting the microphone…"
      : state === "listening"
        ? heard
          ? "Listening…"
          : "Listening — speak naturally"
        : state === "transcribing"
          ? "Transcribing what you said…"
          : state === "thinking"
            ? `${stream?.label || "Thinking"}…`
            : state === "speaking"
              ? "Speaking — tap to interrupt"
              : state === "paused"
                ? "Paused"
                : "Voice mode can't continue";

  const PrimaryIcon = state === "listening" ? MicOff : state === "speaking" || state === "thinking" || state === "transcribing" ? Square : Mic;
  const [primaryLabel, primaryShort] =
    state === "listening"
      ? ["Pause listening", "Pause"]
      : state === "transcribing"
        ? ["Cancel transcription", "Cancel"]
        : state === "speaking"
          ? ["Interrupt and talk", "Interrupt"]
          : state === "thinking"
            ? ["Stop the answer", "Stop"]
            : state === "starting"
              ? ["Starting", "Starting"]
              : ["Start talking", "Talk"];

  const engineBadge =
    state === "speaking" && ttsEngine
      ? { icon: ttsEngine === "server" ? Cloud : Globe, text: ttsEngine === "server" ? "Server voice" : "Browser voice" }
      : engine
        ? { icon: engine === "server" ? Cloud : Globe, text: ENGINE_LABEL[engine] }
        : null;

  return (
    <motion.div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Voice mode"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.22 }}
      className="fixed inset-0 z-[60] flex flex-col items-center overflow-hidden bg-background text-foreground"
    >
      <header className="pt-safe relative z-10 flex w-full items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-muted-foreground">
          <span className={cn("size-2 shrink-0 rounded-full transition-colors duration-200", state === "listening" ? "bg-primary motion-safe:animate-pulse" : "bg-muted-foreground/40")} />
          Voice mode
          {engineBadge && (
            <span className="ml-1 hidden items-center gap-1 rounded-full border bg-card px-2 py-0.5 text-[11px] font-medium text-muted-foreground sm:inline-flex">
              <engineBadge.icon className="size-3" aria-hidden /> {engineBadge.text}
            </span>
          )}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Exit voice mode"
          className="grid size-10 shrink-0 place-items-center rounded-full border bg-card text-muted-foreground transition-[color,transform] duration-150 hover:text-foreground focus-visible:outline-2 active:scale-95 motion-reduce:active:scale-100"
        >
          <X className="size-[18px]" />
        </button>
      </header>

      <div className="relative z-10 flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-8 px-5 text-center">
        <button
          type="button"
          onClick={primary}
          disabled={state === "starting"}
          aria-label={primaryLabel}
          className="relative grid place-items-center rounded-full focus-visible:outline-2 focus-visible:outline-offset-8 disabled:cursor-default"
          style={{ width: orbSize, height: orbSize }}
        >
          <motion.span
            aria-hidden
            className="absolute inset-[-8%] rounded-full blur-2xl"
            style={{
              opacity: glow,
              background: "radial-gradient(circle, color-mix(in oklch, var(--primary) 16%, transparent), transparent 70%)",
            }}
          />
          <motion.span style={{ scale }} className="relative grid place-items-center">
            <motion.span
              animate={
                state === "speaking"
                  ? { scale: [1, 1.07, 0.98, 1.05, 1] }
                  : state === "thinking" || state === "transcribing"
                    ? { scale: [1, 1.035, 1] }
                    : { scale: 1 }
              }
              transition={
                state === "speaking" || state === "thinking" || state === "transcribing"
                  ? { duration: state === "speaking" ? 1.4 : 2.2, repeat: Infinity, ease: "easeInOut" }
                  : { duration: 0.3 }
              }
              className={cn("grid place-items-center transition-opacity duration-300", (state === "paused" || state === "error") && "opacity-45")}
            >
              <SphuraOrb size={orbSize} program={program} active={state !== "error"} aria-label="Sphura voice orb" />
            </motion.span>
          </motion.span>
        </button>

        <div className="flex min-h-36 w-full flex-col items-center gap-3" aria-live="polite">
          <p className={cn("text-sm font-medium text-muted-foreground", (state === "thinking" || state === "starting" || state === "transcribing") && "shimmer-text")}>
            {statusText}
          </p>
          {error ? (
            <p role="alert" className="max-w-md rounded-xl border border-warning/35 bg-warning/10 px-4 py-2.5 text-sm text-foreground">
              {error}
            </p>
          ) : null}
          {heard && (
            <p className="max-w-xl font-brand text-xl leading-snug font-normal text-balance text-foreground sm:text-[1.65rem]">“{heard}”</p>
          )}
          {answer && !(state === "listening" && heard) && (
            <p
              className={cn(
                "line-clamp-4 max-w-xl font-serif text-[15px] leading-relaxed text-muted-foreground transition-opacity",
                state === "listening" && "opacity-60",
              )}
            >
              {answer}
            </p>
          )}
        </div>
      </div>

      <footer className="pb-safe relative z-10 flex w-full flex-col items-center gap-3 px-4 pt-2 pb-6">
        <div className="flex items-center gap-3">
          <button
            ref={primaryRef}
            type="button"
            aria-label={primaryLabel}
            onClick={primary}
            disabled={state === "starting"}
            className={cn(
              "inline-flex h-12 items-center gap-2 rounded-full px-5 text-sm font-semibold transition-[background-color,color,transform] duration-150 focus-visible:outline-2 active:scale-[0.97] disabled:opacity-60 motion-reduce:active:scale-100",
              state === "listening" || state === "transcribing"
                ? "border bg-card text-foreground hover:bg-muted"
                : "bg-primary text-primary-foreground shadow-xs hover:bg-[color-mix(in_oklch,var(--primary),black_8%)]",
            )}
          >
            <PrimaryIcon className="size-4" />
            <span className="sm:hidden">{primaryShort}</span>
            <span className="hidden sm:inline">{primaryLabel}</span>
          </button>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-12 items-center gap-2 rounded-full border bg-card px-5 text-sm font-medium text-muted-foreground transition-[color,transform] duration-150 hover:text-foreground focus-visible:outline-2 active:scale-[0.97] motion-reduce:active:scale-100"
          >
            End
          </button>
        </div>
        <p className="hidden text-[11px] text-muted-foreground sm:block">
          Sends after a short pause · answers appear in this chat · <kbd className="rounded border px-1 font-mono text-[10px]">Esc</kbd> to exit
        </p>
      </footer>
    </motion.div>
  );
}
