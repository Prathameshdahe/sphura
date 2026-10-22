import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ChartColumn, LayoutDashboard, LoaderCircle, Upload } from "lucide-react";
import { toast } from "sonner";
import { DocPicker } from "@/components/features/finance/doc-picker";
import { FinanceDashboard } from "@/components/features/finance/finance-dashboard";
import { FinanceSkeleton } from "@/components/features/finance/finance-skeleton";
import { Page } from "@/components/layout/page";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, ErrorState, Panel } from "@/components/metrics/section";
import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/lib/api";
import { TABULAR_ACCEPT, isTabularDoc, useFinanceReport } from "@/lib/feature-api/finance";
import type { FinanceReport, NewChatState } from "@/lib/feature-types";
import { qk, useDocuments } from "@/lib/queries";
import type { DocumentInfo } from "@/lib/types";
import { glyph } from "@/components/icons/glyphs";

const DISCUSS_PROMPT: Record<FinanceReport["kind"], string> = {
  bank_statement: "Analyse this statement: where is my money going, what recurs every month, and what should I watch?",
  balance_sheet: "Analyse this balance sheet: how healthy are liquidity and leverage, and what should I watch?",
  table: "Analyse this spreadsheet: what are the key figures and anything unusual?",
};

/** Dashboard: pick or upload a statement → deterministic analytics → discuss the numbers in chat. */
export default function Dashboard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const analyzedId = params.get("doc");
  const docs = useDocuments();
  const [picked, setPicked] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [autoId, setAutoId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = "Dashboard · Sphura";
    return () => {
      document.title = "Sphura";
    };
  }, []);

  const tabular = useMemo(() => (docs.data ?? []).filter(isTabularDoc), [docs.data]);
  const firstReady = tabular.find((d) => d.status === "ready")?.id ?? null;
  const selectedId = picked ?? analyzedId ?? firstReady;
  const selected = tabular.find((d) => d.id === selectedId) ?? null;

  const report = useFinanceReport(analyzedId);
  const reportDoc: DocumentInfo | null = useMemo(
    () => (report.data ? ((docs.data ?? []).find((d) => d.id === report.data.docId) ?? null) : null),
    [docs.data, report.data],
  );

  const analyze = (id: string) => {
    if (id === analyzedId) void report.refetch();
    else setParams({ doc: id }, { replace: false });
  };

  // An uploaded statement is analysed automatically once ingestion finishes.
  const handled = useRef<string | null>(null);
  useEffect(() => {
    if (!autoId || handled.current === autoId) return;
    const doc = tabular.find((d) => d.id === autoId);
    if (!doc) return;
    if (doc.status === "ready") {
      handled.current = autoId;
      setParams({ doc: autoId });
    } else if (doc.status === "error") {
      handled.current = autoId;
      toast.error(`${doc.filename}: ${doc.error || "processing failed"}`);
    }
  }, [autoId, tabular, setParams]);

  const upload = (file: File) => {
    if (!isTabularDoc({ filename: file.name })) {
      toast.error("The dashboard reads CSV or Excel files (.csv, .xlsx, .xls).");
      return;
    }
    setUploading(true);
    api
      .uploadDocument(file)
      .then((doc) => {
        qc.setQueryData<DocumentInfo[]>(qk.documents(undefined), (old) => (old ? [doc, ...old.filter((d) => d.id !== doc.id)] : [doc]));
        void qc.invalidateQueries({ queryKey: qk.documentsAll });
        setPicked(doc.id);
        setAutoId(doc.id);
        toast.success(`Uploaded ${doc.filename}`, { description: "Reading the file — the dashboard opens when it's ready." });
      })
      .catch((e: unknown) => toast.error(`${file.name}: ${errorMessage(e, "Upload failed")}`))
      .finally(() => setUploading(false));
  };

  const reportKind = report.data?.kind ?? "bank_statement";
  const discuss = reportDoc
    ? () =>
        navigate("/", {
          state: { fresh: true, attachDoc: reportDoc, prompt: DISCUSS_PROMPT[reportKind] } satisfies NewChatState,
        })
    : null;

  const waitingForUpload = !!selected && selected.id === autoId && (selected.status === "queued" || selected.status === "processing");
  const canAnalyze = !!selected && selected.status === "ready";
  const analyzing = report.isFetching;

  return (
    <Page
      header={
        <PageHeader
          icon={LayoutDashboard}
          title="Dashboard"
          subtitle="Cash flow, categories and ratios computed deterministically from your statements — then discussed in chat."
          action={
            <Button onClick={() => inputRef.current?.click()} disabled={uploading}>
              {uploading ? <LoaderCircle className="animate-spin" /> : <Upload />} Upload statement
            </Button>
          }
        />
      }
    >
      <input
        ref={inputRef}
        type="file"
        accept={TABULAR_ACCEPT}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload(f);
          e.target.value = "";
        }}
      />

      <Panel className="p-4 sm:p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">1 · Choose a statement</h2>
          <span className="text-xs text-muted-foreground">CSV, XLSX or XLS · bank statements and balance sheets</span>
        </div>
        {docs.isError && !docs.data ? (
          <ErrorState error={docs.error} onRetry={() => void docs.refetch()} className="border-0 shadow-none" />
        ) : (
          <DocPicker
            docs={tabular}
            loading={docs.isPending}
            selectedId={selectedId}
            onSelect={setPicked}
            onUploadClick={() => inputRef.current?.click()}
            uploading={uploading}
          />
        )}
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t pt-4">
          <Button size="lg" onClick={() => selected && analyze(selected.id)} disabled={!canAnalyze || analyzing}>
            {analyzing || waitingForUpload ? <LoaderCircle className="animate-spin" /> : <ChartColumn />}
            {waitingForUpload ? "Reading file…" : analyzing ? "Analysing…" : selected?.id === analyzedId && report.data ? "Analyse again" : "Analyse"}
          </Button>
          <span className="min-w-0 text-xs text-muted-foreground">
            {selected
              ? selected.status === "ready"
                ? `2 · Build the dashboard for ${selected.filename}`
                : selected.status === "error"
                  ? "This file failed to process — upload it again."
                  : "Waiting for the file to finish processing…"
              : "Pick or upload a file first."}
          </span>
        </div>
      </Panel>

      <div className="mt-6">
        {!analyzedId ? (
          <EmptyState icon={glyph("dashboard")} title="Your dashboard appears here">
            Inflow, outflow and net by month, where the money goes and the biggest transactions. For a balance sheet: current, quick
            and debt-to-equity ratios with plain-English verdicts.
          </EmptyState>
        ) : report.isPending ? (
          <FinanceSkeleton />
        ) : report.isError ? (
          <ErrorState error={report.error} onRetry={() => void report.refetch()} />
        ) : (
          <FinanceDashboard report={report.data} refreshing={report.isFetching} onRefresh={() => void report.refetch()} onDiscuss={discuss} />
        )}
      </div>
    </Page>
  );
}
