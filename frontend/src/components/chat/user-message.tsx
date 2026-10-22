import { memo, useEffect, useRef, useState } from "react";
import { Check, Copy, Pencil } from "lucide-react";
import { FileIcon } from "@/components/file-icon";
import { IconButton } from "@/components/icon-button";
import { Button } from "@/components/ui/button";
import { useCopy } from "@/hooks/use-copy";
import { formatBytes } from "@/lib/format";
import type { AttachmentRef } from "@/lib/types";
import { cn } from "@/lib/utils";

export function AttachmentChips({ attachments, className }: { attachments: AttachmentRef[]; className?: string }) {
  if (attachments.length === 0) return null;
  return (
    <div className={cn("flex max-w-[85%] flex-wrap justify-end gap-1.5", className)}>
      {attachments.map((a) => (
        <div key={a.docId} className="flex max-w-[16rem] items-center gap-2 rounded-xl border bg-card py-1.5 pr-3 pl-1.5 text-xs shadow-xs">
          <FileIcon name={a.filename} mime={a.mimeType} size="sm" />
          <div className="min-w-0">
            <div className="truncate font-medium">{a.filename}</div>
            <div className="text-[11px] text-muted-foreground">{formatBytes(a.sizeBytes)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

interface UserMessageProps {
  content: string;
  attachments: AttachmentRef[];
  pending?: boolean;
  /** Undefined → editing disabled (e.g. while a response is streaming). */
  onEdit?: (content: string) => void;
}

/** Right-aligned user bubble with copy + inline edit-and-resend. */
export const UserMessage = memo(function UserMessage({ content, attachments, pending, onEdit }: UserMessageProps) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(content);
  const ref = useRef<HTMLTextAreaElement>(null);
  const { copied, copy } = useCopy();

  useEffect(() => {
    if (!editing) return;
    const el = ref.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, [editing]);

  const startEdit = () => {
    setValue(content);
    setEditing(true);
  };
  const submit = () => {
    const next = value.trim();
    if (!next || !onEdit) return;
    setEditing(false);
    if (next !== content.trim()) onEdit(next);
  };

  return (
    <div className="group/user flex flex-col items-end gap-1.5">
      <AttachmentChips attachments={attachments} />
      {editing ? (
        <div className="w-full max-w-[85%] rounded-2xl border bg-card p-2 shadow-sm focus-within:ring-3 focus-within:ring-ring/30">
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              } else if (e.key === "Escape") {
                e.stopPropagation();
                setEditing(false);
              }
            }}
            rows={Math.min(10, Math.max(2, value.split("\n").length))}
            aria-label="Edit message"
            className="w-full resize-none bg-transparent px-2 py-1.5 text-[0.95rem] leading-relaxed outline-none"
          />
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={submit} disabled={!value.trim() || !onEdit}>
              Send
            </Button>
          </div>
        </div>
      ) : (
        <div
          className={cn(
            "max-w-[85%] rounded-[1.25rem] rounded-br-md border border-border/60 bg-bubble px-4 py-2.5 text-[0.95rem] leading-relaxed break-words whitespace-pre-wrap text-foreground",
            pending && "opacity-80",
          )}
        >
          {content}
        </div>
      )}
      {!editing && !pending && (
        <div className="flex items-center gap-0.5 opacity-100 transition-opacity md:opacity-0 md:group-hover/user:opacity-100 md:focus-within:opacity-100">
          <IconButton label={copied ? "Copied" : "Copy"} size="icon-xs" onClick={() => void copy(content)}>
            {copied ? <Check /> : <Copy />}
          </IconButton>
          {onEdit && (
            <IconButton label="Edit" size="icon-xs" onClick={startEdit}>
              <Pencil />
            </IconButton>
          )}
        </div>
      )}
    </div>
  );
});
