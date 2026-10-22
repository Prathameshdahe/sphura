import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { Cpu, Dumbbell, Gauge, Layers, Lightbulb, Scale, ShieldCheck, Timer } from "lucide-react";
import { TooltipRow } from "@/components/metrics/chart-bits";
import { ROSE, CHART_ANIM, OTHER, seriesConfig } from "@/components/metrics/chart-palette";
import { dec, int, pct, pp } from "@/components/metrics/fmt";
import { KpiCard, type KpiDelta } from "@/components/metrics/kpi-card";
import { ErrorState, NotAvailable, Panel, PanelHeader, Section, SectionSkeleton } from "@/components/metrics/section";
import { Badge } from "@/components/ui/badge";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { FinetuneReport } from "@/lib/feature-types";
import { cn } from "@/lib/utils";
import { WRAP_BADGE } from "./model-card";

const config = seriesConfig([
  { key: "base", label: "Base model", color: OTHER },
  { key: "tuned", label: "Fine-tuned", color: ROSE },
]);

/** Higher-is-better share metrics that exist for both models → grouped bars. */
function pairs(e: FinetuneReport["eval"]) {
  const rows = [
    { metric: "FinQA numeric EM", base: e.finqaEmBase, tuned: e.finqaEmTuned },
    { metric: "MMLU-mini", base: e.mmluMiniBase, tuned: e.mmluMiniTuned },
  ];
  return rows.filter((r) => r.base != null || r.tuned != null).map((r) => ({ metric: r.metric, base: r.base ?? 0, tuned: r.tuned ?? 0 }));
}

function shareDelta(base: number | null, tuned: number | null): KpiDelta | null {
  if (base == null || tuned == null) return null;
  const d = tuned - base;
  return { text: `${pp(d)} vs base`, direction: d > 0.0005 ? "up" : d < -0.0005 ? "down" : "flat", good: d >= 0 };
}

function perplexityDelta(base: number | null, tuned: number | null): KpiDelta | null {
  if (base == null || tuned == null || base === 0) return null;
  const rel = (tuned - base) / base;
  const sign = rel < 0 ? "−" : rel > 0 ? "+" : "±";
  return { text: `${sign}${Math.abs(rel * 100).toFixed(1)}% vs base ${dec(base, 2)}`, direction: rel < 0 ? "down" : rel > 0 ? "up" : "flat", good: rel <= 0 };
}

function BaseVsTuned({ data }: { data: { metric: string; base: number; tuned: number }[] }) {
  return (
    <ChartContainer config={config} className="aspect-auto h-64 w-full" role="img" aria-label="Base model versus fine-tuned model on each benchmark">
      <BarChart data={data} barGap={4} barCategoryGap="28%" margin={{ top: 8, right: 4, left: -12, bottom: 0 }}>
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
        <ChartLegend itemSorter={null} content={<ChartLegendContent />} />
        <Bar dataKey="base" fill="var(--color-base)" radius={[4, 4, 0, 0]} maxBarSize={40} {...CHART_ANIM} />
        <Bar dataKey="tuned" fill="var(--color-tuned)" radius={[4, 4, 0, 0]} maxBarSize={40} {...CHART_ANIM} />
      </BarChart>
    </ChartContainer>
  );
}

interface FinetuneSectionProps {
  finetune: FinetuneReport | null | undefined;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}

