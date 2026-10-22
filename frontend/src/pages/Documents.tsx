import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  CircleAlert,
  CircleCheck,
  Clock,
  CloudUpload,
  FileText,
  LayoutDashboard,
  LoaderCircle,
  ScanText,
  MessageSquareText,
  Search,
  Trash,
  Upload,
} from "lucide-react";
import { toast } from "sonner";
import { FileIcon } from "@/components/file-icon";
import { IconButton } from "@/components/icon-button";
import { Page } from "@/components/layout/page";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/metrics/section";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api";
import { isTabularDoc } from "@/lib/feature-api/finance";
import type { NewChatState } from "@/lib/feature-types";
import { fileTypeLabel } from "@/lib/files";
import { formatBytes, formatRelative, uid } from "@/lib/format";
import { EASE_OUT } from "@/lib/motion";
import { qk, useDeleteDocument, useDocuments } from "@/lib/queries";
import type { DocumentInfo } from "@/lib/types";
import { glyph } from "@/components/icons/glyphs";

const ACCEPT = ".pdf,.docx,.txt,.md,.csv,.xlsx,.xls,.json,.html,.png,.jpg,.jpeg,.webp";

function StatusBadge({ status }: { status: DocumentInfo["status"] }) {
  if (status === "ready")
    return (
      <Badge variant="outline" className="gap-1 border-success/30 bg-success/10 text-success">
        <CircleCheck /> Ready
      </Badge>
    );
  if (status === "processing")
    return (
      <Badge variant="outline" className="gap-1 border-warning/30 bg-warning/10 text-warning">
        <LoaderCircle className="animate-spin" /> Processing
      </Badge>
    );
  if (status === "queued")
    return (
      <Badge variant="outline" className="gap-1 text-muted-foreground">
        <Clock /> Queued
      </Badge>
    );
  return (
    <Badge variant="destructive" className="gap-1">
      <CircleAlert /> Error
    </Badge>
  );
}

interface DocRowProps {
  doc: DocumentInfo;
  /** Position in the list: rows rise in 40 ms apart. */
  index: number;
  onAsk: () => void;
  onDashboard?: () => void;
  onDelete: () => void;
}

function DocRow({ doc, index, onAsk, onDashboard, onDelete }: DocRowProps) {
  const meta = [
    fileTypeLabel(doc.filename, doc.mimeType),
    formatBytes(doc.sizeBytes),
    doc.pageCount ? `${doc.pageCount} page${doc.pageCount === 1 ? "" : "s"}` : null,
    doc.chunkCount ? `${doc.chunkCount} chunk${doc.chunkCount === 1 ? "" : "s"}` : null,
    formatRelative(doc.createdAt),
  ].filter(Boolean);

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.18, delay: 0 } }}
      transition={{ duration: 0.24, delay: Math.min(index, 8) * 0.04, ease: EASE_OUT }}
      className="flex items-center gap-3 rounded-xl border bg-card p-3 transition-colors hover:border-foreground/15 sm:gap-4 sm:p-4"
    >
      <FileIcon name={doc.filename} mime={doc.mimeType} size="lg" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium" title={doc.filename}>
          {doc.filename}
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
          <StatusBadge status={doc.status} />
          {doc.ocrUsed && (
            <Badge variant="outline" className="gap-1 text-muted-foreground" title="Text extracted with OCR">
              <ScanText /> OCR
            </Badge>
          )}
          <span className="text-xs text-muted-foreground">{meta.join(" · ")}</span>
        </div>
        {doc.status === "error" && (
          <p className="mt-1.5 text-xs break-words text-destructive">{doc.error || "Processing failed."}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {onDashboard && (
          <IconButton label="Open in the dashboard" onClick={onDashboard} disabled={doc.status !== "ready"}>
            <LayoutDashboard />
          </IconButton>
        )}
        <Button variant="outline" size="sm" onClick={onAsk} disabled={doc.status === "error"} aria-label={`Ask about ${doc.filename}`}>
          <MessageSquareText className="text-muted-foreground" />
          <span className="hidden sm:inline">Ask about this</span>
        </Button>
        <IconButton label="Delete document" onClick={onDelete}>
          <Trash />
        </IconButton>
      </div>
    </motion.li>
  );
}

