import { Database, Newspaper, RefreshCw, Route, Tag, Target, type LucideIcon } from "lucide-react";
import { toast } from "sonner";
import { JobProgress } from "@/components/metrics/chart-bits";
import { int, pct, pp } from "@/components/metrics/fmt";
import { KpiCard, type KpiDelta } from "@/components/metrics/kpi-card";
import { Panel, PanelHeader } from "@/components/metrics/section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { useTrainModel } from "@/lib/feature-api/ml";
import type { ModelCard as ModelCardData, ModelKey } from "@/lib/feature-types";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ConfusionMatrix } from "./confusion-matrix";
import { PerClassTable } from "./per-class-table";

/** Badges that wrap on narrow cards instead of being clipped (the shadcn badge is single-line by default). */
export const WRAP_BADGE = "h-auto max-w-full whitespace-normal py-0.5 text-left text-muted-foreground";

/** What each trained classifier does inside the finance graph (FINANCE_PLAN §3, §5). */
const MODEL_META: Record<ModelKey, { icon: LucideIcon; blurb: string }> = {
  router: {
    icon: Route,
    blurb: "Reads every question first and picks the branch: spending, documents, market, explain, advice — or a polite refusal with no model call.",
  },
  categoriser: {
    icon: Tag,
    blurb: "Labels each bank-statement narration (UPI, NEFT, IMPS, card…) with a spending category for the dashboard and the analytics node.",
  },
  sentiment: {
    icon: Newspaper,
    blurb: "Labels finance headlines positive, neutral or negative for the Markets page and the market branch of the agent.",
  },
};

const humanise = (key: string) => key.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/** Values in 0..1 are shares, anything else a count. */
const extraValue = (v: number) => (v >= 0 && v <= 1 ? pct(v) : int(v));

function delta(value: number, base: number | undefined, baseName: string | undefined): KpiDelta | null {
  if (base == null || !baseName) return null;
  const d = value - base;
  return {
    text: `${pp(d)} vs ${baseName}`,
    direction: d > 0.0005 ? "up" : d < -0.0005 ? "down" : "flat",
    good: d >= 0,
  };
}

interface ModelCardProps {
  card: ModelCardData;
  isAdmin: boolean;
}

/** One trained classifier: KPI tiles with the baseline delta, per-class scores and the confusion heatmap. */
export function ModelCard({ card, isAdmin }: ModelCardProps) {
  const meta = MODEL_META[card.key] ?? { icon: Target, blurb: card.task };
  const Icon = meta.icon;
  const train = useTrainModel();
  const extras = Object.entries(card.extras ?? {}).filter(([, v]) => Number.isFinite(v));
  const [extraKey, extraVal] = extras[0] ?? [];

  const retrain = () => {
    const id = toast.loading(`Retraining the ${card.name.toLowerCase()}…`, { description: "Runs in a backend thread; this page updates when it finishes." });
    train.mutate(card.key, {
      onSuccess: (c) => toast.success(`${c.name} retrained`, { id, description: `Accuracy ${pct(c.metrics.accuracy)} · macro-F1 ${pct(c.metrics.macroF1)}` }),
      onError: (e) => toast.error(errorMessage(e, "Training failed"), { id, description: undefined }),
    });
  };

  return (
    <Panel className="p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 items-start gap-3.5">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl border bg-muted/60 text-muted-foreground" aria-hidden>
            <Icon className="size-5" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <h3 className="font-brand text-xl leading-tight font-normal tracking-[-0.01em] sm:text-2xl">{card.name}</h3>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{meta.blurb}</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <Badge variant="outline" className={cn(WRAP_BADGE, "font-mono")}>
                {card.model}
              </Badge>
              <Badge variant="outline" className={WRAP_BADGE}>
                {card.task}
              </Badge>
              <Badge variant="outline" className={WRAP_BADGE}>
                trained {formatRelative(card.trainedAt)}
              </Badge>
            </div>
          </div>
        </div>
        {isAdmin && (
          <Button variant="outline" size="sm" onClick={retrain} disabled={train.isPending}>
            <RefreshCw className={train.isPending ? "animate-spin" : undefined} /> {train.isPending ? "Training…" : "Retrain"}
          </Button>
        )}
      </div>

      {train.isPending && (
        <div className="mt-4">
          <JobProgress label={`Training ${card.name}`} detail={`${card.model} on ${int(card.dataset.train)} examples.`} startedAt={train.submittedAt} />
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Accuracy"
          icon={Target}
          accent
          value={card.metrics.accuracy}
          format={(n) => pct(n)}
          delta={delta(card.metrics.accuracy, card.baseline?.accuracy, card.baseline?.name)}
          hint="held-out test set"
        />
        <KpiCard
          label="Macro-F1"
          value={card.metrics.macroF1}
          format={(n) => pct(n)}
          delta={delta(card.metrics.macroF1, card.baseline?.macroF1, card.baseline?.name)}
          hint={`${card.labels.length} classes, equally weighted`}
        />
        <KpiCard label="Test examples" icon={Database} value={card.dataset.test} format={int} hint={`${int(card.dataset.train)} used for training`} />
        {extraKey != null && extraVal != null ? (
          <KpiCard label={humanise(extraKey)} value={extraVal} format={extraValue} hint="extra evaluation" />
        ) : (
          <KpiCard label="Classes" value={card.labels.length} format={int} hint={card.labels.slice(0, 3).join(", ") + (card.labels.length > 3 ? "…" : "")} />
        )}
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        <span className="font-medium text-foreground/80">{card.dataset.name}</span> · {card.dataset.license}
        {card.dataset.note ? ` · ${card.dataset.note}` : ""}
        {card.baseline ? ` · baseline “${card.baseline.name}”: ${pct(card.baseline.accuracy)} accuracy, ${pct(card.baseline.macroF1)} macro-F1` : ""}
        {extras.length > 1 ? ` · ${extras.slice(1).map(([k, v]) => `${humanise(k)} ${extraValue(v)}`).join(" · ")}` : ""}
      </p>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Panel className="shadow-none">
          <PanelHeader title="Per-class scores" description="Precision, recall and F1 on the test set." />
          <div className="px-4 pt-2 pb-3 sm:px-5">
            <PerClassTable rows={card.perClass} />
          </div>
        </Panel>
        <Panel className="shadow-none">
          <PanelHeader title="Confusion matrix" description="True label down, predicted label across." />
          <div className="px-4 pt-3 pb-4 sm:px-5">
            <ConfusionMatrix labels={card.labels} matrix={card.confusion} />
          </div>
        </Panel>
      </div>
    </Panel>
  );
}
