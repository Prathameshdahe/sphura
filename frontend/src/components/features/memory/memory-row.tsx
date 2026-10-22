import { memo } from "react";
import { motion } from "framer-motion";
import { MessageSquareText, PencilLine, Trash } from "lucide-react";
import { IconButton } from "@/components/icon-button";
import type { MemoryItem } from "@/lib/feature-types";
import { formatRelative } from "@/lib/format";

/** One remembered fact: content, provenance, date, delete. */
export const MemoryRow = memo(function MemoryRow({ item, onDelete }: { item: MemoryItem; onDelete: (item: MemoryItem) => void }) {
  const fromChat = !!item.sourceMessageId;
  const date = new Date(item.createdAt);
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -12, transition: { duration: 0.18 } }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="group flex items-start gap-3 rounded-xl border bg-card p-3 transition-colors hover:border-foreground/15 sm:p-4"
    >
      <span
        className="mt-0.5 hidden size-8 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground min-[400px]:grid"
        title={fromChat ? "Learned from a chat" : "Added by you"}
        aria-hidden
      >
        {fromChat ? <MessageSquareText className="size-4" strokeWidth={1.75} /> : <PencilLine className="size-4" strokeWidth={1.75} />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-relaxed break-words">{item.content}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {fromChat ? "Learned from a chat" : "Added by you"} ·{" "}
          <time dateTime={item.createdAt} title={Number.isNaN(date.getTime()) ? undefined : date.toLocaleString()}>
            {formatRelative(item.createdAt)}
          </time>
        </p>
      </div>
      <IconButton label="Forget this memory" onClick={() => onDelete(item)} className="shrink-0 sm:opacity-60 sm:group-hover:opacity-100 sm:focus-visible:opacity-100">
        <Trash />
      </IconButton>
    </motion.li>
  );
});
