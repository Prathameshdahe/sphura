import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { ComposerAttachment } from "@/components/ui/ai-mascot-input";
import { ApiError, api, errorMessage } from "@/lib/api";
import { uid } from "@/lib/format";
import { qk } from "@/lib/queries";
import type { AttachmentRef, DocumentInfo } from "@/lib/types";

export interface PendingAttachment extends ComposerAttachment {
  docId: string | null;
  mimeType: string;
  sizeBytes: number;
}

const POLL_MS = 1200;
const MAX_POLLS = 400;

const statusOf = (d: DocumentInfo): PendingAttachment["status"] =>
  d.status === "ready" ? "ready" : d.status === "error" ? "error" : "processing";

export const isImageName = (name: string, mime = "") =>
  mime.startsWith("image/") || /\.(png|jpe?g|webp|gif)$/i.test(name);

export function attachmentFromDoc(d: DocumentInfo): PendingAttachment {
  return {
    id: uid(),
    docId: d.id,
    name: d.filename,
    isImage: isImageName(d.filename, d.mimeType),
    status: statusOf(d),
    error: d.error ?? null,
    mimeType: d.mimeType,
    sizeBytes: d.sizeBytes,
  };
}

export function toAttachmentRef(a: PendingAttachment): AttachmentRef {
  return { docId: a.docId as string, filename: a.name, mimeType: a.mimeType, sizeBytes: a.sizeBytes };
}

/** Sendable = uploaded and not failed (processing docs are allowed; the server waits/uses what's indexed). */
export const isSendable = (a: PendingAttachment) => !!a.docId && (a.status === "ready" || a.status === "processing");

/** Composer attachments: upload immediately, then poll until ready/error. */
export function useAttachments(conversationId?: string | null) {
  const qc = useQueryClient();
  const [items, setItems] = useState<PendingAttachment[]>([]);
  const live = useRef(new Set<string>());
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const convRef = useRef(conversationId);
  useEffect(() => {
    convRef.current = conversationId;
  }, [conversationId]);

  const patch = useCallback((id: string, p: Partial<PendingAttachment>) => {
    setItems((list) => list.map((a) => (a.id === id ? { ...a, ...p } : a)));
  }, []);

  const stopPoll = useCallback((id: string) => {
    const t = timers.current.get(id);
    if (t) clearTimeout(t);
    timers.current.delete(id);
  }, []);

  const poll = useCallback(
    (id: string, docId: string) => {
      const tick = (attempt: number) => {
        if (!live.current.has(id) || attempt > MAX_POLLS) return;
        const t = setTimeout(async () => {
          if (!live.current.has(id)) return;
          try {
            const d = await api.document(docId);
            if (!live.current.has(id)) return;
            patch(id, { status: statusOf(d), error: d.error ?? null });
            if (d.status === "queued" || d.status === "processing") tick(attempt + 1);
            else void qc.invalidateQueries({ queryKey: qk.documentsAll });
          } catch (e) {
            if (!live.current.has(id)) return;
            if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
              // Deleted elsewhere (404) or signed out: stop polling instead of hammering the API.
              patch(id, { status: "error", error: e.status === 404 ? "This file was deleted." : e.detail });
              return;
            }
            tick(attempt + 3); // transient failure — back off a little
          }
        }, POLL_MS);
        timers.current.set(id, t);
      };
      tick(0);
    },
    [patch, qc],
  );

  const add = useCallback(
    (files: File[]) => {
      for (const file of files) {
        const id = uid();
        live.current.add(id);
        setItems((list) => [
          ...list,
          {
            id,
            docId: null,
            name: file.name,
            isImage: isImageName(file.name, file.type),
            status: "uploading",
            error: null,
            mimeType: file.type || "application/octet-stream",
            sizeBytes: file.size,
          },
        ]);
        api
          .uploadDocument(file, convRef.current)
          .then((d) => {
            if (!live.current.has(id)) return;
            patch(id, { docId: d.id, status: statusOf(d), error: d.error ?? null, mimeType: d.mimeType, sizeBytes: d.sizeBytes });
            void qc.invalidateQueries({ queryKey: qk.documentsAll });
            if (d.status === "queued" || d.status === "processing") poll(id, d.id);
          })
          .catch((e: unknown) => {
            if (!live.current.has(id)) return;
            const msg = errorMessage(e, "Upload failed");
            patch(id, { status: "error", error: msg });
            toast.error(`${file.name}: ${msg}`);
          });
      }
    },
    [patch, poll, qc],
  );

  const remove = useCallback(
    (id: string) => {
      live.current.delete(id);
      stopPoll(id);
      setItems((list) => list.filter((a) => a.id !== id));
    },
    [stopPoll],
  );

  /** Replace everything (used after send, on navigation, and to seed "Ask about this"). */
  const reset = useCallback(
    (next: PendingAttachment[] = []) => {
      for (const id of live.current) stopPoll(id);
      live.current = new Set(next.map((a) => a.id));
      setItems(next);
      for (const a of next) if (a.docId && a.status === "processing") poll(a.id, a.docId);
    },
    [poll, stopPoll],
  );

  useEffect(() => {
    const map = timers.current;
    const liveRef = live;
    return () => {
      liveRef.current = new Set();
      for (const t of map.values()) clearTimeout(t);
      map.clear();
    };
  }, []);

  return { items, add, remove, reset };
}
