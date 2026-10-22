import { useId, useMemo } from "react";
import { motion } from "framer-motion";
import { TrendingDown, TrendingUp } from "lucide-react";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltipContent } from "@/components/ui/chart";
import { TooltipRow } from "@/components/metrics/chart-bits";
import { CHART_ANIM } from "@/components/metrics/chart-palette";
import { PERIODS, formatPointDate, formatPrice } from "@/lib/feature-api/market";
import { SPRING_SNAPPY } from "@/lib/motion";
import type { HistoryPeriod, MarketHistory } from "@/lib/feature-types";
import { cn } from "@/lib/utils";

interface SparklineProps {
  history: MarketHistory | undefined;
  loading: boolean;
  period: HistoryPeriod;
  onPeriodChange: (p: HistoryPeriod) => void;
  currency: string | null | undefined;
  /** Line colour follows the sign of the move over the period. */
  className?: string;
}

/** Closing-price area chart with the 1M / 3M / 1Y toggle. Colour = direction over the window (plus the sign in text). */
export function Sparkline({ history, loading, period, onPeriodChange, currency, className }: SparklineProps) {
  const gid = useId().replace(/[^\w-]/g, "");
  const points = useMemo(() => (history?.points ?? []).filter((p) => Number.isFinite(p.close)), [history]);
  const first = points[0]?.close;
  const last = points[points.length - 1]?.close;
  const up = first != null && last != null ? last >= first : true;
  const move = first != null && last != null && first !== 0 ? ((last - first) / first) * 100 : null;
  const years = new Set(points.map((p) => p.date.slice(0, 4)));
  const withYear = years.size > 1;
  const tone = up ? "var(--success)" : "var(--danger)";
  const domain = useMemo(() => {
    if (!points.length) return ["auto", "auto"] as const;
    const lo = Math.min(...points.map((p) => p.close));
    const hi = Math.max(...points.map((p) => p.close));
    const pad = (hi - lo || hi * 0.02 || 1) * 0.12;
    return [lo - pad, hi + pad] as const;
  }, [points]);

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-muted-foreground">
          {move != null ? (
            <>
              <span className={cn("inline-flex items-center gap-1 font-medium tabular-nums", up ? "text-success" : "text-danger")}>
                {up ? <TrendingUp className="size-3.5" aria-hidden /> : <TrendingDown className="size-3.5" aria-hidden />}
                <span className="sr-only">{up ? "Up" : "Down"}</span>
                {Math.abs(move).toFixed(2)}%
              </span>{" "}
              over {PERIODS.find((p) => p.id === period)?.label ?? period}
            </>
          ) : loading ? (
            "Loading history…"
          ) : (
            "No history for this period."
          )}
        </div>
        <div role="radiogroup" aria-label="History period" className="inline-flex rounded-full border bg-card p-0.5">
          {PERIODS.map((p) => (
            <motion.button
              key={p.id}
              type="button"
              role="radio"
              aria-checked={period === p.id}
              onClick={() => onPeriodChange(p.id)}
              whileTap={{ scale: 0.94 }}
              transition={SPRING_SNAPPY}
              className={cn(
                "relative rounded-full px-2.5 py-1 text-xs font-medium transition-colors duration-150 focus-visible:outline-2",
                period === p.id ? "text-background" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {period === p.id && (
                <motion.span layoutId={"period-" + gid} transition={SPRING_SNAPPY} className="absolute inset-0 rounded-full bg-foreground" aria-hidden />
              )}
              <span className="relative">{p.label}</span>
            </motion.button>
          ))}
        </div>
      </div>
      <ChartContainer
        config={{ close: { label: "Close", color: tone } }}
        className={cn("mt-3 aspect-auto h-44 w-full transition-opacity sm:h-52", loading && "opacity-60")}
        role="img"
        aria-label={`Closing price over ${period}`}
      >
        <AreaChart data={points} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`spark-${gid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={tone} stopOpacity={0.16} />
              <stop offset="100%" stopColor={tone} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={28}
            tickFormatter={(v: string) => formatPointDate(v, withYear)}
          />
          <YAxis domain={domain} tickLine={false} axisLine={false} width={64} tickFormatter={(v: number) => formatPrice(v, currency)} />
          <Tooltip
            cursor={{ stroke: "var(--border)" }}
            content={
              <ChartTooltipContent
                labelFormatter={(_v, payload) => {
                  const p = payload?.[0]?.payload as { date?: string } | undefined;
                  return p?.date ? formatPointDate(p.date, true) : "";
                }}
                formatter={(value) => <TooltipRow color={tone} label="Close" value={formatPrice(Number(value), currency)} />}
              />
            }
          />
          <Area
            dataKey="close"
            type="monotone"
            stroke={tone}
            strokeWidth={1.75}
            fill={`url(#spark-${gid})`}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, fill: "var(--card)" }}
            {...CHART_ANIM}
          />
        </AreaChart>
      </ChartContainer>
    </div>
  );
}
