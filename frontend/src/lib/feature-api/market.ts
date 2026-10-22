// Markets API (FINANCE_PLAN §8: /api/market/*) + React Query hooks + the localStorage watchlist.
import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { ApiError, request } from "@/lib/api";
import type { HistoryPeriod, MarketHistory, MarketMatch, NewsItem, Quote } from "@/lib/feature-types";
import { safeStorage } from "@/stores/prefs";

export const marketKeys = {
  all: ["market"] as const,
  search: (q: string) => ["market", "search", q] as const,
  quote: (symbol: string) => ["market", "quote", symbol] as const,
  history: (symbol: string, period: HistoryPeriod) => ["market", "history", symbol, period] as const,
  news: (query: string) => ["market", "news", query] as const,
};

const enc = encodeURIComponent;

export const marketApi = {
  search: (q: string, signal?: AbortSignal) => request<{ matches: MarketMatch[] }>(`/market/search?q=${enc(q)}`, { signal }),
  quote: (symbol: string) => request<Quote>(`/market/quote?symbol=${enc(symbol)}`),
  history: (symbol: string, period: HistoryPeriod) =>
    request<MarketHistory>(`/market/history?symbol=${enc(symbol)}&period=${period}`),
  news: (query: string) => request<{ items: NewsItem[] }>(`/market/news?query=${enc(query)}`),
};

export const PERIODS: { id: HistoryPeriod; label: string }[] = [
  { id: "1mo", label: "1M" },
  { id: "3mo", label: "3M" },
  { id: "1y", label: "1Y" },
];

/** Quotes are delayed and cached server-side (≥ 60 s), so a minute of client staleness costs nothing. */
const QUOTE_STALE_MS = 60_000;

// A 404 ("unknown symbol") won't fix itself: show it at once; retry only network blips, once.
const retryNetworkOnce = (count: number, error: unknown) => error instanceof ApiError && error.status === 0 && count < 1;

export function useSymbolSearch(q: string, enabled = true) {
  const t = q.trim();
  return useQuery<MarketMatch[], ApiError>({
    queryKey: marketKeys.search(t),
    queryFn: async ({ signal }): Promise<MarketMatch[]> => (await marketApi.search(t, signal)).matches ?? [],
    enabled: enabled && t.length >= 2,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
    retry: retryNetworkOnce,
    meta: { silent: true },
  });
}

export function useQuote(symbol: string | null) {
  return useQuery({
    queryKey: marketKeys.quote(symbol ?? ""),
    queryFn: () => marketApi.quote(symbol as string),
    enabled: !!symbol,
    staleTime: QUOTE_STALE_MS,
    refetchInterval: QUOTE_STALE_MS,
    retry: retryNetworkOnce,
    meta: { silent: true },
  });
}

/** One quote per watched symbol (small lists only; the sidebar caps the watchlist). */
export function useQuotes(symbols: string[]) {
  return useQueries({
    queries: symbols.map((symbol) => ({
      queryKey: marketKeys.quote(symbol),
      queryFn: () => marketApi.quote(symbol),
      staleTime: QUOTE_STALE_MS,
      retry: retryNetworkOnce,
      meta: { silent: true },
    })),
  });
}

export function useHistory(symbol: string | null, period: HistoryPeriod) {
  return useQuery({
    queryKey: marketKeys.history(symbol ?? "", period),
    queryFn: () => marketApi.history(symbol as string, period),
    enabled: !!symbol,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
    retry: retryNetworkOnce,
    meta: { silent: true },
  });
}

export function useMarketNews(query: string | null) {
  const q = (query ?? "").trim();
  return useQuery({
    queryKey: marketKeys.news(q),
    queryFn: () => marketApi.news(q).then((r) => r.items ?? []),
    enabled: q.length > 0,
    staleTime: 10 * 60_000,
    retry: retryNetworkOnce,
    meta: { silent: true },
  });
}

/* ── watchlist (per browser) ── */

export const WATCHLIST_MAX = 12;

export interface WatchItem {
  symbol: string;
  name: string;
}

interface WatchlistStore {
  items: WatchItem[];
  add: (item: WatchItem) => void;
  remove: (symbol: string) => void;
  toggle: (item: WatchItem) => void;
}

export const useWatchlist = create<WatchlistStore>()(
  persist(
    (set, get) => ({
      items: [],
      add: (item) =>
        set((s) => (s.items.some((w) => w.symbol === item.symbol) ? s : { items: [item, ...s.items].slice(0, WATCHLIST_MAX) })),
      remove: (symbol) => set((s) => ({ items: s.items.filter((w) => w.symbol !== symbol) })),
      toggle: (item) => (get().items.some((w) => w.symbol === item.symbol) ? get().remove(item.symbol) : get().add(item)),
    }),
    { name: "sphura.watchlist", storage: safeStorage, version: 1 },
  ),
);

/** Starter tickers for an empty watchlist (NSE first, as the app's audience is Indian). */
export const SUGGESTED_SYMBOLS: WatchItem[] = [
  { symbol: "TCS.NS", name: "Tata Consultancy Services" },
  { symbol: "HDFCBANK.NS", name: "HDFC Bank" },
  { symbol: "RELIANCE.NS", name: "Reliance Industries" },
  { symbol: "INFY.NS", name: "Infosys" },
  { symbol: "^NSEI", name: "NIFTY 50" },
  { symbol: "AAPL", name: "Apple" },
];

/* ── formatting ── */

const fmtCache = new Map<string, Intl.NumberFormat>();

function fmt(currency: string | null | undefined, opts: Intl.NumberFormatOptions): Intl.NumberFormat {
  const code = currency && /^[A-Za-z]{3}$/.test(currency) ? currency.toUpperCase() : null;
  const key = `${code ?? "-"}:${JSON.stringify(opts)}`;
  let f = fmtCache.get(key);
  if (!f) {
    try {
      f = new Intl.NumberFormat(undefined, { ...(code ? { style: "currency", currency: code } : {}), ...opts });
    } catch {
      f = new Intl.NumberFormat(undefined, opts);
    }
    fmtCache.set(key, f);
  }
  return f;
}

/** 3,456.7 → "₹3,456.70" (or "3,456.70" for an index without a currency). */
export function formatPrice(value: number, currency: string | null | undefined): string {
  if (!Number.isFinite(value)) return "–";
  const digits = Math.abs(value) >= 1000 ? 2 : Math.abs(value) >= 1 ? 2 : 4;
  return fmt(currency, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

/** Signed change: "+12.35 (+0.42%)". */
export function formatChange(change: number, changePercent: number): string {
  const sign = change > 0 ? "+" : change < 0 ? "−" : "";
  const abs = Math.abs(change).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pct = Math.abs(changePercent).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${sign}${abs} (${sign}${pct}%)`;
}

/** ISO date → "22 Oct", or "22 Oct 24" when the series spans years. */
export function formatPointDate(value: string, withYear = false): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", ...(withYear ? { year: "2-digit" } : {}) });
}