/** 02 · sphura-fin-1.7b: QLoRA fine-tune of Qwen3-1.7B, evaluated against its base model. */
export function FinetuneSection({ finetune: f, loading, error, onRetry }: FinetuneSectionProps) {
  const chart = useMemo(() => (f ? pairs(f.eval) : []), [f]);
  return (
    <Section
      id="finetune"
      icon={Dumbbell}
      eyebrow="02 · Fine-tune"
      title={f?.name ? f.name : "sphura-fin-1.7b"}
      description="A QLoRA supervised fine-tune of a small open model on finance instructions, reasoning paths and an Indian-finance QA set — compared with its untouched base on held-out data."
    >
      {loading ? (
        <SectionSkeleton />
      ) : error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : !f || !f.available ? (
        <NotAvailable
          title="Not trained yet"
          description={
            f?.notes?.length
              ? f.notes.join(" · ")
              : "Run the QLoRA job from the training/ folder (GPU, Ollama stopped). The evaluation report and the Ollama export land in backend/ml/artifacts and show up here."
          }
        />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="outline" className={cn(WRAP_BADGE, "font-mono")}>
              base: {f.base}
            </Badge>
            <Badge variant="outline" className={WRAP_BADGE}>
              {f.method}
            </Badge>
            {f.ollamaTag && (
              <Badge variant="outline" className={cn(WRAP_BADGE, "font-mono")}>
                ollama run {f.ollamaTag}
              </Badge>
            )}
            <Badge variant="outline" className={WRAP_BADGE}>
              LoRA r={f.lora.r} · α={f.lora.alpha} · {f.lora.targets.join(", ") || "all linear"}
            </Badge>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="Training rows" icon={Layers} value={f.rows} format={int} hint={`${int(f.steps)} optimiser steps · ${f.epochs} epoch${f.epochs === 1 ? "" : "s"}`} />
            <KpiCard label="Train time" icon={Timer} value={f.trainMinutes} format={(n) => `${n.toLocaleString(undefined, { maximumFractionDigits: 0 })} min`} hint={f.gpu} />
            <KpiCard
              label="Held-out perplexity"
              icon={Gauge}
              accent
              value={f.eval.heldoutPerplexityTuned ?? "—"}
              format={(n) => dec(n, 2)}
              delta={perplexityDelta(f.eval.heldoutPerplexityBase, f.eval.heldoutPerplexityTuned)}
              hint="lower is better"
            />
            <KpiCard
              label="FinQA numeric EM"
              icon={Scale}
              value={f.eval.finqaEmTuned ?? "—"}
              format={(n) => pct(n)}
              delta={shareDelta(f.eval.finqaEmBase, f.eval.finqaEmTuned)}
              hint="100 held-out rows, 1% tolerance"
            />
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="Refusal rate" icon={ShieldCheck} value={f.eval.refusalRate ?? "—"} format={(n) => pct(n)} hint="100 off-topic prompts (higher is better)" />
            <KpiCard label="False refusals" value={f.eval.falseRefusalRate ?? "—"} format={(n) => pct(n)} hint="finance prompts wrongly declined (lower is better)" />
            <KpiCard
              label="Judge win rate"
              value={f.eval.judgeWinRate ?? "—"}
              format={(n) => pct(n)}
              hint={f.eval.judgeModel ? `judged by ${f.eval.judgeModel}` : "100-item pairwise comparison"}
            />
            <KpiCard
              label="MMLU-mini"
              icon={Cpu}
              value={f.eval.mmluMiniTuned ?? "—"}
              format={(n) => pct(n)}
              delta={shareDelta(f.eval.mmluMiniBase, f.eval.mmluMiniTuned)}
              hint="100-question sanity check"
            />
          </div>

          {chart.length > 0 && (
            <Panel>
              <PanelHeader title="Base vs fine-tuned" description="Same prompts, same decoding — only the LoRA adapter differs." />
              <div className="px-2 pt-4 pb-3 sm:px-4">
                <BaseVsTuned data={chart} />
              </div>
            </Panel>
          )}

          {f.notes.length > 0 && (
            <Panel className="p-4 sm:p-5">
              <h3 className="text-sm font-semibold">Notes</h3>
              <ul className="mt-2 space-y-1.5">
                {f.notes.map((n, i) => (
                  <li key={i} className="flex gap-2 text-sm text-muted-foreground">
                    <Lightbulb className="mt-0.5 size-3.5 shrink-0 text-brand" aria-hidden />
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
