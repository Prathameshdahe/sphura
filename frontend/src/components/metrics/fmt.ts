// Number formatting for the ML Lab (Intl, locale-aware).

const pctFmt = new Map<number, Intl.NumberFormat>();

/** 0.914 → "91.4%". */
export function pct(x: number | null | undefined, digits = 1): string {
  if (x == null || !Number.isFinite(x)) return "–";
  let f = pctFmt.get(digits);
  if (!f) {
    f = new Intl.NumberFormat(undefined, { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits });
    pctFmt.set(digits, f);
  }
  return f.format(x);
}

/** 0.8123 → "0.812". */
export function dec(x: number | null | undefined, digits = 3): string {
  if (x == null || !Number.isFinite(x)) return "–";
  return x.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function int(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return "–";
  return Math.round(x).toLocaleString();
}

/** Difference of two ratios in percentage points: "+12.3 pp". */
export function pp(delta: number): string {
  const v = delta * 100;
  const sign = v > 0 ? "+" : v < 0 ? "−" : "±";
  return `${sign}${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 })} pp`;
}

export function ms(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return "–";
  return `${x < 10 ? x.toFixed(1) : Math.round(x).toLocaleString()} ms`;
}
