import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpen,
  Brain,
  Calculator,
  ChartCandlestick,
  Check,
  ChevronRight,
  CircleAlert,
  GitMerge,
  Globe,
  Library,
  LoaderCircle,
  Newspaper,
  Route,
  ShieldCheck,
  Table2,
  Wrench,
} from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useNow } from "@/hooks/use-now";
import { formatDuration, stepsDurationMs } from "@/lib/format";
import type { Phase, ToolStep } from "@/lib/types";
import { cn } from "@/lib/utils";

const PHASE_LABEL: Record<Phase, string> = {
  thinking: "Understanding your question",
  searching: "Fetching market data",
  reading: "Reading your documents",
  analyzing: "Crunching the numbers",
  composing: "Writing the answer",
};

/** Live agent status ("Crunching your statements…") with a shimmer. */
export function StatusLine({ phase, label }: { phase: Phase | null; label: string | null }) {
  const text = (label || PHASE_LABEL[phase ?? "thinking"]).replace(/[.…]+$/, "");
  return (
    <div className="flex h-7 items-center overflow-hidden" role="status" aria-live="polite">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={text}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.22, ease: "easeOut" }}
          className="shimmer-text truncate text-[0.94rem] font-medium"
        >
          {text}…
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

interface StepKind {
  icon: typeof Globe;
  /** Fallback label when the server sent none. */
  label: string;
  /** Summary fragment for one occurrence / for `#` occurrences. */
  one: string;
  many: string;
}

const ROUTER: StepKind = { icon: Route, label: "Routed the question", one: "Routed", many: "Routed" };
const ANALYTICS: StepKind = { icon: Table2, label: "Crunched your statements", one: "Crunched your statements", many: "Crunched your statements" };
const DOCUMENTS: StepKind = { icon: Library, label: "Searched your documents", one: "Searched your documents", many: "Searched your documents #×" };
const MARKET: StepKind = { icon: ChartCandlestick, label: "Fetched market data", one: "Fetched market data", many: "Fetched market data #×" };
const CALC: StepKind = { icon: Calculator, label: "Ran a calculation", one: "Ran 1 calculation", many: "Ran # calculations" };
const ENSEMBLE: StepKind = { icon: GitMerge, label: "Asking 3 models", one: "Asked 1 model", many: "Asked # models" };
const MERGE: StepKind = { icon: GitMerge, label: "Merging the answers", one: "Merged", many: "Merged" };
/** Steps that only frame others (the ensemble's own row); they don't count in the summary line. */
const SUMMARY_SKIP = new Set(["ensemble"]);

/**
 * Finance graph steps (FINANCE_PLAN §3: node names, the market/calculator tools, CONTRACT step names) + the shared
 * web tools. Several names map to one kind so the summary reads "Fetched market data ×2", not "Used 2 tools".
 */
const STEP_KIND: Record<string, StepKind> = {
  ensemble: ENSEMBLE,
  ensemble_member: ENSEMBLE,
  ensemble_merge: MERGE,
  router: ROUTER,
  classify: ROUTER,
  memory_recall: { icon: Brain, label: "Recalled memories", one: "Recalled memories", many: "Recalled memories" },
  analytics: ANALYTICS,
  finance_analyze: ANALYTICS,
  search_documents: DOCUMENTS,
  retrieve: DOCUMENTS,
  market: MARKET,
  get_quote: MARKET,
  get_history: MARKET,
  fx_rate: MARKET,
  finance_news: { icon: Newspaper, label: "Read finance news", one: "Read finance news", many: "Read finance news #×" },
  web_search: { icon: Globe, label: "Searched the web", one: "Searched the web", many: "Searched the web #×" },
  read_page: { icon: BookOpen, label: "Read a page", one: "Read 1 page", many: "Read # pages" },
  emi: CALC,
  sip_future_value: CALC,
  fd_rd_maturity: CALC,
  income_tax_estimate: CALC,
  ratio_calculator: CALC,
  verify: { icon: ShieldCheck, label: "Checked claims against sources", one: "Checked claims", many: "Checked claims" },
};

const ACCENT_STEPS = new Set(["router", "classify", "verify"]);

function StepIcon({ step }: { step: ToolStep }) {
  if (step.status === "running") return <LoaderCircle className="size-3.5 animate-spin text-primary" />;
  if (step.status === "error") return <CircleAlert className="size-3.5 text-destructive" />;
  return <Check className="size-3.5 text-success" />;
}

function stepDuration(step: ToolStep, now: number): string {
  const start = new Date(step.startedAt).getTime();
  const end = step.finishedAt ? new Date(step.finishedAt).getTime() : now;
  const ms = end - start;
  return Number.isFinite(ms) && (ms >= 100 || step.status === "running") ? formatDuration(Math.max(0, ms)) : "";
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many.replace("#", String(n)));

/** "Routed · Crunched your statements · Fetched market data ×2 · Checked claims" (kinds in order of first use). */
function summarize(steps: ToolStep[]): string {
  const counts = new Map<StepKind, number>();
  let other = 0;
  for (const s of steps) {
    if (SUMMARY_SKIP.has(s.name)) continue;
    const kind = STEP_KIND[s.name];
    if (kind) counts.set(kind, (counts.get(kind) ?? 0) + 1);
    else other += 1;
  }
  const parts = [...counts].map(([kind, n]) => plural(n, kind.one, kind.many));
  if (other) parts.push(plural(other, "Used 1 tool", "Used # tools"));
  return parts.join(" · ");
}

