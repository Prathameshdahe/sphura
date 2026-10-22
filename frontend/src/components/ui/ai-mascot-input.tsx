import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { Cpu, LoaderCircle } from "lucide-react";
import { ModelPicker, type ComposerModel } from "@/components/chat/model-picker";
import {
  PiArrowUpBold,
  PiFileTextBold,
  PiGlobeBold,
  PiImageBold,
  PiMicrophoneBold,
  PiMicrophoneFill,
  PiPaperclipBold,
  PiStopFill,
  PiUploadSimpleBold,
  PiWarningCircleBold,
  PiXBold,
} from "react-icons/pi";
import { cn } from "@/lib/utils";
import type { Effort } from "@/lib/types";

export type { Effort, ComposerModel };

/* ───────────────────────────── contract ───────────────────────────── */

export interface ComposerAttachment {
  id: string;
  name: string;
  isImage: boolean;
  status: "uploading" | "processing" | "ready" | "error";
  error?: string | null;
}

export interface ComposerSubmit {
  prompt: string;
  modelId: string;
  effort: Effort;
  webSearch: boolean;
}

/** In-chat voice: record → server transcription → send (the composer only shows state and the button). */
export interface ComposerVoice {
  state: "idle" | "recording" | "transcribing";
  /** 0..1 microphone loudness while recording. */
  level: number;
  /** Seconds recorded so far. */
  seconds: number;
  /** Tap: start recording, or stop and send what was said. */
  onToggle: () => void;
  /** Discard the recording. */
  onCancel: () => void;
}

export interface AiMascotInputProps {
  onSubmit: (data: ComposerSubmit) => void;
  onCancel?: () => void;
  isProcessing?: boolean;
  models: ComposerModel[];
  modelId?: string;
  onModelChange?: (id: string) => void;
  effort?: Effort;
  onEffortChange?: (e: Effort) => void;
  webSearch?: boolean;
  onWebSearchChange?: (on: boolean) => void;
  attachments?: ComposerAttachment[];
  onAttach?: (files: File[]) => void;
  onRemoveAttachment?: (id: string) => void;
  value?: string;
  onChange?: (v: string) => void;
  disabled?: boolean;
  placeholder?: string;
  showWelcome?: boolean;
  title?: string;
  subtitle?: string;
  showMascot?: boolean;
  enableVoice?: boolean;
  /** Server voice input; when set, the mic records and sends instead of dictating into the box. */
  voice?: ComposerVoice;
  enableWebSearch?: boolean;
  enableAttachments?: boolean;
  autoFocus?: boolean;
  className?: string;
  containerClassName?: string;
}

export const ACCEPTED_FILES = ".pdf,.docx,.txt,.md,.csv,.xlsx,.xls,.json,.html,.png,.jpg,.jpeg,.webp";

/* ───────────────────────────── provider icons ───────────────────────────── */
export const GeminiIcon = ({ size = 16, className = "" }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
    <path d="M11.04 19.32Q12 21.51 12 24q0-2.49.93-4.68.96-2.19 2.58-3.81t3.81-2.55Q21.51 12 24 12q-2.49 0-4.68-.93a12.3 12.3 0 0 1-3.81-2.58 12.3 12.3 0 0 1-2.58-3.81Q12 2.49 12 0q0 2.49-.96 4.68-.93 2.19-2.55 3.81a12.3 12.3 0 0 1-3.81 2.58Q2.49 12 0 12q2.49 0 4.68.96 2.19.93 3.81 2.55t2.55 3.81" />
  </svg>
);

/** Original glyph for Groq: a geometric "G" with speed lines (fast inference). */
export const GroqIcon = ({ size = 16, className = "" }: { size?: number; className?: string }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2.4}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    <path d="M19 8.2A7.5 7.5 0 1 0 20 13h-6.5" />
    <path d="M2 9.5h2.2M1.5 14.5h2.2" opacity={0.55} />
  </svg>
);

/** Local runtimes (Ollama / LM Studio / Mock). */
export const LocalModelIcon = ({ size = 16, className = "" }: { size?: number; className?: string }) => (
  <Cpu size={size} className={className} strokeWidth={2} aria-hidden="true" />
);

