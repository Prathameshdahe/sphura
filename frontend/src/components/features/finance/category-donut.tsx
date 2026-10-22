import { useMemo, type CSSProperties } from "react";
import { Pie, PieChart } from "recharts";
import { TooltipRow } from "@/components/metrics/chart-bits";
import { CHART_ANIM, OTHER, SERIES, seriesConfig, type ThemeColor } from "@/components/metrics/chart-palette";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { MoneyFormatter } from "@/lib/feature-api/finance";
import type { FinanceReport } from "@/lib/feature-types";

const TOP = 5;
const share = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 0 });
const ASSET = /asset/i;

type Side = "assets" | "claims" | null;
interface Slice {
  key: string;
  label: string;
  amount: number;
  count: number;
  color: ThemeColor;
  side: Side;
}

/** Top N by amount, the rest folded into one neutral "Other" slice. */
function topWithOther(rows: { category: string; amount: number; count: number }[], keep: number, offset: number, side: Side): Slice[] {
  // Never fold a single leftover into "Other (1)" when a colour is still free for it.
  if (rows.length === keep + 1 && offset + rows.length <= SERIES.length && side === null) keep += 1;
  const head = rows.slice(0, keep).map((c, i) => ({
    key: `k${offset + i}`,
    label: c.category,
    amount: c.amount,
    count: c.count,
    color: SERIES[(offset + i) % SERIES.length],
    side,
  }));
  const tail = rows.slice(keep);
  if (tail.length) {
    head.push({
      key: `other${offset}`,
      label: `Other (${tail.length})`,
      amount: tail.reduce((n, c) => n + c.amount, 0),
      count: tail.reduce((n, c) => n + c.count, 0),
      color: OTHER,
      side,
    });
  }
  return head;
}

/**
 * Category share as a donut (top 5 + "Other"), with a legend list that doubles as the table view.
 * `balance` (balance sheets): assets on one half, liabilities + equity on the other — each side is its own 100%,
 * and the centre shows total assets instead of a double-counted grand total.
 */
export function CategoryDonut({
  data,
  money,
  centerLabel,
  balance = false,
}: {
  data: FinanceReport["byCategory"];
  money: MoneyFormatter;
  centerLabel: string;
  balance?: boolean;
}) {
  const { slices, config, total, sideTotals, label } = useMemo(() => {
    const sorted = data
      .map((c) => ({ ...c, amount: Math.abs(c.amount) }))
      .filter((c) => c.amount > 0)
      .sort((a, b) => b.amount - a.amount);
    const assets = sorted.filter((c) => ASSET.test(c.category));
    const claims = sorted.filter((c) => !ASSET.test(c.category));
    const split = balance && assets.length > 0 && claims.length > 0;
    const rows: Slice[] = split
      ? [...topWithOther(assets, 3, 0, "assets"), ...topWithOther(claims, 3, 3, "claims")]
      : topWithOther(sorted, TOP, 0, null);
    const sum = (side: Side) => rows.filter((r) => r.side === side).reduce((n, r) => n + r.amount, 0);
    const totals: Record<string, number> = split ? { assets: sum("assets"), claims: sum("claims") } : {};
    return {
      slices: rows.map((r) => ({ ...r, fill: `var(--color-${r.key})` })),
      config: seriesConfig(rows.map((r) => ({ key: r.key, label: r.label, color: r.color }))),
      total: split ? totals.assets : rows.reduce((n, r) => n + r.amount, 0),
      sideTotals: totals,
      label: split ? "total assets" : centerLabel,
    };
  }, [data, balance, centerLabel]);

  if (slices.length === 0) return <p className="py-16 text-center text-sm text-muted-foreground">No categorised amounts.</p>;

  const shareOf = (s: (typeof slices)[number]) => {
    const whole = s.side ? sideTotals[s.side] : total;
    return share.format(whole ? s.amount / whole : 0);
  };
  const item = (s: (typeof slices)[number]) => (
    <li key={s.key} className="flex items-center gap-2 text-sm">
      <span
        className="size-2.5 shrink-0 rounded-[2px] bg-(--sw-l) dark:bg-(--sw-d)"
        style={{ "--sw-l": s.color.light, "--sw-d": s.color.dark } as CSSProperties}
        aria-hidden
      />
      <span className="min-w-0 flex-1 truncate" title={s.label}>
        {s.label}
      </span>
      <span className="font-mono text-xs text-muted-foreground tabular-nums">{shareOf(s)}</span>
      <span className="w-14 text-right font-mono text-xs font-medium tabular-nums sm:w-20">{money.compact(s.amount)}</span>
    </li>
  );
  const groups: { side: Side; title: string | null }[] =
    "assets" in sideTotals
      ? [
          { side: "assets", title: "Assets" },
          { side: "claims", title: "Liabilities & equity" },
        ]
      : [{ side: null, title: null }];

  return (
    <div className="grid items-center gap-4 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)]">
      <div className="relative mx-auto aspect-square w-full max-w-[13rem]">
        <ChartContainer config={config} className="aspect-square h-full w-full" role="img" aria-label={`${centerLabel} by category`}>
          <PieChart>
            <ChartTooltip
              content={
                <ChartTooltipContent
                  hideLabel
                  formatter={(value, _name, item) => {
                    const p = item.payload as { label?: string; fill?: string } | undefined;
                    return <TooltipRow color={p?.fill} label={p?.label ?? ""} value={money.full(Number(value))} />;
                  }}
                />
              }
            />
            <Pie
              data={slices}
              dataKey="amount"
              nameKey="key"
              innerRadius="62%"
              outerRadius="96%"
              stroke="var(--card)"
              strokeWidth={2}
              {...CHART_ANIM}
            />
          </PieChart>
        </ChartContainer>
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="font-brand text-lg leading-tight font-normal tabular-nums">{money.compact(total)}</div>
            <div className="text-[11px] text-muted-foreground">{label}</div>
          </div>
        </div>
      </div>
      <div className="min-w-0 space-y-3">
        {groups.map((g) => (
          <div key={g.side ?? "all"}>
            {g.title && (
              <div className="mb-1 flex items-baseline justify-between gap-2 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                <span>{g.title}</span>
                <span className="font-mono tabular-nums normal-case">{money.compact(g.side ? sideTotals[g.side] : total)}</span>
              </div>
            )}
            <ul className="min-w-0 space-y-1.5" aria-label={g.title ?? "Categories"}>
              {slices.filter((s) => s.side === g.side).map(item)}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
