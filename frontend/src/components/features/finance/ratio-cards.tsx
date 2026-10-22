import { BadgeCheck, ShieldAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import { Panel } from "@/components/metrics/section";
import { CountUp } from "@/components/motion";
import type { FinanceReport } from "@/lib/feature-types";
import { cn } from "@/lib/utils";

type Health = "healthy" | "watch" | "risk";

interface RatioSpec {
  key: "currentRatio" | "quickRatio" | "debtToEquity";
  title: string;
  formula: string;
  /** Upper end of the bar scale. */
  max: number;
  /** [good boundary, risk boundary] — direction depends on `higherIsBetter`. */
  bands: [number, number];
  higherIsBetter: boolean;
  advice: Record<Health, string>;
}

const SPECS: RatioSpec[] = [
  {
    key: "currentRatio",
    title: "Current ratio",
    formula: "Current assets ÷ current liabilities",
    max: 3,
    bands: [1.5, 1],
    higherIsBetter: true,
    advice: {
      healthy: "Short-term obligations are comfortably covered.",
      watch: "Covered, but with a thin cushion — watch cash timing.",
      risk: "Current liabilities exceed current assets — liquidity risk.",
    },
  },
  {
    key: "quickRatio",
    title: "Quick ratio",
    formula: "(Current assets − inventory) ÷ current liabilities",
    max: 2.5,
    bands: [1, 0.7],
    higherIsBetter: true,
    advice: {
      healthy: "Bills can be paid without selling inventory.",
      watch: "Relies partly on inventory to meet obligations.",
      risk: "Liquid assets fall well short of short-term debts.",
    },
  },
  {
    key: "debtToEquity",
    title: "Debt-to-equity",
    formula: "Total liabilities ÷ shareholders' equity",
    max: 3,
    bands: [1, 2],
    higherIsBetter: false,
    advice: {
      healthy: "Conservatively financed — more equity than debt.",
      watch: "Moderate leverage — fine if earnings are steady.",
      risk: "Highly leveraged — creditors carry most of the risk.",
    },
  },
];

const HEALTH: Record<Health, { label: string; icon: LucideIcon; chip: string; bar: string }> = {
  healthy: { label: "Healthy", icon: BadgeCheck, chip: "bg-success/12 text-success", bar: "bg-success" },
  watch: { label: "Watch", icon: TriangleAlert, chip: "bg-warning/14 text-warning", bar: "bg-warning" },
  risk: { label: "At risk", icon: ShieldAlert, chip: "bg-danger/12 text-danger", bar: "bg-danger" },
};

function healthOf(spec: RatioSpec, v: number): Health {
  const [good, bad] = spec.bands;
  if (spec.higherIsBetter) return v >= good ? "healthy" : v >= bad ? "watch" : "risk";
  return v <= good ? "healthy" : v <= bad ? "watch" : "risk";
}

/** Balance-sheet ratios with a healthy / watch / at-risk verdict (icon + text, never colour alone). */
export function RatioCards({ sheet }: { sheet: NonNullable<FinanceReport["balanceSheet"]> }) {
  const specs = SPECS.filter((s) => sheet[s.key] != null && Number.isFinite(sheet[s.key]));
  if (specs.length === 0) return null;
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {specs.map((spec) => {
        const v = sheet[spec.key] as number;
        const h = healthOf(spec, v);
        const meta = HEALTH[h];
        const Icon = meta.icon;
        const pos = Math.min(100, Math.max(0, (v / spec.max) * 100));
        return (
          <Panel key={spec.key} className="flex flex-col gap-2 p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium">{spec.title}</div>
                <div className="text-[11px] text-muted-foreground">{spec.formula}</div>
              </div>
              <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", meta.chip)}>
                <Icon className="size-3" aria-hidden /> {meta.label}
              </span>
            </div>
            <div className="font-brand text-3xl font-normal tracking-[-0.01em] tabular-nums">
              <CountUp value={v} format={(n) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} />
              <span className="ml-0.5 text-lg text-muted-foreground">×</span>
            </div>
            <div className="relative h-1.5 rounded-full bg-muted" aria-hidden>
              <motion.div
                className={cn("absolute inset-y-0 left-0 rounded-full", meta.bar)}
                initial={{ width: 0 }}
                animate={{ width: `${Math.max(3, pos)}%` }}
                transition={{ duration: 0.4, ease: "easeOut" }}
              />
              {spec.bands.map((b) => (
                <span
                  key={b}
                  className="absolute -top-0.5 h-2.5 w-px bg-foreground/40"
                  style={{ left: `${Math.min(100, (b / spec.max) * 100)}%` }}
                />
              ))}
            </div>
            <p className="text-xs text-muted-foreground">{spec.advice[h]}</p>
          </Panel>
        );
      })}
    </div>
  );
}