/* ───────────────────────────── speech (Web Speech API) ───────────────────────────── */
interface ISpeechRecognitionEvent {
  results: { length: number; [index: number]: { [index: number]: { transcript: string } } };
}
interface ISpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: ISpeechRecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}
type SpeechCtor = new () => ISpeechRecognition;

const getSpeechCtor = (): SpeechCtor | null => {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: SpeechCtor; webkitSpeechRecognition?: SpeechCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};

const SPEECH_ERRORS: Record<string, string> = {
  "not-allowed": "Microphone access is blocked — allow it in your browser to dictate.",
  "service-not-allowed": "Voice input is disabled in this browser.",
  "audio-capture": "No microphone was found.",
  network: "Voice input needs a network connection to the browser's speech service.",
};

/* ───────────────────────────── mascot ───────────────────────────── */
export type RobotEmotion = "reading" | "thinking";

export function RobotBeta({
  emotion,
  textLength = 0,
  isListening = false,
}: {
  emotion: RobotEmotion;
  textLength?: number;
  isListening?: boolean;
}) {
  const [isBlinking, setIsBlinking] = useState(false);

  useEffect(() => {
    let blink: ReturnType<typeof setTimeout> | undefined;
    const interval = setInterval(() => {
      if (emotion !== "thinking") {
        setIsBlinking(true);
        blink = setTimeout(() => setIsBlinking(false), 140);
      }
    }, 2800 + Math.random() * 2200);
    return () => {
      clearInterval(interval);
      if (blink) clearTimeout(blink);
    };
  }, [emotion]);

  const eyeOffset = Math.sin(textLength * 0.45) * 6;

  const sideEarStyle = isListening
    ? "bg-red-500 shadow-[0_0_10px_#ef4444,0_0_18px_rgba(239,68,68,0.7)] animate-pulse"
    : emotion === "thinking"
      ? "bg-amber-400 shadow-[0_0_8px_#facc15]"
      : "bg-emerald-400 shadow-[0_0_8px_#10b981]";

  return (
    <motion.div
      className="relative flex flex-col items-center justify-center select-none px-2.5 pt-2"
      aria-hidden="true"
      animate={{ y: emotion === "thinking" ? [0, -5, 0] : [0, -2, 0] }}
      transition={{ y: { duration: 2.2, repeat: Infinity, ease: "easeInOut" } }}
    >
      <div className="relative w-20 flex justify-between px-2 -mb-2 z-0">
        <div className="w-3.5 h-4 bg-zinc-300 dark:bg-zinc-700 border-2 border-black/10 dark:border-white/10 rounded-tl-xl" />
        <div className="w-3.5 h-4 bg-zinc-300 dark:bg-zinc-700 border-2 border-black/10 dark:border-white/10 rounded-tr-xl" />
      </div>

      <div className="relative flex items-center justify-center">
        <div className={`absolute -left-1.5 w-1 h-5 rounded-l-xs transition-all duration-300 ${sideEarStyle}`} />
        <div className={`absolute -right-1.5 w-1 h-5 rounded-r-xs transition-all duration-300 ${sideEarStyle}`} />

        <div className="z-10 w-22 h-15 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-black/10 dark:border-white/20 flex items-center justify-center p-1.5 shadow-[0_3px_10px_rgba(0,0,0,0.05)] dark:shadow-[0_4px_16px_rgba(0,0,0,0.4)]">
          <div className="relative w-full h-full bg-[#050505] rounded-lg flex items-center justify-center gap-3.5 overflow-hidden shadow-[inset_0_2px_5px_rgba(0,0,0,0.95)]">
            <div className="relative z-10 flex items-center justify-center gap-3.5">
              <EyeLED emotion={emotion} isBlinking={isBlinking} offsetX={eyeOffset} />
              <EyeLED emotion={emotion} isBlinking={isBlinking} offsetX={eyeOffset} />
            </div>

            <div
              className="absolute inset-0 pointer-events-none z-20"
              style={{
                backgroundImage: "linear-gradient(rgba(0, 0, 0, 0) 50%, rgba(0, 0, 0, 0.72) 50%)",
                backgroundSize: "100% 4px",
              }}
            />
            <div className="absolute inset-0 pointer-events-none z-20 shadow-[inset_0_0_8px_rgba(0,0,0,0.9)]" />
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export function EyeLED({
  emotion,
  isBlinking,
  offsetX,
}: {
  emotion: RobotEmotion;
  isBlinking: boolean;
  offsetX: number;
}) {
  const isThinking = emotion === "thinking";

  if (isBlinking && !isThinking) {
    return <div className="w-2.5 h-1 rounded-xs bg-emerald-400 shadow-[0_0_6px_#10b981]" />;
  }

  if (isThinking) {
    return (
      <motion.div
        className="w-2.5 h-3.5 rounded-xs bg-amber-300 shadow-[0_0_10px_#facc15,0_0_18px_rgba(250,204,21,0.4)]"
        animate={{ y: [-1, -3, -1] }}
        transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
      />
    );
  }

  return (
    <motion.div
      className="w-2.5 h-4.5 rounded-xs bg-emerald-400 shadow-[0_0_12px_#34d399,0_0_20px_rgba(52,211,153,0.45)]"
      animate={{ x: offsetX }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
    />
  );
}

/* ───────────────────────────── attachment chip ───────────────────────────── */
function AttachmentChip({ a, onRemove, disabled }: { a: ComposerAttachment; onRemove?: (id: string) => void; disabled?: boolean }) {
  const busy = a.status === "uploading" || a.status === "processing";
  const failed = a.status === "error";
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9, y: 4 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.16 }}
      title={failed ? (a.error ?? "Upload failed") : a.name}
      className={cn(
        "flex h-8 max-w-full items-center gap-1.5 rounded-xl pl-2.5 pr-1 text-xs font-medium",
        failed
          ? "bg-red-500/10 text-red-700 ring-1 ring-red-500/30 dark:text-red-300"
          : "bg-zinc-100 text-zinc-800 dark:bg-white/10 dark:text-zinc-200",
      )}
    >
      {busy ? (
        <LoaderCircle size={14} className="shrink-0 animate-spin text-rose-500" aria-hidden="true" />
      ) : failed ? (
        <PiWarningCircleBold size={15} className="shrink-0 text-red-500" aria-hidden="true" />
      ) : a.isImage ? (
        <PiImageBold size={15} className="shrink-0 text-cyan-500" aria-hidden="true" />
      ) : (
        <PiFileTextBold size={15} className="shrink-0 text-blue-500" aria-hidden="true" />
      )}
      <span className="min-w-0 max-w-36 truncate sm:max-w-44">{a.name}</span>
      {a.status !== "ready" && (
        <span className={cn("shrink-0 text-[10px] font-semibold uppercase tracking-wide", failed ? "text-red-600 dark:text-red-400" : "text-zinc-500 dark:text-zinc-400")}>
          {a.status === "uploading" ? "Uploading…" : a.status === "processing" ? "Processing…" : "Failed"}
        </span>
      )}
      <span className="sr-only" role="status">
        {failed ? `${a.name} failed: ${a.error ?? "upload error"}` : busy ? "" : `${a.name} ready`}
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(a.id)}
          disabled={disabled}
          aria-label={`Remove ${a.name}`}
          className="ml-0.5 grid size-6 shrink-0 place-items-center rounded-lg text-zinc-500 transition-colors hover:bg-black/5 hover:text-red-500 disabled:opacity-50 dark:hover:bg-white/10"
        >
          <PiXBold size={11} />
        </button>
      )}
    </motion.div>
  );
}

