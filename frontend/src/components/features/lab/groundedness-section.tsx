import { useMemo } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { MessageSquareText, ShieldAlert, ShieldCheck, ShieldHalf, ShieldQuestionMark, ShieldX, type LucideIcon } from "lucide-react";
import { TooltipRow } from "@/components/metrics/chart-bits";
import { CHART_ANIM, SLATE, seriesConfig } from "@/components/metrics/chart-palette";
import { int, pct } from "@/components/metrics/fmt";
import { ErrorState, Panel, PanelHeader, Section, SectionSkeleton } from "@/components/metrics/section";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { useVerificationStats } from "@/lib/feature-api/ml";
import type { VerificationStats } from "@/lib/feature-types";
import { cn } from "@/lib/utils";

/** Verdict labels (Verification.label) in severity order; status colours ship with an icon + text. */
const LABELS: { key: string; title: string; icon: LucideIcon; bar: string; text: string }[] = [
  { key: "grounded", title: "Grounded", icon: ShieldCheck, bar: "bg-success", text: "text-success" },
  { key: "mostly grounded", title: "Mostly grounded", icon: ShieldHalf, bar: "bg-success/60", text: "text-success" },
  { key: "partially grounded", title: "Partially grounded", icon: ShieldAlert, bar: "bg-warning", text: "text-warning" },
  { key: "ungrounded", title: "Ungrounded", icon: ShieldX, bar: "bg-danger", text: "text-danger" },
  { key: "not checkable", title: "Not checkable", icon: ShieldQuestionMark, bar: "bg-muted-foreground/40", text: "text-muted-foreground" },
];

function Gauge({ score, answers }: { score: number | null; answers: number }) {
  const v = score == null ? 0 : Math.min(1, Math.max(0, score));
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(v * 100)}
      aria-label="Average groundedness score"
      className="relative mx-auto w-full max-w-[15rem]"
    >
      <svg viewBox="0 0 200 116" className="w-full" aria-hidden>
        <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="var(--muted)" strokeWidth="14" strokeLinecap="round" />
        <motion.path
          d="M 20 100 A 80 80 0 0 1 180 100"
          fill="none"
          stroke="var(--primary)"
          strokeWidth="14"
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          whileInView={{ pathLength: Math.max(0.001, v) }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className="font-brand text-4xl font-normal tracking-[-0.015em] tabular-nums">{score == null ? "–" : pct(score, 0)}</div>
        <div className="text-xs text-muted-foreground">
          average over {int(answers)} answer{answers === 1 ? "" : "s"}
        </div>
      </div>
    </div>
  );
}

