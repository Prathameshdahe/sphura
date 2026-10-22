import { useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { RotateCcw } from "lucide-react";
import { AssistantMessage } from "@/components/chat/assistant-message";
import { UserMessage } from "@/components/chat/user-message";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { AttachmentRef, Message } from "@/lib/types";
import type { ChatStream } from "@/stores/chat-store";

interface ThreadProps {
  /** Conversation the thread shows; when it changes, the messages already there rise in one after another. */
  threadKey?: string | null;
  messages: Message[];
  stream?: ChatStream | null;
  lastCompletedId: string | null;
  modelLabel: (id?: string | null) => string | null;
  onEdit?: (messageId: string, content: string) => void;
  onRegenerate?: () => void;
}

const EASE = [0.22, 1, 0.36, 1] as const;
const enter = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: EASE },
};
/** Messages present when a chat opens rise in, 45 ms apart (only the last 8 are staggered; older ones are off-screen). */
const STAGGER = 0.045;
const STAGGERED = 8;

/** Saved messages + the in-flight optimistic user message and streaming draft. */
export function Thread({ threadKey = null, messages, stream, lastCompletedId, modelLabel, onEdit, onRegenerate }: ThreadProps) {
  // Ids that were on screen when this conversation opened: those animate in (staggered); later ones swap in quietly
  // (the optimistic message / streaming draft already played their own entrance).
  const [opened, setOpened] = useState<{ key: string | null; ids: Set<string> | null }>({ key: threadKey, ids: null });
  let openIds = opened.ids;
  if (opened.key !== threadKey || (openIds === null && messages.length > 0)) {
    openIds = stream ? new Set<string>() : new Set(messages.map((m) => m.id));
    setOpened({ key: threadKey, ids: openIds });
  }
  const firstStaggered = Math.max(0, messages.length - STAGGERED);

  const busy = !!stream;
  const seenDocs = new Set<string>();
  let lastAssistant = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") {
      lastAssistant = i;
      break;
    }
  }
  const lastIsAssistant = lastAssistant === messages.length - 1 && lastAssistant !== -1;
  const draftSaved = !!stream?.assistantMessageId && messages.some((m) => m.id === stream.assistantMessageId);

  // Follow-up messages re-send earlier docs for grounding; show each attachment once.
  const freshAttachments = (list: AttachmentRef[]) =>
    list.filter((a) => {
      if (seenDocs.has(a.docId)) return false;
      seenDocs.add(a.docId);
      return true;
    });

  // One flat keyed list: the draft is keyed by its assistant message id once `start` arrives, so when
  // `done` swaps it for the saved message React keeps the same component (and plays its orb→logo hand-off).
  const items: ReactNode[] = messages.map((m, i) => (
    <motion.div
      key={m.id}
      {...(openIds?.has(m.id)
        ? {
            initial: { opacity: 0, y: 12 },
            animate: { opacity: 1, y: 0 },
            transition: { duration: 0.32, ease: EASE, delay: Math.max(0, i - firstStaggered) * STAGGER },
          }
        : { initial: false })}
    >
      {m.role === "user" ? (
        <UserMessage
          content={m.content}
          attachments={freshAttachments(m.attachments)}
          onEdit={!busy && onEdit ? (content) => onEdit(m.id, content) : undefined}
        />
      ) : (
        <AssistantMessage
          message={m}
          isLast={!stream && i === lastAssistant && lastIsAssistant}
          busy={busy}
          justCompleted={m.id === lastCompletedId}
          modelLabel={modelLabel(m.model)}
          fallbackLabel={typeof m.meta?.fallbackFrom === "string" ? modelLabel(m.meta.fallbackFrom) : null}
          onRegenerate={onRegenerate}
        />
      )}
    </motion.div>
  ));

  if (stream?.optimisticUser && !stream.started) {
    items.push(
      <motion.div key="optimistic-user" {...enter}>
        <UserMessage
          content={stream.optimisticUser.content}
          attachments={freshAttachments(stream.optimisticUser.attachments)}
          pending
        />
      </motion.div>,
    );
  }

  if (stream && !draftSaved) {
    items.push(
      <motion.div key={stream.assistantMessageId ?? "draft"} {...(stream.started ? { initial: false } : enter)}>
        <AssistantMessage stream={stream} isLast busy justCompleted={false} modelLabel={modelLabel(stream.model)} />
      </motion.div>,
    );
  }

  return (
    <div className="flex flex-col gap-9">
      {items}

      {!stream && messages.length > 0 && !lastIsAssistant && onRegenerate && (
        <div className="flex items-center gap-3 pl-10 text-sm text-muted-foreground">
          <span>No answer was saved for this message.</span>
          <Button variant="outline" size="sm" onClick={onRegenerate}>
            <RotateCcw /> Answer it
          </Button>
        </div>
      )}
    </div>
  );
}

export function ThreadSkeleton() {
  return (
    <div className="flex flex-col gap-10" aria-busy="true" aria-label="Loading conversation">
      <div className="flex justify-end">
        <Skeleton className="h-11 w-2/3 rounded-2xl" />
      </div>
      <div className="flex gap-4">
        <Skeleton className="size-7 rounded-full" />
        <div className="flex-1 space-y-2.5">
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
      <div className="flex justify-end">
        <Skeleton className="h-9 w-1/2 rounded-2xl" />
      </div>
    </div>
  );
}
