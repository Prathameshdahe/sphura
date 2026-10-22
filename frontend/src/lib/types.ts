// Mirrors docs/CONTRACT.md exactly. Change both together.
import type { Verification } from "@/lib/feature-types";

export type ISODate = string;
/** Kept for compatibility: the finance agent classifies every question itself, the UI always sends "chat". */
export type ChatMode = "chat" | "research" | "finance";
export type Effort = "fast" | "balanced" | "deep";
export type Phase = "thinking" | "searching" | "reading" | "analyzing" | "composing";
export type Provider = "ensemble" | "gemini" | "groq" | "nvidia" | "ollama" | "lmstudio" | "mock";

export interface User {
  id: string;
  email: string;
  name: string;
  isAdmin: boolean;
  createdAt: ISODate;
}

export interface ModelInfo {
  id: string;
  provider: Provider;
  label: string;
  description: string;
  available: boolean;
  reason?: string | null;
  supportsTools: boolean;
  supportsVision: boolean;
  isDefault: boolean;
}

export interface ConversationSummary {
  id: string;
  title: string;
  mode: ChatMode;
  pinned: boolean;
  createdAt: ISODate;
  updatedAt: ISODate;
}

export interface Source {
  index: number;
  type: "web" | "doc";
  title: string;
  url?: string | null;
  domain?: string | null;
  docId?: string | null;
  filename?: string | null;
  page?: number | null;
  snippet: string;
  score?: number | null;
}

export interface ToolStep {
  id: string;
  name: string;
  label: string;
  status: "running" | "done" | "error";
  detail?: string | null;
  startedAt: ISODate;
  finishedAt?: ISODate | null;
}

export interface AttachmentRef {
  docId: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
}

export interface Message {
  id: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string;
  createdAt: ISODate;
  model?: string | null;
  status: "complete" | "stopped" | "error";
  error?: string | null;
  sources: Source[];
  steps: ToolStep[];
  attachments: AttachmentRef[];
  meta?: Record<string, unknown> | null;
}

export interface ConversationDetail {
  conversation: ConversationSummary;
  messages: Message[];
}

export interface DocumentInfo {
  id: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  status: "queued" | "processing" | "ready" | "error";
  error?: string | null;
  pageCount?: number | null;
  chunkCount: number;
  ocrUsed: boolean;
  conversationId?: string | null;
  createdAt: ISODate;
}

export interface ChatRequest {
  conversationId?: string | null;
  content: string;
  model?: string | null;
  /** Forces the market / finance-news branch (FINANCE_PLAN §3). */
  webSearch: boolean;
  docIds: string[];
  /** Ignored by the finance graph (the intent router decides); always "chat". */
  mode: ChatMode;
  effort: Effort;
  regenerate?: boolean;
  editMessageId?: string | null;
}

export interface Health {
  ok: boolean;
  version: string;
  providers: Record<"gemini" | "groq" | "nvidia" | "ollama" | "lmstudio", boolean>;
  search: { tavily: boolean; duckduckgo: boolean };
  vectorStore: "qdrant" | "qdrant-local";
  embeddings: string;
}

/* ── /api/chat SSE events (unchanged by the finance pivot) ── */
export type ChatEvent =
  | { event: "start"; data: { conversationId: string; userMessage: Message; assistantMessageId: string; model: string } }
  | { event: "status"; data: { phase: Phase; label: string } }
  | { event: "step"; data: ToolStep }
  | { event: "sources"; data: { sources: Source[] } }
  | { event: "delta"; data: { text: string } }
  | { event: "title"; data: { conversationId: string; title: string } }
  | { event: "verification"; data: { verification: Verification } }
  | { event: "done"; data: { message: Message } }
  | { event: "error"; data: { message: string } };

/** Orb light program per phase (see sphura-orb.tsx). */
export const PHASE_PROGRAM: Record<Phase, 0 | 1 | 2 | 3> = {
  thinking: 0,
  searching: 1,
  reading: 2,
  analyzing: 2,
  composing: 3,
};
