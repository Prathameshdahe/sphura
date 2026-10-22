import { useMemo } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, XAxis, YAxis } from "recharts";
import { TooltipRow } from "@/components/metrics/chart-bits";
import { ROSE, CHART_ANIM, TEAL, VIOLET, seriesConfig } from "@/components/metrics/chart-palette";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { formatMonth, type MoneyFormatter } from "@/lib/feature-api/finance";
import type { FinanceReport } from "@/lib/feature-types";

const config = seriesConfig([
  { key: "inflow", label: "Inflow", color: TEAL },
  { key: "outflow", label: "Outflow", color: ROSE },
  { key: "net", label: "Net", color: VIOLET },
]);

/** Monthly inflow vs outflow bars with the net line — one shared currency axis. */
export function MonthlyChart({ data, money }: { data: FinanceReport["byMonth"]; money: MoneyFormatter }) {
  const rows = useMemo(() => {
    const years = new Set(data.map((m) => m.month.slice(0, 4)));
    const tick = years.size > 1 ? "month-year" : "month";
    return data.map((m) => ({
      month: m.month,
      label: formatMonth(m.month, tick),
      inflow: Math.abs(m.inflow),
      outflow: Math.abs(m.outflow),
      net: m.net,
    }));
  }, [data]);
  const hasNegative = rows.some((r) => r.net < 0);
  return (
    <ChartContainer
      config={config}
      className="aspect-auto h-72 w-full"
      role="img"
      aria-label={`Monthly inflow, outflow and net over ${rows.length} months`}
    >
      <ComposedChart data={rows} barGap={2} barCategoryGap="22%" margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={8} minTickGap={8} />
        <YAxis tickFormatter={(v: number) => money.compact(v)} tickLine={false} axisLine={false} width={58} />
        {hasNegative && <ReferenceLine y={0} stroke="var(--border)" />}
        <ChartTooltip
          cursor={{ fillOpacity: 0.5 }}
          content={
            <ChartTooltipContent
              labelFormatter={(_v, payload) => {
                const m = payload?.[0]?.payload as { month?: string } | undefined;
                return m?.month ? formatMonth(m.month) : "";
              }}
              formatter={(value, name, item) => (
                <TooltipRow
                  color={item.color}
                  label={config[String(name)]?.label ?? String(name)}
                  value={money.full(Number(value))}
                />
              )}
            />
          }
        />
        <ChartLegend itemSorter={null} content={<ChartLegendContent />} />
        <Bar dataKey="inflow" fill="var(--color-inflow)" radius={[4, 4, 0, 0]} maxBarSize={26} {...CHART_ANIM} />
        <Bar dataKey="outflow" fill="var(--color-outflow)" radius={[4, 4, 0, 0]} maxBarSize={26} {...CHART_ANIM} />
        <Line
          dataKey="net"
          type="monotone"
          stroke="var(--color-net)"
          strokeWidth={2}
          dot={{ r: 3.5, strokeWidth: 2, fill: "var(--card)" }}
          activeDot={{ r: 5 }}
          {...CHART_ANIM}
        />
      </ComposedChart>
    </ChartContainer>
  );
}