/** "answered in 2.1 s" → "2.1 s" (anything else is left out of the chip; the full detail is its tooltip). */
function latencyOf(step: ToolStep): string {
  const d = step.detail?.trim() ?? "";
  const m = /(\d+(?:\.\d+)?\s*m?s)\b/.exec(d);
  return m ? m[1].replace(/\s+/, " ") : "";
}

/** The ensemble at a glance: one chip per model with its latency, then the merge. */
function EnsembleStrip({ steps }: { steps: ToolStep[] }) {
  const members = steps.filter((s) => s.name === "ensemble_member");
  const merge = steps.find((s) => s.name === "ensemble_merge");
  const asking = steps.find((s) => s.name === "ensemble");
  if (members.length === 0 && !asking) return null;
  return (
    <div className="mb-2.5 flex flex-wrap items-center gap-1.5" role="list" aria-label="Models asked">
      {members.length === 0 && asking && (
        <span role="listitem" className="inline-flex h-7 items-center gap-1.5 rounded-full border bg-card/70 px-2.5 text-[12px] text-muted-foreground">
          <LoaderCircle className="size-3.5 animate-spin text-brand" /> {asking.label || "Asking 3 models"}
        </span>
      )}
      {members.map((m, i) => {
        const latency = latencyOf(m);
        return (
          <motion.span
            key={m.id}
            role="listitem"
            initial={{ opacity: 0, y: 4, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.2, delay: i * 0.05 }}
            title={m.detail ?? undefined}
            className={cn(
              "inline-flex h-7 max-w-full items-center gap-1.5 rounded-full border px-2.5 text-[12px]",
              m.status === "error" ? "border-destructive/30 text-muted-foreground" : "bg-card/70 text-foreground/90",
            )}
          >
            <StepIcon step={m} />
            <span className="truncate">{m.label}</span>
            {m.status === "error" ? (
              <span className="shrink-0 text-destructive">failed</span>
            ) : latency ? (
              <span className="shrink-0 text-muted-foreground tabular-nums">{latency}</span>
            ) : null}
          </motion.span>
        );
      })}
      {merge && (
        <motion.span
          role="listitem"
          initial={{ opacity: 0, x: -4 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.2 }}
          className="inline-flex h-7 items-center gap-1.5 rounded-full bg-accent px-2.5 text-[12px] font-medium text-foreground"
        >
          <span aria-hidden className="text-muted-foreground">→</span>
          {merge.status === "running" ? <LoaderCircle className="size-3.5 animate-spin text-brand" /> : <GitMerge className="size-3.5 text-brand" />}
          {merge.status === "running" ? "Merging" : merge.status === "error" ? "Merge failed" : "Merged"}
        </motion.span>
      )}
    </div>
  );
}

/** Collapsible agent trace: "Routed · Crunched your statements · 4 s". */
export function StepsTimeline({ steps, live }: { steps: ToolStep[]; live: boolean }) {
  const [open, setOpen] = useState(false);
  const running = steps.find((s) => s.status === "running");
  const now = useNow(live && !!running);
  if (steps.length === 0) return null;

  const summary = summarize(steps);
  const ms = stepsDurationMs(steps, now);
  const duration = ms >= 100 ? formatDuration(ms) : "";
  const runningLabel = running ? running.label || STEP_KIND[running.name]?.label || running.name : "";

  return (
    <>
    <EnsembleStrip steps={steps} />
    <Collapsible open={open} onOpenChange={setOpen} className="mb-3">
      <CollapsibleTrigger
        className="group/steps flex max-w-full items-center gap-1.5 rounded-full border bg-card/70 py-1 pr-2 pl-2.5 text-left text-[12.5px] text-muted-foreground shadow-xs transition-[color,background-color,border-color,transform] hover:border-brand/25 hover:bg-card hover:text-foreground active:scale-[0.98] data-[state=open]:bg-card data-[state=open]:text-foreground motion-reduce:active:scale-100"
        aria-label={open ? "Hide steps" : "Show steps"}
      >
        {running ? <LoaderCircle className="size-3.5 shrink-0 animate-spin text-primary" /> : <Wrench className="size-3.5 shrink-0" />}
        <span className="truncate">{running && live ? runningLabel : summary}</span>
        {duration && <span className="shrink-0 tabular-nums opacity-70">· {duration}</span>}
        <ChevronRight className={cn("size-3.5 shrink-0 transition-transform duration-200", open && "rotate-90")} />
      </CollapsibleTrigger>
      <CollapsibleContent className="overflow-hidden data-closed:animate-collapsible-up data-open:animate-collapsible-down">
        <ol className="relative mt-2.5 ml-3 space-y-2.5 border-l border-border pl-4">
          {steps.map((step) => {
            const kind = STEP_KIND[step.name];
            const Icon = kind?.icon ?? Wrench;
            return (
              <li key={step.id} className="relative text-[13px]">
                <span className="absolute top-0.5 -left-[1.4rem] grid size-4 place-items-center rounded-full bg-background">
                  <StepIcon step={step} />
                </span>
                <div className="flex items-start gap-2">
                  <Icon className={cn("mt-0.5 size-3.5 shrink-0", ACCENT_STEPS.has(step.name) ? "text-brand" : "text-muted-foreground")} />
                  <div className="min-w-0 flex-1">
                    <div className="leading-snug text-foreground/90">{step.label || kind?.label || step.name}</div>
                    {step.detail && (
                      <div className={cn("mt-0.5 text-xs break-words", step.status === "error" ? "text-destructive" : "text-muted-foreground")}>
                        {step.detail}
                      </div>
                    )}
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{stepDuration(step, now)}</span>
                </div>
              </li>
            );
          })}
        </ol>
      </CollapsibleContent>
    </Collapsible>
    </>
  );
}