/** Library: drag-and-drop multi upload, live ingestion status, ask / dashboard / delete. */
export default function Documents() {
  const docs = useDocuments();
  const del = useDeleteDocument();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [filter, setFilter] = useState("");
  const [uploading, setUploading] = useState<{ id: string; name: string; size: number }[]>([]);
  const [confirm, setConfirm] = useState<DocumentInfo | null>(null);

  useEffect(() => {
    document.title = "Documents · Sphura";
    return () => {
      document.title = "Sphura";
    };
  }, []);

  const list = useMemo(() => {
    const all = docs.data ?? [];
    const f = filter.trim().toLowerCase();
    return f ? all.filter((d) => d.filename.toLowerCase().includes(f)) : all;
  }, [docs.data, filter]);

  const stats = useMemo(() => {
    const all = docs.data ?? [];
    return {
      total: all.length,
      ready: all.filter((d) => d.status === "ready").length,
      bytes: all.reduce((n, d) => n + d.sizeBytes, 0),
    };
  }, [docs.data]);

  const upload = (files: File[]) => {
    if (files.length === 0) return;
    for (const file of files) {
      const id = uid();
      setUploading((u) => [...u, { id, name: file.name, size: file.size }]);
      api
        .uploadDocument(file)
        .then(() => qc.invalidateQueries({ queryKey: qk.documentsAll }))
        .catch((e: unknown) => toast.error(`${file.name}: ${errorMessage(e, "Upload failed")}`))
        .finally(() => setUploading((u) => u.filter((x) => x.id !== id)));
    }
  };

  const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer.types).includes("Files");
  const dragProps = {
    onDragEnter: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth.current += 1;
      setDragging(true);
    },
    onDragOver: (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    },
    onDragLeave: () => {
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDragging(false);
    },
    onDrop: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      upload(Array.from(e.dataTransfer.files));
    },
  };

  const confirmDelete = () => {
    const d = confirm;
    setConfirm(null);
    if (d) del.mutate(d.id, { onSuccess: () => toast.success(`Deleted ${d.filename}`) });
  };

  const ask = (d: DocumentInfo) => navigate("/", { state: { fresh: true, attachDoc: d } satisfies NewChatState });

  const empty = docs.isSuccess && (docs.data?.length ?? 0) === 0 && uploading.length === 0;

  return (
    <Page
      {...dragProps}
      header={
        <PageHeader
          icon={FileText}
          title="Documents"
          subtitle="Statements, balance sheets, invoices and policies Sphura reads, searches and cites by page — scans go through OCR."
          action={
            <Button onClick={() => inputRef.current?.click()}>
              <Upload /> Upload files
            </Button>
          }
        />
      }
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          upload(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />

      {!empty && (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex w-full flex-col items-center gap-1 rounded-xl border border-dashed border-input bg-card/50 px-4 py-6 text-center transition-colors hover:border-foreground/25 hover:bg-card focus-visible:outline-2 active:scale-[0.995] motion-reduce:active:scale-100"
        >
          <CloudUpload className="size-5 text-muted-foreground" strokeWidth={1.75} />
          <span className="text-sm font-medium">Drop files here or click to browse</span>
          <span className="text-xs text-muted-foreground">PDF, DOCX, TXT, MD, CSV, XLSX, JSON, HTML, PNG, JPG, WEBP</span>
        </button>
      )}

      {docs.isPending ? (
        <div className="mt-6 space-y-2.5" aria-busy="true" aria-label="Loading documents">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-4 rounded-xl border bg-card p-4">
              <Skeleton className="size-11 rounded-lg" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-3 w-1/3" />
              </div>
            </div>
          ))}
        </div>
      ) : docs.isError && !docs.data ? (
        <div className="mt-10 text-center text-sm text-muted-foreground">
          {errorMessage(docs.error)}{" "}
          <button type="button" className="underline underline-offset-2" onClick={() => void docs.refetch()}>
            Retry
          </button>
        </div>
      ) : empty ? (
        <EmptyState
          icon={glyph("documents")}
          title="No documents yet"
          action={
            <Button onClick={() => inputRef.current?.click()}>
              <Upload /> Upload your first file
            </Button>
          }
          footnote="Or drag and drop anywhere on this page. A bank statement exported as CSV or Excel works best: date, description and amount columns are enough."
        >
          Upload a bank statement, a balance sheet, an invoice or a policy. Sphura indexes it so you can ask questions and get answers with
          page-level citations. CSV and Excel statements also power the dashboard.
        </EmptyState>
      ) : (
        <>
          <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {stats.total} document{stats.total === 1 ? "" : "s"} · {stats.ready} ready · {formatBytes(stats.bytes)}
            </p>
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="search"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter by name"
                aria-label="Filter documents"
                className="h-8 w-full rounded-lg border bg-card pr-3 pl-8 text-sm outline-none focus:border-ring/60 focus:ring-3 focus:ring-ring/20"
              />
            </div>
          </div>
          <ul className="mt-3 space-y-2.5">
              {uploading.map((u) => (
                <li key={u.id} className="flex items-center gap-4 rounded-xl border border-dashed bg-card/60 p-4">
                  <FileIcon name={u.name} size="lg" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{u.name}</div>
                    <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                      <LoaderCircle className="size-3 animate-spin" /> Uploading · {formatBytes(u.size)}
                    </div>
                  </div>
                </li>
              ))}
              <AnimatePresence>
                {list.map((d, i) => (
                  <DocRow
                    key={d.id}
                    doc={d}
                    index={i}
                    onAsk={() => ask(d)}
                    onDashboard={isTabularDoc(d) ? () => navigate(`/dashboard?doc=${encodeURIComponent(d.id)}`) : undefined}
                    onDelete={() => setConfirm(d)}
                  />
                ))}
              </AnimatePresence>
              {list.length === 0 && filter && (
                <li className="py-8 text-center text-sm text-muted-foreground">No documents match “{filter}”.</li>
              )}
          </ul>
        </>
      )}

      <AnimatePresence>
        {dragging && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="pointer-events-none absolute inset-3 z-40 grid place-items-center rounded-2xl border-2 border-dashed border-ring/50 bg-background/90 backdrop-blur-sm"
          >
            <motion.div initial={{ scale: 0.97, y: 4 }} animate={{ scale: 1, y: 0 }} transition={{ duration: 0.2, ease: EASE_OUT }} className="text-center">
              <CloudUpload className="mx-auto size-8 text-brand" strokeWidth={1.75} />
              <p className="mt-3 font-brand text-2xl font-normal">Drop to upload</p>
              <p className="mt-1 text-sm text-muted-foreground">Sphura will read and index them for you.</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AlertDialog open={!!confirm} onOpenChange={(open) => !open && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this document?</AlertDialogTitle>
            <AlertDialogDescription>
              “{confirm?.filename}” and its search index will be permanently removed. Chats that cited it keep their text.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Page>
  );
}
