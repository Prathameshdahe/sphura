import { useMemo, type CSSProperties } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { FileSearch, Lightbulb, Trophy } from "lucide-react";
import { TooltipRow } from "@/components/metrics/chart-bits";
import { CHART_ANIM, SERIES, seriesConfig } from "@/components/metrics/chart-palette";
import { dec, int, ms, pct, pp } from "@/components/metrics/fmt";
import { ErrorState, NotAvailable, Panel, PanelHeader, Section, SectionSkeleton } from "@/components/metrics/section";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { RagEvalConfig, RagEvalReport } from "@/lib/feature-types";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const RECALL = [
  ["recallAt1", "Recall@1"],
  ["recallAt3", "Recall@3"],
  ["recallAt5", "Recall@5"],
  ["recallAt10", "Recall@10"],
] as const;

type MetricKey = keyof Omit<RagEvalConfig, "name">;

const COLUMNS: { key: MetricKey; label: string; better: "max" | "min"; fmt: (v: number) => string }[] = [
  { key: "recallAt1", label: "R@1", better: "max", fmt: (v) => pct(v) },
  { key: "recallAt3", label: "R@3", better: "max", fmt: (v) => pct(v) },
  { key: "recallAt5", label: "R@5", better: "max", fmt: (v) => pct(v) },
  { key: "recallAt10", label: "R@10", better: "max", fmt: (v) => pct(v) },
  { key: "mrr", label: "MRR", better: "max", fmt: (v) => dec(v) },
  { key: "ndcg10", label: "nDCG@10", better: "max", fmt: (v) => dec(v) },
  { key: "latencyMsP50", label: "p50", better: "min", fmt: (v) => ms(v) },
  { key: "latencyMsP95", label: "p95", better: "min", fmt: (v) => ms(v) },
];

const swatch = (i: number) =>
  ({ "--sw-l": SERIES[i]?.light ?? "#888", "--sw-d": SERIES[i]?.dark ?? "#888" }) as CSSProperties;

function RecallChart({ configs }: { configs: RagEvalConfig[] }) {
  const shown = useMemo(() => configs.slice(0, SERIES.length), [configs]);
  const config = useMemo(() => seriesConfig(shown.map((c, i) => ({ key: `c${i}`, label: c.name, color: SERIES[i] }))), [shown]);
  const data = RECALL.map(([k, label]) => {
    const row: Record<string, string | number> = { metric: label };
    shown.forEach((c, i) => (row[`c${i}`] = c[k]));
    return row;
  });
  return (
    <ChartContainer config={config} className="aspect-auto h-72 w-full sm:h-80" role="img" aria-label="Grouped bar chart of Recall at 1, 3, 5 and 10 for each retrieval configuration. Exact values are in the table below.">
      <BarChart data={data} barGap={2} barCategoryGap="20%" margin={{ top: 8, right: 4, left: -12, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="metric" tickLine={false} axisLine={false} tickMargin={8} />
        <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v: number) => pct(v, 0)} tickLine={false} axisLine={false} width={48} />
        <ChartTooltip
          cursor={{ fillOpacity: 0.5 }}
          content={
            <ChartTooltipContent
              formatter={(value, name, item) => (
                <TooltipRow color={item.color} label={config[String(name)]?.label ?? String(name)} value={pct(Number(value))} />
              )}
            />
          }
        />
        <ChartLegend itemSorter={null} content={<ChartLegendContent className="flex-wrap gap-x-4 gap-y-1.5" />} />
        {shown.map((_, i) => (
          <Bar key={i} dataKey={`c${i}`} fill={`var(--color-c${i})`} radius={[4, 4, 0, 0]} maxBarSize={30} {...CHART_ANIM} />
        ))}
      </BarChart>
    </ChartContainer>
  );
}

