import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AudioLines, Square, Volume2, VolumeX } from "lucide-react";
import { AiMascotInput, type ComposerSubmit, type ComposerVoice } from "@/components/ui/ai-mascot-input";
import { ttsSupported } from "@/components/voice/tts";
import { useVoiceInput, voiceInputSupported } from "@/components/voice/use-voice-input";
import type { useAttachments } from "@/hooks/use-attachments";
import { useModelChoice } from "@/hooks/use-model-choice";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/stores/prefs";
import { useSpeech } from "@/stores/speech";
import { useUi } from "@/stores/ui";

interface ChatComposerProps {
  attachments: ReturnType<typeof useAttachments>;
  isStreaming: boolean;
  onSend: (data: ComposerSubmit) => void;
  onStop: () => void;
  value: string;
  onChange: (v: string) => void;
  welcome?: { title: string; subtitle: string };
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
  /** Opens hands-free voice mode. */
  onVoiceMode?: () => void;
  /** Small centred note in the footer row (desktop). */
  note?: ReactNode;
}

function SpeakingBars() {
  return (
    <span className="flex h-3 items-end gap-[2px]" aria-hidden>
      {[0.55, 1, 0.7, 0.9].map((h, i) => (
        <motion.span
          key={i}
          className="w-[2.5px] rounded-full bg-current"
          style={{ height: `${h * 100}%` }}
          animate={{ scaleY: [0.35, 1, 0.5, 0.85, 0.35] }}
          transition={{ duration: 1 + i * 0.13, repeat: Infinity, ease: "easeInOut", delay: i * 0.09 }}
        />
      ))}
    </span>
  );
}

/**
 * AiMascotInput wired to /api/models, persisted composer prefs and live attachments, plus the voice row:
 * the mic asks by voice (record → transcribe → send → the answer is read aloud), a toggle reads every answer
 * aloud, a "Speaking…" pill stops playback, and "Voice" opens hands-free mode.
 */
export function ChatComposer({
  attachments,
  isStreaming,
  onSend,
  onStop,
  value,
  onChange,
  welcome,
  placeholder,
  autoFocus,
  className,
  onVoiceMode,
  note,
}: ChatComposerProps) {
  const { composerModels, selected, setModelId, forVoice } = useModelChoice();
  const effort = usePrefs((s) => s.effort);
  const setEffort = usePrefs((s) => s.setEffort);
  const webSearch = usePrefs((s) => s.webSearch);
  const setWebSearch = usePrefs((s) => s.setWebSearch);
  const autoSpeak = usePrefs((s) => s.autoSpeak);
  const setAutoSpeak = usePrefs((s) => s.setAutoSpeak);
  const speaking = useSpeech((s) => !!s.speakingId);
  const canSpeak = useMemo(() => ttsSupported(), []);

  // Send pulse: one ring on the composer the moment a message leaves (≤ 400 ms, CSS-driven).
  const [pulse, setPulse] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  const send = (d: ComposerSubmit) => {
    setPulse((n) => n + 1);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setPulse(0), 420);
    onSend(d);
  };

  /* ask by voice: the transcript is sent straight away and its answer is read aloud */
  const voiceInput = useVoiceInput((text) => {
    useUi.getState().setSpeakNext(true);
    send({ prompt: text, modelId: forVoice, effort, webSearch });
  });
  const voiceSupported = useMemo(() => voiceInputSupported(), []);
  const voice: ComposerVoice | undefined = voiceSupported
    ? { state: voiceInput.state, level: voiceInput.level, seconds: voiceInput.seconds, onToggle: voiceInput.toggle, onCancel: voiceInput.cancel }
    : undefined;

  return (
    <div className="w-full">
      <div className={cn("rounded-3xl", pulse > 0 && "sphura-send-pulse")}>
        <AiMascotInput
          models={composerModels}
          modelId={selected?.id}
          onModelChange={setModelId}
          effort={effort}
          onEffortChange={setEffort}
          webSearch={webSearch}
          onWebSearchChange={setWebSearch}
          attachments={attachments.items}
          onAttach={attachments.add}
          onRemoveAttachment={attachments.remove}
          onSubmit={send}
          onCancel={onStop}
          isProcessing={isStreaming}
          value={value}
          onChange={onChange}
          showWelcome={!!welcome}
          title={welcome?.title}
          subtitle={welcome?.subtitle}
          placeholder={placeholder ?? (isStreaming ? "Sphura is answering…" : "Reply to Sphura…")}
          enableVoice
          voice={voice}
          enableWebSearch
          enableAttachments
          autoFocus={autoFocus}
          containerClassName={className}
        />
      </div>
      <div className="mt-1.5 flex min-h-8 items-center gap-2 px-1">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <AnimatePresence mode="popLayout" initial={false}>
            {speaking ? (
              <motion.div
                key="speaking"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.16 }}
                className="inline-flex h-7 items-center gap-2 rounded-full border bg-card pr-1 pl-2.5 text-xs font-medium text-foreground shadow-xs"
                role="status"
              >
                <span className="text-brand">
                  <SpeakingBars />
                </span>
                Speaking…
                <button
                  type="button"
                  onClick={() => useSpeech.getState().stop()}
                  aria-label="Stop speaking"
                  className="grid size-5 place-items-center rounded-full bg-muted text-foreground transition-colors hover:bg-accent focus-visible:outline-2"
                >
                  <Square className="size-2.5 fill-current" />
                </button>
              </motion.div>
            ) : note ? (
              <motion.span
                key="note"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="hidden truncate text-[11px] text-muted-foreground sm:inline"
              >
                {note}
              </motion.span>
            ) : null}
          </AnimatePresence>
        </div>
        {canSpeak && (
          <button
            type="button"
            onClick={() => setAutoSpeak(!autoSpeak)}
            aria-pressed={autoSpeak}
            aria-label={autoSpeak ? "Stop reading answers aloud" : "Read every answer aloud"}
            title={autoSpeak ? "Answers are read aloud" : "Read every answer aloud"}
            className={cn(
              "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-[color,background-color,border-color,transform] focus-visible:outline-2 active:scale-[0.96] motion-reduce:active:scale-100",
              autoSpeak ? "border-brand/30 bg-accent text-brand" : "bg-card text-muted-foreground hover:text-foreground",
            )}
          >
            {autoSpeak ? <Volume2 className="size-3.5" /> : <VolumeX className="size-3.5" />}
            <span className="hidden min-[400px]:inline">Read aloud</span>
          </button>
        )}
        {onVoiceMode && (
          <button
            type="button"
            onClick={onVoiceMode}
            aria-label="Start hands-free voice mode"
            title="Hands-free: talk, listen, talk again"
            className="group/voice inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border bg-card px-2.5 text-xs font-medium text-muted-foreground transition-[color,border-color,transform] hover:text-foreground focus-visible:outline-2 active:scale-[0.96] motion-reduce:active:scale-100"
          >
            <AudioLines className="size-3.5 text-brand transition-transform group-hover/voice:scale-110" />
            Voice
          </button>
        )}
      </div>
    </div>
  );
}
