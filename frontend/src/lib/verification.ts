import type { Verification, VerifiedSentence } from "@/lib/feature-types";

/**
 * Answer verification (hallucination meter): parsing `message.meta.verification`, the colour scale,
 * and mapping claim sentences onto the rendered answer with the CSS Custom Highlight API
 * (no DOM mutation, so React's markdown tree is never touched).
 */

export type Verdict = VerifiedSentence["verdict"];
export type Tone = "good" | "ok" | "warn" | "bad" | "none";

const VERDICTS: Verdict[] = ["supported", "partial", "unsupported", "uncited"];
const LABELS = new Set<Verification["label"]>([
  "grounded",
  "mostly grounded",
  "partially grounded",
  "ungrounded",
  "not checkable",
]);

const num = (v: unknown, fallback = 0) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);

function readSentence(raw: unknown): VerifiedSentence | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.text !== "string" || !o.text.trim()) return null;
  const verdict = VERDICTS.includes(o.verdict as Verdict) ? (o.verdict as Verdict) : "uncited";
  return {
    text: o.text,
    start: num(o.start, -1),
    end: num(o.end, -1),
    sourceIndexes: Array.isArray(o.sourceIndexes) ? o.sourceIndexes.filter((n): n is number => typeof n === "number") : [],
    verdict,
    score: Math.max(0, Math.min(1, num(o.score))),
  };
}

/** Validate an unknown value (SSE payload or persisted meta) into a Verification, or null. */
export function parseVerification(raw: unknown): Verification | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.score !== "number" || !Array.isArray(o.sentences)) return null;
  const sentences = o.sentences.map(readSentence).filter((s): s is VerifiedSentence => !!s);
  const count = (k: Verdict) => sentences.filter((s) => s.verdict === k).length;
  const label = LABELS.has(o.label as Verification["label"]) ? (o.label as Verification["label"]) : "not checkable";
  return {
    score: Math.max(0, Math.min(1, o.score)),
    label,
    supported: num(o.supported, count("supported")),
    partial: num(o.partial, count("partial")),
    unsupported: num(o.unsupported, count("unsupported")),
    uncited: num(o.uncited, count("uncited")),
    model: typeof o.model === "string" ? o.model : "",
    sentences,
  };
}

export function verificationFromMeta(meta: Record<string, unknown> | null | undefined): Verification | null {
  return parseVerification(meta?.verification);
}

export function checkable(v: Verification): number {
  return v.supported + v.partial + v.unsupported;
}

export function toneOf(v: Verification): Tone {
  if (v.label === "not checkable" || checkable(v) === 0) return "none";
  if (v.score >= 0.85) return "good";
  if (v.score >= 0.65) return "ok";
  if (v.score >= 0.4) return "warn";
  return "bad";
}

export const percent = (x: number) => `${Math.round(Math.max(0, Math.min(1, x)) * 100)}%`;

/** User-facing wording of the verdict ("Verified · 92%"); the raw label stays in the popover. */
const TONE_WORD: Record<Tone, string> = {
  good: "Verified",
  ok: "Mostly verified",
  warn: "Partly verified",
  bad: "Unverified",
  none: "Not checkable",
};

export function verificationLabel(v: Verification): string {
  const tone = toneOf(v);
  return tone === "none" ? TONE_WORD.none : `${TONE_WORD[tone]} · ${percent(v.score)}`;
}

/** Badge colours per tone (text + soft background + ring), correct in both themes. */
export const TONE_CLASS: Record<Tone, string> = {
  good: "text-success bg-success/10 ring-success/30",
  ok: "text-success bg-success/8 ring-success/20",
  warn: "text-warning bg-warning/10 ring-warning/30",
  bad: "text-danger bg-danger/10 ring-danger/30",
  none: "text-muted-foreground bg-muted ring-border",
};

export const TONE_BAR: Record<Tone, string> = {
  good: "bg-success",
  ok: "bg-success/80",
  warn: "bg-warning",
  bad: "bg-danger",
  none: "bg-muted-foreground/40",
};

