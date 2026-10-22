import { CircleAlert, CircleCheck, FileSpreadsheet, LoaderCircle, Upload } from "lucide-react";
import { FileIcon } from "@/components/file-icon";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes, formatRelative } from "@/lib/format";
import type { DocumentInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

interface DocPickerProps {
  docs: DocumentInfo[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** Opens the page's file picker (the Dashboard owns the <input type="file">). */
  onUploadClick: () => void;
  uploading: boolean;
}

function StatusLine({ doc }: { doc: DocumentInfo }) {
  if (doc.status === "ready")
    return (
      <span className="inline-flex items-center gap-1 text-success">
        <CircleCheck className="size-3" aria-hidden /> Ready
      </span>
    );
  if (doc.status === "error")
    return (
      <span className="inline-flex items-center gap-1 text-destructive">
        <CircleAlert className="size-3" aria-hidden /> {doc.error || "Failed"}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-warning">
      <LoaderCircle className="size-3 animate-spin" aria-hidden /> {doc.status === "queued" ? "Queued" : "Processing"}
    </span>
  );
}

/** Pick a CSV/XLSX statement (native radios → arrow-key navigation) or upload a new one. */
export function DocPicker({ docs, loading, selectedId, onSelect, onUploadClick, uploading }: DocPickerProps) {
  return (
    <div>
      {loading ? (
        <div className="grid gap-2 sm:grid-cols-2" aria-busy="true" aria-label="Loading documents">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-16 rounded-xl" />
          ))}
        </div>
      ) : docs.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-input px-4 py-8 text-center">
          <FileSpreadsheet className="size-6 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          <p className="text-sm font-medium">No statements yet</p>
          <p className="max-w-sm text-xs text-muted-foreground">Upload a bank statement or balance sheet as CSV or Excel.</p>
          <Button className="mt-2" onClick={onUploadClick} disabled={uploading}>
            {uploading ? <LoaderCircle className="animate-spin" /> : <Upload />} Upload a statement
          </Button>
        </div>
      ) : (
        <fieldset>
          <legend className="sr-only">Statement to analyse</legend>
          <div className="scrollbar-thin grid max-h-72 gap-2 overflow-y-auto p-0.5 sm:grid-cols-2">
            {docs.map((d) => {
              const checked = d.id === selectedId;
              const disabled = d.status === "error";
              return (
                <label
                  key={d.id}
                  className={cn(
                    "relative flex min-w-0 cursor-pointer items-center gap-3 rounded-xl border bg-card p-3 transition-[background-color,border-color,transform] duration-150 active:scale-[0.99] has-focus-visible:ring-3 has-focus-visible:ring-ring/30 motion-reduce:active:scale-100",
                    checked ? "border-brand/45 bg-brand/[0.04]" : "hover:border-foreground/20",
                    disabled && "cursor-not-allowed opacity-60",
                  )}
                >
                  <input
                    type="radio"
                    name="finance-doc"
                    value={d.id}
                    checked={checked}
                    disabled={disabled}
                    onChange={() => onSelect(d.id)}
                    className="sr-only"
                  />
                  <FileIcon name={d.filename} mime={d.mimeType} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium" title={d.filename}>
                      {d.filename}
                    </span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
                      <StatusLine doc={d} />
                      <span aria-hidden>·</span>
                      <span>{formatBytes(d.sizeBytes)}</span>
                      <span aria-hidden>·</span>
                      <span>{formatRelative(d.createdAt)}</span>
                    </span>
                  </span>
                  <span
                    className={cn(
                      "grid size-4 shrink-0 place-items-center rounded-full border-2 transition-colors",
                      checked ? "border-brand" : "border-muted-foreground/40",
                    )}
                    aria-hidden
                  >
                    {checked && <span className="size-1.5 rounded-full bg-brand" />}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        Export a statement from your bank's net banking as CSV or Excel: date, description and amount columns are enough. A balance
        sheet works too.
      </p>
    </div>
  );
}
