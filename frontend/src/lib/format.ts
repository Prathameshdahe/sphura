import type { ConversationSummary, Provider, ToolStep } from "./types";

/** RFC4122-ish id that also works outside secure contexts (LAN demos over http). */
export function uid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" && window.isSecureContext) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function greeting(date = new Date()): string {
  const h = date.getHours();
  if (h >= 5 && h < 12) return "Good morning";
  if (h >= 12 && h < 17) return "Good afternoon";
  return "Good evening";
}

export function firstName(name?: string | null): string {
  return (name ?? "").trim().split(/\s+/)[0] ?? "";
}

export function initials(name?: string | null, email?: string | null): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (email ?? "?").slice(0, 1).toUpperCase();
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const v = bytes / 1024 ** i;
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}

const parse = (iso: string) => new Date(iso);

export function formatDate(iso: string): string {
  const d = parse(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) });
}

export function formatRelative(iso: string): string {
  const d = parse(iso);
  const diff = Date.now() - d.getTime();
  if (Number.isNaN(diff)) return "";
  const min = Math.round(diff / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const hours = Math.round(min / 60);
  if (hours < 24) return `${hours} h ago`;
  return formatDate(iso);
}

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 10) return `${s.toFixed(1)} s`;
  if (s < 60) return `${Math.round(s)} s`;
  const m = Math.floor(s / 60);
  return `${m} m ${Math.round(s - m * 60)} s`;
}

export function domainOf(url?: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export const PROVIDER_LABEL: Record<Provider, string> = {
  ensemble: "Ensemble",
  gemini: "Gemini",
  groq: "Groq",
  nvidia: "NVIDIA",
  ollama: "Ollama",
  lmstudio: "LM Studio",
  mock: "Mock",
};

export interface ConversationGroup {
  label: string;
  items: ConversationSummary[];
}

/** Sidebar buckets: Pinned / Today / Yesterday / Previous 7 days / Previous 30 days / Older. */
export function groupConversations(list: ConversationSummary[], now = new Date()): ConversationGroup[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86_400_000;
  const buckets: ConversationGroup[] = [
    { label: "Pinned", items: [] },
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Previous 7 days", items: [] },
    { label: "Previous 30 days", items: [] },
    { label: "Older", items: [] },
  ];
  for (const c of list) {
    if (c.pinned) {
      buckets[0].items.push(c);
      continue;
    }
    const t = parse(c.updatedAt).getTime();
    if (t >= startOfToday) buckets[1].items.push(c);
    else if (t >= startOfToday - day) buckets[2].items.push(c);
    else if (t >= startOfToday - 7 * day) buckets[3].items.push(c);
    else if (t >= startOfToday - 30 * day) buckets[4].items.push(c);
    else buckets[5].items.push(c);
  }
  return buckets.filter((b) => b.items.length > 0);
}

export function stepsDurationMs(steps: ToolStep[], now = Date.now()): number {
  if (steps.length === 0) return 0;
  const start = Math.min(...steps.map((s) => parse(s.startedAt).getTime()));
  const end = Math.max(...steps.map((s) => (s.finishedAt ? parse(s.finishedAt).getTime() : now)));
  return Math.max(0, end - start);
}

/** Markdown → plain text for tiny surfaces (Focus card, previews). */
export function toPlainText(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/^\s*\|.*\|\s*$/gm, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "• ")
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(\*|_)(.*?)\1/g, "$2")
    .replace(/\$\$?([^$]+)\$\$?/g, "$1")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Clip to roughly `max` chars at a word boundary. */
export function clip(text: string, max: number): string {
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const at = cut.lastIndexOf(" ");
  return `${(at > max * 0.6 ? cut.slice(0, at) : cut).trimEnd()}…`;
}
