import { Pause, Play, Square, Volume2 } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { IconButton } from "@/components/icon-button";
import { ttsSupported } from "@/components/voice/tts";
import { useSpeech } from "@/stores/speech";

function Bars({ paused }: { paused: boolean }) {
  return (
    <span className="flex h-3.5 items-end gap-[2px]" aria-hidden>
      {[0.55, 1, 0.7, 0.9].map((h, i) => (
        <motion.span
          key={i}
          className="w-[2.5px] rounded-full bg-current"
          style={{ height: `${h * 100}%` }}
          animate={paused ? { scaleY: 0.35 } : { scaleY: [0.35, 1, 0.5, 0.85, 0.35] }}
          transition={paused ? { duration: 0.2 } : { duration: 1 + i * 0.13, repeat: Infinity, ease: "easeInOut", delay: i * 0.09 }}
        />
      ))}
    </span>
  );
}

/** "Read aloud" for an answer (server voice first, browser voice as fallback); while playing it turns into a small player. */
export function ReadAloud({ id, text }: { id: string; text: string }) {
  const speaking = useSpeech((s) => s.speakingId === id);
  const paused = useSpeech((s) => s.paused);
  const engine = useSpeech((s) => s.engine);
  if (!ttsSupported() || !text.trim()) return null;
  const { speak, pause, resume, stop } = useSpeech.getState();

  if (!speaking) {
    return (
      <IconButton
        label="Read aloud"
        onClick={() =>
          void speak(id, text).then((r) => {
            if (r === "error") toast.error("Couldn't read this answer aloud.");
          })
        }
      >
        <Volume2 />
      </IconButton>
    );
  }
  return (
    <span
      className="mx-0.5 inline-flex items-center gap-0.5 rounded-full bg-brand/10 py-0.5 pr-0.5 pl-2.5 text-brand ring-1 ring-brand/25 ring-inset"
      title={engine === "server" ? "Server voice" : "Browser voice"}
    >
      <Bars paused={paused} />
      <span className="sr-only" role="status">
        {paused ? "Paused" : `Reading aloud (${engine === "server" ? "server voice" : "browser voice"})`}
      </span>
      <IconButton
        label={paused ? "Resume" : "Pause"}
        size="icon-xs"
        className="ml-1 text-current hover:bg-brand/15 hover:text-current"
        onClick={paused ? resume : pause}
      >
        {paused ? <Play /> : <Pause />}
      </IconButton>
      <IconButton label="Stop reading" size="icon-xs" className="text-current hover:bg-brand/15 hover:text-current" onClick={stop}>
        <Square className="fill-current" />
      </IconButton>
    </span>
  );
}
