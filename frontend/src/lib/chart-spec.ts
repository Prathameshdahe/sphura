/** A chart the backend embeds in an answer as a ```chart fenced block (JSON). */
export interface ChartSpec {
  type: "bar" | "line" | "pie" | "area";
  title: string;
  unit: string | null;
  labels: string[];
  /** null = no value for that label (a gap in lines, no bar). */
  series: { name: string; data: (number | null)[] }[];
}

/** Charts larger than this are shown as their JSON instead (keeps answers light). */
export const MAX_CHART_POINTS = 200;
const TYPES = new Set(["bar", "line", "pie", "area"]);

/** number → itself; numeric string → number; null / "" / "-" → null (a gap); anything else → undefined (invalid). */
const toNumber = (v: unknown): number | null | undefined => {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string") {
    const t = v.trim();
    if (!t || t === "-" || t === "—") return null;
    const n = Number(t.replace(/[,₹\s%]/g, ""));
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
};

/** Parse and validate a chart block; null when it isn't a usable chart (invalid JSON, wrong shape, too large). */
export function parseChartSpec(code: string): ChartSpec | null {
  let raw: unknown;
  try {
    raw = JSON.parse(code);
  } catch {
    return null;
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const o = raw as Record<string, unknown>;
  const type = typeof o.type === "string" ? o.type.toLowerCase() : "";
  if (!TYPES.has(type)) return null;
  if (!Array.isArray(o.labels) || o.labels.length === 0 || !Array.isArray(o.series) || o.series.length === 0) return null;
  const labels = o.labels.map((l) => (typeof l === "string" ? l : typeof l === "number" ? String(l) : "")).slice(0, MAX_CHART_POINTS);
  if (labels.some((l) => !l)) return null;
  const series: ChartSpec["series"] = [];
  for (const [i, s] of o.series.entries()) {
    if (!s || typeof s !== "object") return null;
    const so = s as Record<string, unknown>;
    if (!Array.isArray(so.data)) return null;
    const data = so.data.map(toNumber);
    if (data.some((d) => d === undefined) || data.every((d) => d === null)) return null;
    series.push({
      name: typeof so.name === "string" && so.name.trim() ? so.name.trim() : `Series ${i + 1}`,
      data: (data as (number | null)[]).slice(0, labels.length),
    });
  }
  if (series.some((s) => s.data.length !== labels.length)) return null;
  if (labels.length * series.length > MAX_CHART_POINTS || series.length > 8) return null;
  return {
    type: type as ChartSpec["type"],
    title: typeof o.title === "string" && o.title.trim() ? o.title.trim() : "Chart",
    unit: typeof o.unit === "string" && o.unit.trim() ? o.unit.trim() : null,
    labels,
    series: type === "pie" ? series.slice(0, 1) : series,
  };
}

const INR = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const INR_COMPACT = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const PLAIN = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const PLAIN_COMPACT = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

/** "₹ crore" → { rupees: true, scale: "crore" }; "INR" → rupees; "%" → percent; anything else → a suffix. */
function parseUnit(unit: string | null): { rupees: boolean; percent: boolean; scale: string | null } {
  const u = (unit ?? "").trim();
  const m = /^(₹|inr|rs\.?|rupees?)\s*(.*)$/i.exec(u);
  if (m) return { rupees: true, percent: false, scale: m[2].trim() || null };
  return { rupees: false, percent: u === "%", scale: u && u !== "%" ? u : null };
}

/** Full value: ₹1,23,456 (Indian grouping) / ₹1,234 crore / 12.5% / 1,234 kg; null → "–". */
export function formatChartValue(v: number | null, unit: string | null): string {
  if (v === null || !Number.isFinite(v)) return "–";
  const u = parseUnit(unit);
  if (u.rupees) return `₹${INR.format(v)}${u.scale ? ` ${u.scale}` : ""}`;
  if (u.percent) return `${PLAIN.format(v)}%`;
  return u.scale ? `${PLAIN.format(v)} ${u.scale}` : PLAIN.format(v);
}

const INR_WHOLE = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** Axis tick: ₹1,050 (below a lakh, exact so neighbouring ticks never collapse to the same label) / ₹1.2L / ₹1,234 crore
 * values / 40% / 3.4K. */
export function formatChartTick(v: number, unit: string | null): string {
  const u = parseUnit(unit);
  if (u.rupees) return u.scale || Math.abs(v) < 100_000 ? `₹${INR_WHOLE.format(v)}` : `₹${INR_COMPACT.format(v)}`;
  if (u.percent) return `${PLAIN.format(v)}%`;
  return Math.abs(v) < 10_000 ? PLAIN.format(v) : PLAIN_COMPACT.format(v);
}

/** Small caption for the unit when values are scaled ("₹ crore"). */
export function unitCaption(unit: string | null): string | null {
  const u = parseUnit(unit);
  return u.scale ? (u.rupees ? `₹ ${u.scale}` : u.scale) : null;
}

/** CSV of the chart's data (label column + one column per series). */
export function chartCsv(spec: ChartSpec): string {
  const esc = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  const header = ["label", ...spec.series.map((s) => s.name)].map(esc).join(",");
  const rows = spec.labels.map((l, i) => [esc(l), ...spec.series.map((s) => (s.data[i] == null ? "" : String(s.data[i])))].join(","));
  return [header, ...rows].join("\n");
}
