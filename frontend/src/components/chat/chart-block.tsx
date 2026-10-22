import { useId, useMemo } from "react";
import { useReducedMotion } from "framer-motion";
import { Check, Copy } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SERIES } from "@/components/metrics/chart-palette";
import { useCopy } from "@/hooks/use-copy";
import { useIsDark } from "@/hooks/use-is-dark";
import { chartCsv, formatChartTick, formatChartValue, unitCaption, type ChartSpec } from "@/lib/chart-spec";

const tooltipStyle = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 12,
  color: "var(--popover-foreground)",
  fontSize: 12,
  boxShadow: "var(--shadow-pop)",
} as const;

/** A chart from a ```chart block in an answer: themed recharts, accessible title + data table, "Copy data (CSV)". */
export default function ChartBlock({ spec }: { spec: ChartSpec }) {
  const titleId = useId();
  const dark = useIsDark();
  const reduced = useReducedMotion() ?? false;
  const { copied, copy } = useCopy();
  const colors = useMemo(() => SERIES.map((c) => (dark ? c.dark : c.light)), [dark]);
  const rows = useMemo(
    () => spec.labels.map((label, i) => Object.fromEntries([["label", label], ...spec.series.map((s, k) => [`s${k}`, s.data[i]])])),
    [spec],
  );
  const animation = { isAnimationActive: !reduced, animationDuration: 450 } as const;
  // Lines and areas zoom to the data (a ₹992 → ₹1,190 price history must not look flat); bars keep their zero.
  const domain = useMemo<[number, number] | undefined>(() => {
    if (spec.type !== "line" && spec.type !== "area") return undefined;
    const values = spec.series.flatMap((s) => s.data).filter((v): v is number => v != null && Number.isFinite(v));
    if (values.length === 0) return undefined;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || Math.abs(max) * 0.1 || 1;
    const pad = range * 0.12;
    const step = Math.pow(10, Math.floor(Math.log10(range)) - 1);
    let lo = Math.floor((min - pad) / step) * step;
    const hi = Math.ceil((max + pad) / step) * step;
    if (min >= 0 && lo < 0) lo = 0;
    return [lo, hi];
  }, [spec]);
  const fmt = (v: unknown) => (typeof v === "number" ? formatChartValue(v, spec.unit) : String(v));
  const tick = { fill: "var(--muted-foreground)", fontSize: 11 } as const;
  const axes = (
    <>
      <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 4" />
      <XAxis dataKey="label" tick={tick} tickLine={false} axisLine={{ stroke: "var(--border)" }} interval="preserveStartEnd" minTickGap={8} />
      <YAxis
        tick={tick}
        tickLine={false}
        axisLine={false}
        width={60}
        domain={domain ?? [0, "auto"]}
        allowDataOverflow={false}
        tickFormatter={(v: number) => formatChartTick(v, spec.unit)}
      />
      <Tooltip
        contentStyle={tooltipStyle}
        labelStyle={{ color: "var(--muted-foreground)", marginBottom: 2 }}
        cursor={{ fill: "color-mix(in oklch, var(--foreground) 6%, transparent)" }}
        formatter={(v, name) => [fmt(v), name]}
      />
      {spec.series.length > 1 && <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted-foreground)" }} iconType="circle" iconSize={8} />}
    </>
  );

  let chart: React.ReactElement;
  if (spec.type === "pie") {
    const s = spec.series[0];
    const data = spec.labels
      .map((name, i) => ({ name, value: s.data[i] }))
      .filter((d): d is { name: string; value: number } => d.value != null && d.value > 0);
    chart = (
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius="52%" outerRadius="82%" paddingAngle={1.5} stroke="var(--card)" strokeWidth={2} {...animation}>
          {data.map((d, i) => (
            <Cell key={d.name} fill={colors[i % colors.length]} fillOpacity={i < colors.length ? 1 : 0.6} />
          ))}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} formatter={(v, name) => [fmt(v), name]} />
        <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted-foreground)" }} iconType="circle" iconSize={8} />
      </PieChart>
    );
  } else if (spec.type === "line") {
    chart = (
      <LineChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        {axes}
        {spec.series.map((s, k) => (
          <Line key={s.name} type="monotone" dataKey={`s${k}`} name={s.name} stroke={colors[k % colors.length]} strokeWidth={2.2} dot={rows.length <= 24} connectNulls={false} {...animation} />
        ))}
      </LineChart>
    );
  } else if (spec.type === "area") {
    chart = (
      <AreaChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        {axes}
        {spec.series.map((s, k) => (
          <Area
            key={s.name}
            type="monotone"
            dataKey={`s${k}`}
            name={s.name}
            stroke={colors[k % colors.length]}
            fill={colors[k % colors.length]}
            fillOpacity={0.18}
            strokeWidth={2}
            {...animation}
          />
        ))}
      </AreaChart>
    );
  } else {
    chart = (
      <BarChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        {axes}
        {spec.series.map((s, k) => (
          <Bar key={s.name} dataKey={`s${k}`} name={s.name} fill={colors[k % colors.length]} radius={[5, 5, 0, 0]} maxBarSize={44} {...animation} />
        ))}
      </BarChart>
    );
  }

  return (
    <figure className="not-prose my-4 overflow-hidden rounded-2xl border bg-card font-sans" aria-labelledby={titleId}>
      <figcaption className="flex items-center gap-2 border-b px-4 py-2.5">
        <span id={titleId} className="min-w-0 flex-1 truncate text-[13.5px] font-semibold text-foreground">
          {spec.title}
          {unitCaption(spec.unit) && <span className="ml-1.5 font-normal text-muted-foreground">({unitCaption(spec.unit)})</span>}
        </span>
        <button
          type="button"
          onClick={() => void copy(chartCsv(spec))}
          className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2"
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy data (CSV)"}
        </button>
      </figcaption>
      <div className="h-64 px-2 pt-3 pb-2 sm:h-72" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          {chart}
        </ResponsiveContainer>
      </div>
      {/* The same numbers for screen readers. */}
      <table className="sr-only">
        <caption>{spec.title}</caption>
        <thead>
          <tr>
            <th scope="col">Label</th>
            {spec.series.map((s) => (
              <th key={s.name} scope="col">
                {s.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.labels.map((l, i) => (
            <tr key={`${l}-${i}`}>
              <th scope="row">{l}</th>
              {spec.series.map((s) => (
                <td key={s.name}>{formatChartValue(s.data[i], spec.unit)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
