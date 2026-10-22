// Finance API (docs/CONTRACT.md → "Finance") + React Query hooks + number formatting helpers.
import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";
import type { FinanceReport } from "@/lib/feature-types";
import type { DocumentInfo } from "@/lib/types";

export const financeKeys = {
  all: ["finance"] as const,
  report: (docId: string) => ["finance", "report", docId] as const,
};

export const financeApi = {
  analyze: (docId: string) => request<FinanceReport>("/finance/analyze", { method: "POST", body: { docId } }),
};

export const TABULAR_ACCEPT = ".csv,.xlsx,.xls";

export function isTabularDoc(doc: Pick<DocumentInfo, "filename">): boolean {
  return /\.(csv|xlsx|xls)$/i.test(doc.filename);
}

/** Analytics for one ready document; cached for the session so returning to the page is instant. */
export function useFinanceReport(docId: string | null) {
  return useQuery({
    queryKey: financeKeys.report(docId ?? ""),
    queryFn: () => financeApi.analyze(docId as string),
    enabled: !!docId,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    retry: false,
  });
}

/* ── formatting ── */

function validCurrency(code: string | null | undefined): string | null {
  if (!code || !/^[A-Za-z]{3}$/.test(code)) return null;
  try {
    new Intl.NumberFormat(undefined, { style: "currency", currency: code.toUpperCase() });
    return code.toUpperCase();
  } catch {
    return null;
  }
}

export interface MoneyFormatter {
  /** Full amount, e.g. "₹1,23,450" / "$12,340.50". */
  full: (n: number) => string;
  /** Compact for axes and tiles, e.g. "$12.3K". */
  compact: (n: number) => string;
  currency: string | null;
}

export function moneyFormatter(currency: string | null | undefined): MoneyFormatter {
  const code = validCurrency(currency);
  const base: Intl.NumberFormatOptions = code ? { style: "currency", currency: code } : {};
  const full = new Intl.NumberFormat(undefined, { ...base, maximumFractionDigits: 2, minimumFractionDigits: 0 });
  const compact = new Intl.NumberFormat(undefined, { ...base, notation: "compact", maximumFractionDigits: 1 });
  return {
    full: (n) => (Number.isFinite(n) ? full.format(n) : "–"),
    compact: (n) => (Number.isFinite(n) ? compact.format(n) : "–"),
    currency: code,
  };
}

/** "2025-03" → "Mar 2025"; `tick` → "Mar" (or "Mar 25" when the series spans several years). Falls back to the raw string. */
export function formatMonth(month: string, tick: false | "month" | "month-year" = false): string {
  const m = /^(\d{4})-(\d{2})/.exec(month);
  if (!m) return month;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, 1);
  if (tick === "month") return d.toLocaleDateString(undefined, { month: "short" });
  if (tick === "month-year") return d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
  return d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

/** ISO-ish date → "3 Mar 2025". Falls back to the raw string. */
export function formatDay(value: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!m) return value;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
