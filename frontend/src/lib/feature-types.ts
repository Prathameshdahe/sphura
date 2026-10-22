// Feature contract mirror: docs/CONTRACT.md "Wave 2 additions" (kept parts) + docs/FINANCE_PLAN.md §8. Change both together.
import type { ChatMode, DocumentInfo, ISODate } from "@/lib/types";

/* ── verification (answer check) ── */
export interface VerifiedSentence {
  text: string;
  start: number;
  end: number;
  sourceIndexes: number[];
  verdict: "supported" | "partial" | "unsupported" | "uncited";
  score: number;
}

export interface Verification {
  score: number;
  label: "grounded" | "mostly grounded" | "partially grounded" | "ungrounded" | "not checkable";
  supported: number;
  partial: number;
  unsupported: number;
  uncited: number;
  model: string;
  sentences: VerifiedSentence[];
}

/* ── memory ── */
export interface MemoryItem {
  id: string;
  content: string;
  createdAt: ISODate;
  sourceMessageId?: string | null;
}

export interface MemoryState {
  enabled: boolean;
  items: MemoryItem[];
}

/* ── finance analytics (dashboard) ── */
export interface FinanceReport {
  docId: string;
  filename: string;
  kind: "bank_statement" | "balance_sheet" | "table";
  currency: string | null;
  period: { start: string; end: string } | null;
  totals: { inflow: number; outflow: number; net: number } | null;
  byMonth: { month: string; inflow: number; outflow: number; net: number }[];
  byCategory: { category: string; amount: number; count: number }[];
  topTransactions: { date: string; description: string; amount: number; category: string }[];
  balanceSheet: {
    totalAssets: number | null;
    totalLiabilities: number | null;
    equity: number | null;
    currentRatio: number | null;
    quickRatio: number | null;
    debtToEquity: number | null;
  } | null;
  /** Profit and loss figures when the file holds a P&L statement (ratios are fractions: 0.12 = 12%). */
  profitLoss?: ProfitLoss | null;
  /** Scale stated in the file ("crore", "lakh", "thousand"), when amounts aren't in units. */
  amountUnit?: string | null;
  insights: string[];
  warnings: string[];
}

export interface ProfitLoss {
  period?: string | null;
  previousPeriod?: string | null;
  revenue?: number | null;
  totalExpenses?: number | null;
  ebitda?: number | null;
  profitBeforeTax?: number | null;
  netProfit?: number | null;
  netMargin?: number | null;
  ebitdaMargin?: number | null;
  revenueGrowth?: number | null;
  profitGrowth?: number | null;
  returnOnEquity?: number | null;
  returnOnAssets?: number | null;
  interestCoverage?: number | null;
}

/* ── markets (FINANCE_PLAN §8) ── */
export interface MarketMatch {
  symbol: string;
  name: string;
  exchange: string;
}

export interface Quote {
  symbol: string;
  name: string;
  price: number;
  currency: string;
  change: number;
  changePercent: number;
  dayHigh?: number | null;
  dayLow?: number | null;
  asOf: ISODate;
  source: "yfinance";
  delayed: true;
}

export type HistoryPeriod = "1mo" | "3mo" | "6mo" | "1y" | "5y";

export interface MarketHistory {
  symbol: string;
  period: string;
  points: { date: string; close: number }[];
}

export type SentimentLabel = "positive" | "neutral" | "negative";

export interface NewsItem {
  title: string;
  url: string;
  domain: string;
  snippet: string;
  publishedAt?: string | null;
  sentiment: { label: SentimentLabel; score: number };
}

/* ── voice (FINANCE_PLAN §8) ── */
export interface TranscribeResult {
  text: string;
  language: string | null;
  provider: "groq" | "local";
}

/* ── agent (LangGraph) ── */
export interface AgentGraph {
  mermaid: string;
  nodes: { id: string; label: string }[];
  edges: { source: string; target: string; label?: string | null }[];
}

/* ── Model Lab (FINANCE_PLAN §8: GET /api/ml/report) ── */
export type ModelKey = "categoriser" | "sentiment" | "router";

export interface PerClassRow {
  label: string;
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface ModelCard {
  key: ModelKey;
  name: string;
  task: string;
  model: string;
  trainedAt: ISODate;
  dataset: { name: string; train: number; test: number; license: string; note: string };
  metrics: { accuracy: number; macroF1: number };
  baseline?: { name: string; accuracy: number; macroF1: number } | null;
  labels: string[];
  perClass: PerClassRow[];
  /** rows = true label, cols = predicted, same order as `labels`. */
  confusion: number[][];
  extras?: Record<string, number> | null;
}

export interface FinetuneReport {
  available: boolean;
  name: string;
  base: string;
  method: string;
  rows: number;
  steps: number;
  epochs: number;
  trainMinutes: number;
  gpu: string;
  lora: { r: number; alpha: number; targets: string[] };
  eval: {
    heldoutPerplexityBase: number | null;
    heldoutPerplexityTuned: number | null;
    finqaEmBase: number | null;
    finqaEmTuned: number | null;
    refusalRate: number | null;
    falseRefusalRate: number | null;
    judgeWinRate: number | null;
    judgeModel: string | null;
    mmluMiniBase: number | null;
    mmluMiniTuned: number | null;
  };
  ollamaTag: string | null;
  notes: string[];
}

export interface RagEvalConfig {
  name: string;
  recallAt1: number;
  recallAt3: number;
  recallAt5: number;
  recallAt10: number;
  mrr: number;
  ndcg10: number;
  latencyMsP50: number;
  latencyMsP95: number;
}

export interface RagEvalReport {
  available: boolean;
  runAt?: ISODate;
  dataset?: { name: string; documents: number; chunks: number; questions: number };
  k?: number;
  configs?: RagEvalConfig[];
  notes?: string[];
}

export interface ModelLabReport {
  models: ModelCard[];
  finetune: FinetuneReport | null;
  ragEval: RagEvalReport;
  generatedAt: ISODate;
}

export interface VerificationStats {
  answers: number;
  avgScore: number | null;
  labelCounts: Record<string, number>;
  histogram: { bucket: string; count: number }[];
}

/* ── navigation hand-off into a new chat (CONTRACT "Frontend navigation contract") ── */
export interface NewChatState {
  fresh: true;
  attachDoc?: DocumentInfo;
  attachDocs?: DocumentInfo[];
  /** Pre-fills the composer (sent straight away when `autoSend` is set). */
  prompt?: string;
  /** Send `prompt` as the first message as soon as the new chat opens (workspace dock). */
  autoSend?: boolean;
  /** Web search for that auto-sent first message (defaults to the saved preference). */
  webSearch?: boolean;
  /** Kept for compatibility; ignored by the finance UI. */
  mode?: ChatMode;
}
