import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import MorphOrb from "@/components/ui/ai-thiking-orb-and-input";
import { useModelChoice } from "@/hooks/use-model-choice";
import { sendChat } from "@/lib/chat-runner";
import { clip, toPlainText, uid } from "@/lib/format";
import { PHASE_PROGRAM } from "@/lib/types";
import { useChatStore } from "@/stores/chat-store";

/** Full-screen MorphOrb: one question → a fast answer, driven by live agent status. */
export default function Focus() {
  const { selected } = useModelChoice();
  const modelId = selected?.id ?? null;
  const [streamKey, setStreamKey] = useState<string | null>(null);
  const stream = useChatStore((s) => (streamKey ? s.streams[streamKey] : undefined));

  useEffect(() => {
    document.title = "Focus · Sphura";
    return () => {
      document.title = "Sphura";
    };
  }, []);

  const onSubmit = useCallback(
    async (text: string, signal: AbortSignal): Promise<string> => {
      const key = `focus:${uid()}`;
      setStreamKey(key);
      const res = await sendChat({
        key,
        request: { conversationId: null, content: text, model: modelId, webSearch: false, docIds: [], mode: "chat", effort: "fast" },
        onStart: (id) => setStreamKey(id),
        signal, // Esc / reset in the orb (or leaving the page) stops the answer too
      });
      if (res.status === "done") {
        const plain = toPlainText(res.text).replace(/\s+/g, " ").trim();
        // The orb's answer card is small; the full answer is saved as a chat.
        return clip(plain, 280) || "…";
      }
      if (res.status === "stopped") return "Stopped.";
      return `Sorry — ${res.error ?? "something went wrong."}`;
    },
    [modelId],
  );

  return (
    <div className="relative h-dvh w-full overflow-hidden bg-background">
      <Link
        to="/"
        className="absolute top-[max(env(safe-area-inset-top),1rem)] left-4 z-50 inline-flex items-center gap-1.5 rounded-full border bg-background/70 px-3 py-1.5 text-sm text-muted-foreground shadow-xs backdrop-blur transition-colors hover:text-foreground focus-visible:outline-2"
      >
        <ArrowLeft className="size-4" /> Back
      </Link>
      <MorphOrb
        onSubmit={onSubmit}
        statusLabel={stream ? (stream.label ?? undefined) : undefined}
        statusProgram={stream?.phase ? PHASE_PROGRAM[stream.phase] : undefined}
        placeholder="Ask about money…"
      />
    </div>
  );
}