export const VERDICT_INFO: Record<Verdict, { label: string; dot: string; chip: string; hint: string }> = {
  supported: {
    label: "Supported",
    dot: "bg-success",
    chip: "bg-success/12 text-success",
    hint: "The cited source entails this claim.",
  },
  partial: {
    label: "Partial",
    dot: "bg-warning",
    chip: "bg-warning/14 text-warning",
    hint: "The cited source only partly backs this claim.",
  },
  unsupported: {
    label: "Unsupported",
    dot: "bg-danger",
    chip: "bg-danger/12 text-danger",
    hint: "The cited source does not back this claim.",
  },
  uncited: {
    label: "Uncited",
    dot: "bg-muted-foreground/50",
    chip: "bg-muted text-muted-foreground",
    hint: "This sentence has no citation to check.",
  },
};

/** Claim text for display: drop citation markers and inline markdown syntax. */
export function cleanClaim(text: string): string {
  return text
    .replace(/\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(^|[^\w*])[*_]([^*_\n]+)[*_](?=[^\w*]|$)/g, "$1$2")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)/gm, "")
    .replace(/\s+([.,;:!?])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/* ── mapping claims onto the rendered answer ── */

/**
 * Elements whose text never belongs to a claim (code blocks, math markup, citation chips, UI chrome).
 * Inline `code` is kept: it is part of the sentence ("use `torch.compile` to …") and of the claim text.
 */
const SKIP = "pre, .katex-mathml, [data-sphura-cite], [data-sphura-skip], button, svg, style, script";

interface TextIndex {
  nodes: Text[];
  starts: number[];
  /** Folded haystack (lower-case letters/digits only) and its map back to the flat text offset. */
  folded: string;
  map: number[];
}

function fold(text: string, base: number, out: { folded: string[]; map: number[] }) {
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (!/[\p{L}\p{N}]/u.test(c)) continue;
    const lower = c.toLowerCase();
    for (let k = 0; k < lower.length; k++) {
      out.folded.push(lower[k]);
      out.map.push(base + i);
    }
  }
}

function indexText(root: HTMLElement): TextIndex {
  const nodes: Text[] = [];
  const starts: number[] = [];
  const acc = { folded: [] as string[], map: [] as number[] };
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => {
      const parent = n.parentElement;
      const skip = parent?.closest(SKIP);
      return !parent || (skip && root.contains(skip)) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
    },
  });
  let offset = 0;
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = n as Text;
    nodes.push(t);
    starts.push(offset);
    fold(t.data, offset, acc);
    offset += t.data.length;
  }
  return { nodes, starts, folded: acc.folded.join(""), map: acc.map };
}

function foldClaim(text: string): string {
  const acc = { folded: [] as string[], map: [] as number[] };
  fold(cleanClaim(text), 0, acc);
  return acc.folded.join("");
}

function locate(idx: TextIndex, flat: number): { node: Text; offset: number } | null {
  let lo = 0;
  let hi = idx.starts.length - 1;
  if (hi < 0) return null;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (idx.starts[mid] <= flat) lo = mid;
    else hi = mid - 1;
  }
  const node = idx.nodes[lo];
  return { node, offset: Math.min(node.data.length, Math.max(0, flat - idx.starts[lo])) };
}

/** Find [start, end) of `needle` in the folded haystack, tolerating small differences in the middle. */
function findFolded(hay: string, needle: string, from: number): [number, number] | null {
  const exact = (at: number) => {
    const i = hay.indexOf(needle, at);
    return i === -1 ? null : ([i, i + needle.length] as [number, number]);
  };
  const hit = exact(from) ?? exact(0);
  if (hit) return hit;
  if (needle.length < 36) return null;
  const head = needle.slice(0, 24);
  const tail = needle.slice(-16);
  for (const at of [from, 0]) {
    const i = hay.indexOf(head, at);
    if (i === -1) continue;
    const j = hay.indexOf(tail, i + head.length);
    if (j !== -1 && j + tail.length - i <= needle.length * 1.6) return [i, j + tail.length];
  }
  return null;
}

