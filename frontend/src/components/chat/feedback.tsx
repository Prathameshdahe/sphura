import { useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { toast } from "sonner";
import { IconButton } from "@/components/icon-button";
import { Button } from "@/components/ui/button";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { errorMessage } from "@/lib/api";
import { useSendFeedback } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { useFeedbackStore, type Vote } from "@/stores/feedback";

const REASONS = ["Inaccurate", "Not helpful", "Missing sources", "Too long", "Didn't follow instructions"];

/** Thumbs up / down (optimistic, toggles) + an optional "what went wrong?" note on thumbs down. */
export function FeedbackButtons({ messageId }: { messageId: string }) {
  const vote = useFeedbackStore((s) => s.votes[messageId] ?? null);
  const setVote = useFeedbackStore((s) => s.setVote);
  const send = useSendFeedback();
  const [askOpen, setAskOpen] = useState(false);
  const [reasons, setReasons] = useState<string[]>([]);
  const [note, setNote] = useState("");

  const submit = (value: Vote, comment?: string) => {
    const before = useFeedbackStore.getState().votes[messageId] ?? null;
    setVote(messageId, value);
    send.mutate(
      { messageId, value, ...(comment ? { comment } : {}) },
      {
        onError: (e) => {
          setVote(messageId, before);
          toast.error(`Couldn't save your feedback — ${errorMessage(e)}`);
        },
      },
    );
  };

  const click = (value: Vote) => {
    if (vote === value) {
      // Toggle off (the API keeps the last vote; this only clears it here).
      setVote(messageId, null);
      setAskOpen(false);
      return;
    }
    submit(value);
    if (value === -1) {
      setReasons([]);
      setNote("");
      setAskOpen(true);
    } else {
      setAskOpen(false);
      toast.success("Thanks for the feedback!");
    }
  };

  const sendNote = () => {
    const comment = [reasons.join(", "), note.trim()].filter(Boolean).join(" — ");
    setAskOpen(false);
    if (comment) submit(-1, comment.slice(0, 1000));
    toast.success("Thanks — this helps Sphura improve.");
  };

  return (
    <Popover open={askOpen} onOpenChange={setAskOpen}>
      <PopoverAnchor asChild>
        <span className="inline-flex items-center">
          <IconButton
            label={vote === 1 ? "Remove good rating" : "Good response"}
            aria-pressed={vote === 1}
            onClick={() => click(1)}
            className={cn(vote === 1 && "text-success hover:text-success")}
          >
            <ThumbsUp className={cn(vote === 1 && "fill-current/20")} />
          </IconButton>
          <IconButton
            label={vote === -1 ? "Remove bad rating" : "Bad response"}
            aria-pressed={vote === -1}
            onClick={() => click(-1)}
            className={cn(vote === -1 && "text-danger hover:text-danger")}
          >
            <ThumbsDown className={cn(vote === -1 && "fill-current/20")} />
          </IconButton>
        </span>
      </PopoverAnchor>
      <PopoverContent side="top" align="start" collisionPadding={12} className="w-[min(20rem,calc(100vw-1.5rem))] p-3">
        <p className="text-sm font-medium">What went wrong?</p>
        <div className="flex flex-wrap gap-1.5">
          {REASONS.map((r) => {
            const on = reasons.includes(r);
            return (
              <button
                key={r}
                type="button"
                aria-pressed={on}
                onClick={() => setReasons((list) => (on ? list.filter((x) => x !== r) : [...list, r]))}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs transition-colors focus-visible:outline-2",
                  on ? "border-foreground bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {r}
              </button>
            );
          })}
        </div>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) sendNote();
          }}
          rows={2}
          maxLength={800}
          placeholder="Anything else? (optional)"
          aria-label="Feedback comment"
          className="w-full resize-none rounded-lg border bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-ring/30"
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setAskOpen(false)}>
            Skip
          </Button>
          <Button size="sm" onClick={sendNote} disabled={!reasons.length && !note.trim()}>
            Send
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