function LabelDistribution({ counts }: { counts: Record<string, number> }) {
  const known = new Set(LABELS.map((l) => l.key));
  const rows = [
    ...LABELS.map((l) => ({ ...l, count: counts[l.key] ?? 0 })),
    ...Object.entries(counts)
      .filter(([k]) => !known.has(k))
      .map(([k, count]) => ({ key: k, title: k, icon: ShieldQuestionMark, bar: "bg-muted-foreground/40", text: "text-muted-foreground", count })),
  ];
  const total = rows.reduce((n, r) => n + r.count, 0) || 1;
  return (
    <div>
      <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-muted" aria-hidden>
        {rows
          .filter((r) => r.count > 0)
          .map((r) => (
            <motion.div
              key={r.key}
              className={cn("h-full first:rounded-l-full last:rounded-r-full", r.bar)}
              initial={{ width: 0 }}
              whileInView={{ width: `${(r.count / total) * 100}%` }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, ease: "easeOut" }}
            />
          ))}
      </div>
      <ul className="mt-4 space-y-2">
        {rows.map((r) => {
          const Icon = r.icon;
          return (
            <li key={r.key} className="flex items-center gap-2.5 text-sm">
              <Icon className={cn("size-4 shrink-0", r.text)} aria-hidden />
              <span className="flex-1 truncate">{r.title}</span>
              <span className="font-mono text-xs text-muted-foreground tabular-nums">{pct(r.count / total, 0)}</span>
              <span className="w-8 text-right font-mono text-sm font-medium tabular-nums">{int(r.count)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Histogram({ data }: { data: VerificationStats["histogram"] }) {
  const config = useMemo(() => seriesConfig([{ key: "count", label: "Answers", color: SLATE }]), []);
  return (
    <ChartContainer config={config} className="aspect-auto h-56 w-full" role="img" aria-label="Histogram of answer groundedness scores">
      <BarChart data={data} margin={{ top: 8, right: 4, left: -8, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="bucket" tickLine={false} axisLine={false} tickMargin={8} interval="preserveStartEnd" />
        <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={40} />
        <ChartTooltip
          cursor={{ fillOpacity: 0.5 }}
          content={
            <ChartTooltipContent
              formatter={(value, _name, item) => <TooltipRow color={item.color} label="Answers" value={int(Number(value))} />}
            />
          }
        />
        <Bar dataKey="count" fill="var(--color-count)" radius={[4, 4, 0, 0]} maxBarSize={44} {...CHART_ANIM} />
      </BarChart>
    </ChartContainer>
  );
}

/** 04 · Hallucination meter: NLI groundedness of the user's cited answers (GET /api/ml/verification). */
export function HallucinationSection() {
  const stats = useVerificationStats();
  const s = stats.data;
  return (
    <Section
      id="verification"
      icon={ShieldCheck}
      eyebrow="04 · Verification"
      title="Hallucination meter"
      description="Each cited answer is split into sentences and checked against its sources with a natural-language-inference model (always local): does the cited passage actually entail the claim?"
    >
      {stats.isPending ? (
        <SectionSkeleton tiles={0} />
      ) : stats.isError ? (
        <ErrorState error={stats.error} onRetry={() => void stats.refetch()} />
      ) : !s || s.answers === 0 ? (
        <Panel className="flex flex-col items-center gap-2 px-6 py-10 text-center">
          <span className="grid size-10 place-items-center rounded-xl border bg-muted/60 text-muted-foreground" aria-hidden>
            <ShieldCheck className="size-[18px]" strokeWidth={1.75} />
          </span>
          <h3 className="mt-2 font-brand text-xl font-normal">No verified answers yet</h3>
          <p className="max-w-md text-sm text-muted-foreground">
            Ask about a document, a statement or a stock. Sphura verifies every cited answer and the scores collect here.
          </p>
          <Button asChild variant="outline" size="sm" className="mt-2">
            <Link to="/" state={{ fresh: true }}>
              <MessageSquareText /> Ask a question
            </Link>
          </Button>
        </Panel>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1fr)_minmax(0,1.3fr)]">
          <Panel className="flex flex-col p-4 sm:p-5">
            <h3 className="text-sm font-semibold">Average groundedness</h3>
            <p className="text-xs text-muted-foreground">Share of checkable claims supported by their citation.</p>
            <div className="flex flex-1 items-center py-4">
              <Gauge score={s.avgScore} answers={s.answers} />
            </div>
          </Panel>
          <Panel className="p-4 sm:p-5">
            <h3 className="text-sm font-semibold">Verdicts</h3>
            <p className="mb-4 text-xs text-muted-foreground">How each answer was labelled.</p>
            <LabelDistribution counts={s.labelCounts} />
          </Panel>
          <Panel>
            <PanelHeader title="Score distribution" description="Number of answers per groundedness bucket." />
            <div className="px-2 pt-4 pb-3 sm:px-4">
              {s.histogram.length > 0 ? (
                <Histogram data={s.histogram} />
              ) : (
                <p className="py-12 text-center text-sm text-muted-foreground">Not enough answers for a histogram yet.</p>
              )}
            </div>
          </Panel>
        </div>
      )}
    </Section>
  );
}
