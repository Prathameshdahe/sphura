import type { ToolStep } from "@/lib/types";

/**
 * Typed, defensive view of the keys in `message.meta` (CONTRACT "Chat additions" + the finance graph's finalize node).
 * Everything is optional: the backend may add keys, and older answers carry fewer of them.
 */
export interface MessageMeta {
  /** Intent router decision: `{label|intent, confidence|intentConfidence, autoSearch}`. */
  router: { label: string; confidence: number; autoSearch: boolean } | null;
  memoryUsed: number;
  memoriesAdded: string[];
  /** Statement analytics ran over these documents (`meta.finance.docIds` or `meta.analytics.docIds`). */
  analyticsDocs: number;
  /** Market data was fetched (`meta.market`: `{symbol|symbols, name?}`). */
  market: { symbols: string[]; name: string | null } | null;
  fallbackFrom: string | null;
  durationMs: number | null;
  /** `meta.ensemble`: the merged answer's lead model and every member asked. */
  ensemble: { lead: string | null; members: { id: string; label: string; ms: number | null; ok: boolean }[] } | null;
}

const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null);
const strings = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((s): s is string => typeof s === "string" && !!s.trim()) : [];
const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v.trim() : null);

function readEnsemble(v: unknown): MessageMeta["ensemble"] {
  const e = obj(v);
  if (!e) return null;
  const members = (Array.isArray(e.members) ? e.members : [])
    .map((m) => obj(m))
    .filter((m): m is Record<string, unknown> => !!m && !!str(m.id))
    .map((m) => ({
      id: str(m.id) as string,
      label: str(m.label) ?? (str(m.id) as string),
      ms: typeof m.ms === "number" && Number.isFinite(m.ms) ? m.ms : null,
      ok: m.ok !== false,
    }));
  return members.length ? { lead: str(e.lead), members } : null;
}

export function readMessageMeta(meta: Record<string, unknown> | null | undefined): MessageMeta {
  const router = obj(meta?.router);
  const finance = obj(meta?.finance) ?? obj(meta?.analytics);
  const market = obj(meta?.market);
  const label = str(router?.label) ?? str(router?.intent);
  const symbols = market ? [...strings(market.symbols), ...(str(market.symbol) ? [str(market.symbol) as string] : [])] : [];
  return {
    router: label
      ? {
          label,
          confidence: Math.max(0, Math.min(1, num(router?.confidence ?? router?.intentConfidence))),
          autoSearch: router?.autoSearch === true,
        }
      : null,
    memoryUsed: num(meta?.memoryUsed),
    memoriesAdded: strings(meta?.memoriesAdded),
    analyticsDocs: finance ? strings(finance.docIds).length : 0,
    market: market && (symbols.length || str(market.name)) ? { symbols: [...new Set(symbols)], name: str(market.name) } : null,
    fallbackFrom: str(meta?.fallbackFrom),
    durationMs: typeof meta?.durationMs === "number" ? meta.durationMs : null,
    ensemble: readEnsemble(meta?.ensemble),
  };
}

/** `## ` headings of a markdown answer (outside code fences), cleaned for a table of contents. */
export function h2Headings(md: string): string[] {
  const out: string[] = [];
  let fence: string | null = null;
  for (const line of md.split(/\r?\n/)) {
    const f = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (f) {
      if (!fence) fence = f[1];
      else if (f[1][0] === fence[0] && f[1].length >= fence.length) fence = null;
      continue;
    }
    if (fence) continue;
    const h = /^ {0,3}##\s+(.+?)\s*#*\s*$/.exec(line);
    if (h) {
      out.push(
        h[1]
          .replace(/\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g, "")
          .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
          .replace(/[*_`]/g, "")
          .trim(),
      );
    }
  }
  return out.filter(Boolean);
}

/** True while the answer verifier is running (drives "Checking claims…"). */
export const isVerifying = (steps: ToolStep[]) => steps.some((s) => s.name === "verify" && s.status === "running");