/* ───────────────────────────── composer ───────────────────────────── */
export function AiMascotInput({
  onSubmit,
  onCancel,
  isProcessing = false,
  models,
  modelId,
  onModelChange,
  effort,
  onEffortChange,
  webSearch,
  onWebSearchChange,
  attachments = [],
  onAttach,
  onRemoveAttachment,
  value,
  onChange,
  disabled = false,
  placeholder = "Ask Sphura anything…",
  showWelcome = false,
  title = "How can I help you today?",
  subtitle = "Ask, search the web, or drop in a document",
  showMascot = true,
  enableVoice = true,
  voice,
  enableWebSearch = true,
  enableAttachments = true,
  autoFocus = false,
  className,
  containerClassName,
}: AiMascotInputProps) {
  const uid = useId();
  const layoutId = `robot-mascot-${uid}`;

  /* text (optionally controlled) */
  const [innerText, setInnerText] = useState("");
  const text = value ?? innerText;
  const textRef = useRef(text);
  const onChangeRef = useRef(onChange);
  useLayoutEffect(() => {
    textRef.current = text;
    onChangeRef.current = onChange;
  });
  const controlledText = value !== undefined;
  const setText = useCallback(
    (v: string) => {
      if (!controlledText) setInnerText(v);
      onChangeRef.current?.(v);
    },
    [controlledText],
  );

  /* model / effort / web search (controlled with internal fallback) */
  const [innerModel, setInnerModel] = useState("");
  const fallbackModel = models.find((m) => m.available)?.id ?? models[0]?.id ?? "";
  const currentModelId = modelId ?? (models.some((m) => m.id === innerModel) ? innerModel : fallbackModel);
  const currentModel = models.find((m) => m.id === currentModelId) ?? null;

  const [innerEffort, setInnerEffort] = useState<Effort>("balanced");
  const currentEffort = effort ?? innerEffort;

  const [innerWeb, setInnerWeb] = useState(false);
  const web = webSearch ?? innerWeb;

  const selectModel = (id: string) => {
    setInnerModel(id);
    onModelChange?.(id);
  };
  const selectEffort = (e: Effort) => {
    setInnerEffort(e);
    onEffortChange?.(e);
  };
  const toggleWeb = () => {
    setInnerWeb(!web);
    onWebSearchChange?.(!web);
  };

  /* inline hint (voice unsupported, uploads pending, …) */
  const [hint, setHint] = useState<string | null>(null);
  const hintTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const showHint = useCallback((msg: string) => {
    setHint(msg);
    clearTimeout(hintTimer.current);
    hintTimer.current = setTimeout(() => setHint(null), 4500);
  }, []);

  /* voice */
  const [listening, setListening] = useState(false);
  const recRef = useRef<ISpeechRecognition | null>(null);
  const listeningRef = useRef(false);
  const heardRef = useRef(false);
  const baseRef = useRef("");

  const stopListening = useCallback(() => {
    listeningRef.current = false;
    setListening(false);
    const rec = recRef.current;
    recRef.current = null;
    if (rec) {
      rec.onend = null;
      try {
        rec.stop();
      } catch {
        /* already stopped */
      }
    }
  }, []);

  useEffect(
    () => () => {
      clearTimeout(hintTimer.current);
      stopListening();
    },
    [stopListening],
  );

  const startListening = () => {
    const Ctor = getSpeechCtor();
    if (!Ctor) {
      showHint("Voice input isn't supported in this browser — try Chrome or Edge.");
      return;
    }
    heardRef.current = false;
    baseRef.current = textRef.current.trim() ? textRef.current.trim() + " " : "";
    try {
      const rec = new Ctor();
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = navigator.language || "en-US";
      rec.onresult = (event) => {
        if (recRef.current !== rec) return; // late result after stop/send must not refill the box
        heardRef.current = true;
        let transcript = "";
        for (let i = 0; i < event.results.length; i++) transcript += event.results[i]?.[0]?.transcript ?? "";
        if (transcript) setText(baseRef.current + transcript);
      };
      rec.onerror = (event) => {
        if (recRef.current !== rec || event.error === "no-speech" || event.error === "aborted") return;
        showHint(SPEECH_ERRORS[event.error] ?? "Voice input stopped unexpectedly.");
        stopListening();
      };
      rec.onend = () => {
        if (listeningRef.current && heardRef.current) {
          // a restarted session starts a fresh result list: keep what was dictated so far
          baseRef.current = textRef.current.trim() ? textRef.current.trim() + " " : "";
          try {
            rec.start();
            return;
          } catch {
            /* fall through */
          }
        }
        stopListening();
      };
      recRef.current = rec;
      listeningRef.current = true;
      setListening(true);
      rec.start();
    } catch {
      stopListening();
      showHint("Couldn't start voice input.");
    }
  };

  /* textarea autosize + focus */
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(54, Math.min(el.scrollHeight, 260))}px`;
  }, [text]);

  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  /* attachments: picker, drag & drop, paste */
  const fileInputRef = useRef<HTMLInputElement>(null);
  const canAttach = enableAttachments && !!onAttach && !disabled;
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const hasFiles = (e: React.DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");

  const attach = (files: File[]) => {
    if (!canAttach || files.length === 0) return;
    onAttach?.(files);
  };

  const onDragEnter = (e: React.DragEvent) => {
    if (!canAttach || !hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  };
  const onDragOver = (e: React.DragEvent) => {
    if (!canAttach || !hasFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };
  const onDragLeave = (e: React.DragEvent) => {
    if (!canAttach || !hasFiles(e)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  };
  const onDrop = (e: React.DragEvent) => {
    if (!canAttach || !hasFiles(e)) return;
    e.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    attach(Array.from(e.dataTransfer.files));
  };

  /* a file dropped elsewhere on the page must not navigate the browser away: attach it instead */
  const onAttachRef = useRef(onAttach);
  useLayoutEffect(() => {
    onAttachRef.current = onAttach;
  });
  useEffect(() => {
    if (!canAttach) return;
    const isFileDrag = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const onOver = (e: DragEvent) => {
      if (isFileDrag(e)) e.preventDefault();
    };
    const onDropAnywhere = (e: DragEvent) => {
      if (!isFileDrag(e) || e.defaultPrevented) return;
      e.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      const files = Array.from(e.dataTransfer?.files ?? []);
      if (files.length) onAttachRef.current?.(files);
    };
    window.addEventListener("dragover", onOver);
    window.addEventListener("drop", onDropAnywhere);
    return () => {
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("drop", onDropAnywhere);
    };
  }, [canAttach]);

  const onPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!canAttach) return;
    const files = Array.from(e.clipboardData.files ?? []);
    if (files.length === 0 || e.clipboardData.getData("text/plain").trim()) return;
    e.preventDefault();
    const stamp = new Date().toISOString().slice(11, 19).replace(/:/g, "");
    attach(
      files.map((f, i) =>
        /^image\.\w+$/i.test(f.name) ? new File([f], `pasted-${stamp}${i ? "-" + i : ""}.${f.name.split(".").pop()}`, { type: f.type }) : f,
      ),
    );
  };

  /* submit */
  const uploading = attachments.some((a) => a.status === "uploading");
  const hasReady = attachments.some((a) => a.status === "ready");
  const hasContent = text.trim().length > 0 || hasReady;
  const canSend = !disabled && !isProcessing && !uploading && hasContent;

  const send = () => {
    if (disabled || isProcessing) return;
    if (uploading) {
      showHint("Hold on — your files are still uploading.");
      return;
    }
    if (!hasContent) return;
    stopListening();
    const prompt = text.trim();
    setText("");
    onSubmit({ prompt, modelId: currentModelId, effort: currentEffort, webSearch: web });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter" || e.shiftKey) return;
    if (e.nativeEvent.isComposing || e.keyCode === 229) return; // IME composition
    e.preventDefault();
    send();
  };

  const recording = voice ? voice.state === "recording" : listening;
  const transcribing = voice?.state === "transcribing";
  const active = text.length > 0 || attachments.length > 0 || recording || transcribing || isProcessing;
  const emotion: RobotEmotion = isProcessing || transcribing ? "thinking" : "reading";

  return (
    <MotionConfig reducedMotion="user">
      <div className={cn("relative flex w-full flex-col items-center", containerClassName)}>
        <AnimatePresence>
          {showWelcome && !active && (
            <motion.div
              key="welcome-header"
              initial={{ opacity: 0, y: -6, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, y: -6, height: 0, transition: { duration: 0.22 } }}
              transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
              className="mb-3.5 flex w-full select-none flex-col items-center justify-center gap-3.5 text-center sm:mb-4 sm:flex-row sm:justify-start sm:gap-4.5 sm:text-left"
            >
              {showMascot && (
                <motion.div layoutId={layoutId} className="shrink-0">
                  <RobotBeta emotion="reading" textLength={0} isListening={recording} />
                </motion.div>
              )}
              <div>
                <h2
                  className="text-2xl font-semibold tracking-tight text-zinc-950 sm:text-[1.7rem] dark:text-white"
                  style={{ fontFamily: "var(--font-brand, inherit)" }}
                >
                  {title}
                </h2>
                {subtitle && <p className="mt-0.5 text-xs font-medium text-zinc-600 sm:text-sm dark:text-zinc-400">{subtitle}</p>}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.div
          className="relative w-full"
          animate={{ paddingTop: showMascot && active ? 72 : 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 26 }}
        >
          {showMascot && active && (
            <motion.div
              layoutId={layoutId}
              transition={{ type: "spring", stiffness: 320, damping: 26 }}
              className="pointer-events-none absolute right-4 top-1 z-20 sm:right-6"
            >
              <RobotBeta emotion={emotion} textLength={text.length} isListening={recording} />
            </motion.div>
          )}

          <div
            onDragEnter={onDragEnter}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className={cn(
              "relative w-full rounded-3xl",
              "z-10",
              "border border-zinc-200/90 bg-white p-3.5 shadow-[0_20px_50px_-14px_rgba(76,29,149,0.12)] transition-all duration-300 focus-within:border-zinc-300 focus-within:shadow-[0_24px_60px_-14px_rgba(76,29,149,0.18)] sm:p-5 dark:border-white/10 dark:bg-zinc-900 dark:shadow-[0_25px_60px_rgba(0,0,0,0.45)] dark:focus-within:border-white/25",
              disabled && "cursor-not-allowed opacity-60",
              className,
            )}
          >
            <AnimatePresence>
              {dragging && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="pointer-events-none absolute inset-0 z-30 grid place-items-center rounded-3xl border-2 border-dashed border-rose-400/70 bg-white/85 backdrop-blur-sm dark:bg-zinc-900/85"
                >
                  <div className="flex flex-col items-center gap-1.5 text-sm font-semibold text-zinc-800 dark:text-zinc-100">
                    <span className="grid size-10 place-items-center rounded-full bg-primary text-primary-foreground shadow-md">
                      <PiUploadSimpleBold size={18} />
                    </span>
                    Drop files to attach
                    <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">PDF, Word, Excel, text, images</span>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {attachments.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                <AnimatePresence initial={false}>
                  {attachments.map((a) => (
                    <AttachmentChip key={a.id} a={a} onRemove={onRemoveAttachment} disabled={disabled} />
                  ))}
                </AnimatePresence>
              </div>
            )}

            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={onKeyDown}
              onPaste={onPaste}
              disabled={disabled}
              rows={1}
              aria-label="Message"
              placeholder={
                recording
                  ? voice
                    ? "Listening… tap the mic again to send"
                    : "Listening… speak your mind"
                  : transcribing
                    ? "Transcribing…"
                    : isProcessing
                    ? web
                      ? "Searching the web and thinking…"
                      : "Thinking…"
                    : placeholder
              }
              className="max-h-64 w-full resize-none overflow-y-auto bg-transparent text-base leading-relaxed font-medium text-zinc-900 outline-hidden transition-[height] duration-150 placeholder:text-zinc-400 focus:outline-none dark:text-zinc-100 dark:placeholder:text-zinc-500"
              style={{ minHeight: "54px" }}
            />

            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 border-t border-zinc-200/70 pt-3 dark:border-white/5">
              <div className="relative flex flex-1 items-center gap-1 sm:gap-2">
                {/* model + effort */}
                <ModelPicker
                  models={models}
                  current={currentModel}
                  onSelect={selectModel}
                  effort={currentEffort}
                  onEffortChange={selectEffort}
                  disabled={disabled}
                />

                {enableAttachments && (
                  <>
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      accept={ACCEPTED_FILES}
                      onChange={(e) => {
                        attach(Array.from(e.target.files ?? []));
                        e.target.value = "";
                      }}
                      disabled={!canAttach}
                      className="hidden"
                      tabIndex={-1}
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={!canAttach}
                      aria-label="Attach files"
                      title="Attach files (or drop / paste them)"
                      className="shrink-0 rounded-xl p-2 text-zinc-600 transition-all hover:bg-zinc-100 hover:text-zinc-950 disabled:cursor-not-allowed disabled:opacity-50 dark:text-zinc-400 dark:hover:bg-white/5 dark:hover:text-white"
                    >
                      <PiPaperclipBold size={16} />
                    </button>
                  </>
                )}

                {enableWebSearch && (
                  <button
                    type="button"
                    onClick={toggleWeb}
                    disabled={disabled}
                    aria-pressed={web}
                    aria-label={web ? "Web search on" : "Web search off"}
                    title={web ? "Web search enabled" : "Enable live web search"}
                    className={cn(
                      "flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl px-2 py-1.5 text-xs transition-all disabled:cursor-not-allowed disabled:opacity-50 min-[400px]:px-2.5",
                      web
                        ? "border border-emerald-500/30 bg-emerald-500/10 font-semibold text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-400"
                        : "border border-transparent font-medium text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-400 dark:hover:bg-white/5 dark:hover:text-white",
                    )}
                  >
                    <PiGlobeBold size={15} className="shrink-0" />
                    <span className="hidden min-[400px]:inline">{web ? "Search on" : "Search"}</span>
                  </button>
                )}
              </div>

              <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
                <AnimatePresence>
                  {recording && voice && (
                    <motion.div
                      key="rec"
                      initial={{ opacity: 0, scale: 0.85, x: 6 }}
                      animate={{ opacity: 1, scale: 1, x: 0 }}
                      exit={{ opacity: 0, scale: 0.85, x: 6 }}
                      transition={{ duration: 0.18 }}
                      className="flex h-8 shrink-0 items-center gap-1.5 rounded-xl border border-red-500/25 bg-red-500/10 px-2 text-xs font-medium text-red-600 tabular-nums dark:text-red-400"
                    >
                      <span className="flex h-4 items-center gap-[2px]" aria-hidden="true">
                        {[0.55, 1, 0.75, 0.9, 0.6].map((k, i) => (
                          <span
                            key={i}
                            className="w-[3px] rounded-full bg-red-500 transition-[height] duration-100"
                            style={{ height: `${Math.round(3 + Math.min(1, voice.level * 2.4) * 13 * k)}px` }}
                          />
                        ))}
                      </span>
                      <span>{`${Math.floor(voice.seconds / 60)}:${String(voice.seconds % 60).padStart(2, "0")}`}</span>
                      <button
                        type="button"
                        onClick={voice.onCancel}
                        aria-label="Discard recording"
                        title="Discard recording"
                        className="-mr-0.5 grid size-5 place-items-center rounded-md text-red-600/80 hover:bg-red-500/15 hover:text-red-700 dark:text-red-300"
                      >
                        <PiXBold size={10} />
                      </button>
                    </motion.div>
                  )}
                  {transcribing && (
                    <motion.div
                      key="stt"
                      initial={{ opacity: 0, scale: 0.85, x: 6 }}
                      animate={{ opacity: 1, scale: 1, x: 0 }}
                      exit={{ opacity: 0, scale: 0.85, x: 6 }}
                      transition={{ duration: 0.18 }}
                      className="flex h-8 shrink-0 items-center gap-1.5 rounded-xl bg-zinc-100 px-2.5 text-xs font-medium text-zinc-600 dark:bg-white/5 dark:text-zinc-300"
                      role="status"
                    >
                      <LoaderCircle size={13} className="animate-spin" aria-hidden="true" /> Transcribing
                    </motion.div>
                  )}
                  {listening && !voice && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.85, x: 6 }}
                      animate={{ opacity: 1, scale: 1, x: 0 }}
                      exit={{ opacity: 0, scale: 0.85, x: 6 }}
                      transition={{ duration: 0.18 }}
                      className="hidden h-8 shrink-0 items-center gap-1 rounded-xl border border-red-500/25 bg-red-500/10 px-2.5 py-1.5 shadow-[0_0_12px_rgba(239,68,68,0.25)] min-[400px]:flex"
                      aria-hidden="true"
                    >
                      {[
                        { min: 4, max: 13, duration: 0.45 },
                        { min: 6, max: 18, duration: 0.55 },
                        { min: 8, max: 22, duration: 0.38 },
                        { min: 5, max: 16, duration: 0.5 },
                        { min: 4, max: 11, duration: 0.42 },
                      ].map((bar, i) => (
                        <motion.span
                          key={i}
                          className="w-1 rounded-full bg-red-500"
                          animate={{ height: [`${bar.min}px`, `${bar.max}px`, `${bar.min}px`], opacity: [0.7, 1, 0.7] }}
                          transition={{ duration: bar.duration, repeat: Infinity, ease: "easeInOut", delay: i * 0.08 }}
                        />
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>

                {enableVoice && (
                  <button
                    type="button"
                    onClick={() => (voice ? voice.onToggle() : listening ? stopListening() : startListening())}
                    disabled={disabled || transcribing || (!!voice && isProcessing)}
                    aria-pressed={recording}
                    aria-label={voice ? (recording ? "Stop and send" : "Ask by voice (answer is read aloud)") : listening ? "Stop voice input" : "Dictate with voice"}
                    title={voice ? (recording ? "Stop and send" : "Ask by voice: Sphura answers out loud") : listening ? "Stop voice input" : "Dictate with voice"}
                    className={cn(
                      "shrink-0 rounded-xl p-2 transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50",
                      recording
                        ? "animate-pulse bg-red-500 text-white shadow-[0_0_12px_rgba(239,68,68,0.5)]"
                        : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-400 dark:hover:bg-white/5 dark:hover:text-white",
                    )}
                  >
                    {recording ? <PiMicrophoneFill size={16} /> : <PiMicrophoneBold size={16} />}
                  </button>
                )}

                {isProcessing ? (
                  <button
                    type="button"
                    onClick={onCancel}
                    disabled={!onCancel}
                    aria-label="Stop generating"
                    title="Stop generating"
                    className="grid size-9 shrink-0 place-items-center rounded-full border border-zinc-300 bg-white text-zinc-800 shadow-xs transition-all hover:scale-105 hover:bg-zinc-50 active:scale-95 disabled:cursor-default disabled:hover:scale-100 dark:border-white/15 dark:bg-zinc-800 dark:text-zinc-100"
                  >
                    {onCancel ? <PiStopFill size={14} /> : <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={send}
                    disabled={!canSend}
                    aria-label={uploading ? "Waiting for uploads" : "Send message"}
                    title={uploading ? "Waiting for uploads to finish…" : "Send message"}
                    className={cn(
                      "grid size-9 shrink-0 place-items-center rounded-full transition-all duration-200",
                      canSend
                        ? "bg-primary text-primary-foreground shadow-sm hover:scale-105 active:scale-95"
                        : "cursor-not-allowed bg-zinc-200/60 text-zinc-400 dark:bg-white/5 dark:text-zinc-600",
                    )}
                  >
                    {uploading ? <LoaderCircle size={16} className="animate-spin" aria-hidden="true" /> : <PiArrowUpBold size={16} />}
                  </button>
                )}
              </div>
            </div>

            <AnimatePresence>
              {hint && (
                <motion.p
                  key="hint"
                  role="status"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.18 }}
                  className="overflow-hidden px-1 pt-2 text-xs font-medium text-amber-700 dark:text-amber-400"
                >
                  {hint}
                </motion.p>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </MotionConfig>
  );
}

export default AiMascotInput;