function MetricsTable({ configs }: { configs: RagEvalConfig[] }) {
  const best = Object.fromEntries(
    COLUMNS.map((c) => {
      const vals = configs.map((x) => x[c.key]).filter((v) => Number.isFinite(v));
      return [c.key, vals.length ? (c.better === "max" ? Math.max(...vals) : Math.min(...vals)) : NaN];
    }),
  ) as Record<MetricKey, number>;
  return (
    <div className="scrollbar-thin relative overflow-x-auto">
      <table className="w-full min-w-[40rem] text-sm">
        <caption className="sr-only">Retrieval metrics per configuration; the best value in each column is highlighted.</caption>
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th scope="col" className="sticky left-0 z-[1] bg-card py-2 pr-3 text-left font-medium">Configuration</th>
            {COLUMNS.map((c) => (
              <th key={c.key} scope="col" className="px-2 py-2 text-right font-medium whitespace-nowrap">
                {c.label}
                {c.key.startsWith("latency") && <span className="sr-only"> latency</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {configs.map((cfg, i) => (
            <tr key={cfg.name} className="border-b border-border/60 last:border-0">
              <th scope="row" className="sticky left-0 z-[1] max-w-[11rem] bg-card py-2.5 pr-3 text-left font-medium sm:max-w-none">
                <span className="flex items-center gap-2">
                  <span className="size-2.5 shrink-0 rounded-[2px] bg-(--sw-l) dark:bg-(--sw-d)" style={swatch(i)} aria-hidden />
                  {cfg.name}
                </span>
              </th>
              {COLUMNS.map((c) => {
                const isBest = cfg[c.key] === best[c.key];
                return (
                  <td key={c.key} className="px-1 py-2 text-right whitespace-nowrap tabular-nums">
                    <span className={cn("inline-block rounded-md px-1.5 py-0.5", isBest ? "bg-success/12 font-semibold text-success" : "text-foreground/85")}>
                      {c.fmt(cfg[c.key])}
                      {isBest && <span className="sr-only"> (best)</span>}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface RagSectionProps {
  report: RagEvalReport | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}

/** 03 · Retrieval evaluation: Recall@k / MRR / nDCG / latency across the four pipelines (ModelLabReport.ragEval). */
export function RagSection({ report: r, loading, error, onRetry }: RagSectionProps) {
  const configs = useMemo(() => r?.configs ?? [], [r]);

  const winner = useMemo(() => {
    if (configs.length < 2) return null;
    const top = configs.reduce((a, b) => (b.ndcg10 > a.ndcg10 ? b : a));
    const base = configs[0];
    return { top, base, lift: top.recallAt5 - base.recallAt5 };
  }, [configs]);

  return (
    <Section
      id="retrieval"
      icon={FileSearch}
      eyebrow="03 · Retrieval"
      title="RAG retrieval evaluation"
      description="How often the passage that answers a question is retrieved — measured on a labelled question set and compared across keyword, dense, hybrid and re-ranked pipelines."
    >
      {loading ? (
        <SectionSkeleton tiles={0} />
      ) : error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : !r?.available || configs.length === 0 ? (
        <NotAvailable
          title="No evaluation run yet"
          description="Run the benchmark once from the backend folder. It indexes a small labelled corpus, scores every retrieval pipeline and saves the report that appears here."
          commands={["cd backend", "python -m ml.eval_rag"]}
        />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
            <Panel className="p-4 sm:p-5">
              <div className="text-xs font-medium text-muted-foreground">Dataset</div>
              <div className="mt-1 font-brand text-lg leading-snug">{r.dataset?.name ?? "Labelled questions"}</div>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
                {[
                  ["documents", r.dataset?.documents],
                  ["chunks", r.dataset?.chunks],
                  ["questions", r.dataset?.questions],
                ].map(([k, v]) => (
                  <div key={k as string} className="rounded-lg bg-muted/50 px-2 py-2">
                    <dd className="font-mono text-base font-medium tabular-nums">{int(v as number | undefined)}</dd>
                    <dt className="text-[11px] text-muted-foreground">{k as string}</dt>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-xs text-muted-foreground">
                {r.k ? <>Top-{r.k} retrieval · </> : null}
                {r.runAt ? <>run {formatRelative(r.runAt)}</> : "latest saved run"}
              </p>
            </Panel>
            {winner && (
              <Panel className="relative overflow-hidden p-4 sm:p-5">
                <div className="relative flex h-full flex-col justify-between gap-3">
                  <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                    <Trophy className="size-3.5 text-brand" aria-hidden /> Best pipeline (by nDCG@10)
                  </div>
                  <div>
                    <div className="font-brand text-2xl leading-tight font-normal">{winner.top.name}</div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Recall@5 <span className="font-medium text-foreground tabular-nums">{pct(winner.top.recallAt5)}</span>
                      {winner.top.name !== winner.base.name && (
                        <>
                          {" "}vs {pct(winner.base.recallAt5)} for {winner.base.name}{" "}
                          <span className="font-medium text-success tabular-nums">({pp(winner.lift)})</span>
                        </>
                      )}
                      {" · "}MRR <span className="font-medium text-foreground tabular-nums">{dec(winner.top.mrr)}</span>
                      {" · "}p50 {ms(winner.top.latencyMsP50)}
                    </p>
                  </div>
                </div>
              </Panel>
            )}
          </div>

          <Panel>
            <PanelHeader title="Recall@k by configuration" description="Share of questions whose gold passage appears in the top k results." />
            <div className="px-2 pt-4 pb-3 sm:px-4">
              <RecallChart configs={configs} />
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Ranking quality and latency" description="Best value per column highlighted · latency per query (p50 / p95)." />
            <div className="px-4 pt-2 pb-3 sm:px-5">
              <MetricsTable configs={configs} />
            </div>
          </Panel>

          {r.notes && r.notes.length > 0 && (
            <Panel className="p-4 sm:p-5">
              <h3 className="text-sm font-semibold">Notes</h3>
              <ul className="mt-2 space-y-1.5">
                {r.notes.map((n, i) => (
                  <li key={i} className="flex gap-2 text-sm text-muted-foreground">
                    <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                    <span>{n}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      )}
    </Section>
  );
}