export interface ClaimRange {
  sentence: VerifiedSentence;
  index: number;
  range: Range;
}

/** Map each claim sentence to a DOM Range inside the rendered answer; claims that can't be found are skipped. */
export function mapClaims(root: HTMLElement, sentences: VerifiedSentence[]): ClaimRange[] {
  const idx = indexText(root);
  if (!idx.folded) return [];
  const out: ClaimRange[] = [];
  let cursor = 0;
  sentences.forEach((sentence, index) => {
    const needle = foldClaim(sentence.text);
    if (needle.length < 6) return;
    const hit = findFolded(idx.folded, needle, cursor);
    if (!hit) return;
    const startFlat = idx.map[hit[0]];
    const endFlat = idx.map[hit[1] - 1] + 1;
    const a = locate(idx, startFlat);
    const b = locate(idx, endFlat - 1);
    if (!a || !b) return;
    try {
      const range = document.createRange();
      range.setStart(a.node, a.offset);
      range.setEnd(b.node, Math.min(b.node.data.length, b.offset + 1));
      out.push({ sentence, index, range });
      cursor = hit[1];
    } catch {
      /* node vanished mid-render — skip this claim */
    }
  });
  return out;
}

/* ── global highlight registry (CSS.highlights is page-wide; several answers can be highlighted) ── */

export const supportsHighlights = (): boolean =>
  typeof CSS !== "undefined" && "highlights" in CSS && typeof Highlight !== "undefined";

const registered = new Map<string, ClaimRange[]>();

function syncHighlights() {
  if (!supportsHighlights()) return;
  for (const verdict of VERDICTS) {
    const ranges: Range[] = [];
    for (const list of registered.values()) for (const c of list) if (c.sentence.verdict === verdict) ranges.push(c.range);
    const name = `sphura-claim-${verdict}`;
    if (ranges.length) CSS.highlights.set(name, new Highlight(...ranges));
    else CSS.highlights.delete(name);
  }
}

/** Register (or clear, with null) the highlighted claims of one answer. */
export function setClaimHighlights(key: string, claims: ClaimRange[] | null): void {
  if (claims && claims.length) registered.set(key, claims);
  else registered.delete(key);
  syncHighlights();
}

let flashTimer: ReturnType<typeof setTimeout> | undefined;

/** Scroll a claim into view and flash it briefly. */
export function revealClaim(range: Range): void {
  const el = range.startContainer.parentElement;
  el?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  if (!supportsHighlights()) return;
  CSS.highlights.set("sphura-claim-focus", new Highlight(range));
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => CSS.highlights.delete("sphura-claim-focus"), 1800);
}

/** The claim under a viewport point (for the hover tooltip), if any. */
export function claimAtPoint(claims: ClaimRange[], x: number, y: number): ClaimRange | null {
  let node: Node | null = null;
  let offset = 0;
  const doc = document as Document & { caretRangeFromPoint?: (x: number, y: number) => Range | null };
  if (typeof document.caretPositionFromPoint === "function") {
    const pos = document.caretPositionFromPoint(x, y);
    if (pos) {
      node = pos.offsetNode;
      offset = pos.offset;
    }
  } else if (typeof doc.caretRangeFromPoint === "function") {
    const r = doc.caretRangeFromPoint(x, y);
    if (r) {
      node = r.startContainer;
      offset = r.startOffset;
    }
  }
  if (!node) return null;
  for (const c of claims) {
    try {
      if (c.range.comparePoint(node, offset) !== 0) continue;
      // caret APIs snap to the nearest character: make sure the pointer is really over the text
      for (const rect of c.range.getClientRects()) {
        if (x >= rect.left - 2 && x <= rect.right + 2 && y >= rect.top - 2 && y <= rect.bottom + 2) return c;
      }
    } catch {
      /* different document / detached */
    }
  }
  return null;
}
