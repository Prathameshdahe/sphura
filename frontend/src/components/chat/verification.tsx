import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Highlighter, Info, LocateFixed, Shield, ShieldAlert, ShieldCheck, ShieldQuestionMark } from "lucide-react";
import { toast } from "sonner";
import { SourcePreview } from "@/components/chat/sources";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import type { HoveredClaim } from "@/hooks/use-claim-highlights";
import { errorMessage } from "@/lib/api";
import type { Verification, VerifiedSentence } from "@/lib/feature-types";
import { useVerifyMessage } from "@/lib/queries";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  TONE_BAR,
  TONE_CLASS,
  VERDICT_INFO,
  checkable,
  cleanClaim,
  percent,
  supportsHighlights,
  toneOf,
  verificationLabel,
  type Verdict,
} from "@/lib/verification";
import "./chat-extras.css";

function ToneIcon({ v, className }: { v: Verification; className?: string }) {
  const tone = toneOf(v);
  if (tone === "none") return <Shield className={className} />;
  if (tone === "good" || tone === "ok") return <ShieldCheck className={className} />;
  return <ShieldAlert className={className} />;
}

/** Live "Checking claims…" chip while the verifier step runs. */
export function VerificationPending() {
  return (
    <span
      role="status"
      className="inline-flex h-7 items-center gap-1.5 rounded-full bg-muted px-2.5 text-xs font-medium text-muted-foreground"
    >
      <ShieldCheck className="size-3.5 animate-pulse text-brand motion-reduce:animate-none" />
      <span className="shimmer-text">Checking claims…</span>
    </span>
  );
}

/** "Check claims" for a saved, sourced answer that has no verification yet (the model was still loading, or it timed out). */
export function VerifyButton({ messageId, conversationId }: { messageId: string; conversationId: string }) {
  const verify = useVerifyMessage();
  if (verify.isPending) return <VerificationPending />;
  return (
    <button
      type="button"
      onClick={() =>
        verify.mutate(
          { messageId, conversationId },
          { onError: (e) => toast.error(`Couldn't check this answer — ${errorMessage(e)}`) },
        )
      }
      title="Check each cited sentence against its sources"
      className="inline-flex h-7 items-center gap-1.5 rounded-full border border-dashed px-2.5 text-[11.5px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-2"
    >
      <ShieldQuestionMark className="size-3.5" />
      Check claims
    </button>
  );
}

function VerdictChip({ verdict, score }: { verdict: Verdict; score?: number }) {
  const info = VERDICT_INFO[verdict];
  return (
    <span
      title={info.hint}
      className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-1.5 text-[10.5px] font-semibold", info.chip)}
    >
      <span className={cn("size-1.5 rounded-full", info.dot)} aria-hidden />
      {info.label}
      {verdict !== "uncited" && typeof score === "number" && <span className="font-medium opacity-75 tabular-nums">{percent(score)}</span>}
    </span>
  );
}

function ScoreBar({ v }: { v: Verification }) {
  const total = Math.max(1, v.supported + v.partial + v.unsupported + v.uncited);
  const parts: { key: Verdict; n: number }[] = [
    { key: "supported", n: v.supported },
    { key: "partial", n: v.partial },
    { key: "unsupported", n: v.unsupported },
    { key: "uncited", n: v.uncited },
  ];
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label="Claim verdicts">
      {parts.map((p) =>
        p.n > 0 ? (
          <span
            key={p.key}
            className={cn("h-full transition-[width] duration-500", VERDICT_INFO[p.key].dot, p.key === "uncited" && "opacity-50")}
            style={{ width: `${(p.n / total) * 100}%` }}
          />
        ) : null,
      )}
    </div>
  );
}

function ClaimItem({
  sentence,
  index,
  sources,
  onLocate,
}: {
  sentence: VerifiedSentence;
  index: number;
  sources: Source[];
  onLocate?: (index: number) => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const shown = open === null ? null : sources.find((s) => s.index === open);
  const text = cleanClaim(sentence.text);
  return (
    <li className="px-4 py-3">
      <div className="flex items-center gap-1.5">
        <VerdictChip verdict={sentence.verdict} score={sentence.score} />
        <div className="ml-auto flex flex-wrap justify-end gap-1">
          {sentence.sourceIndexes.map((n) => {
            const exists = sources.some((s) => s.index === n);
            return (
              <button
                key={n}
                type="button"
                disabled={!exists}
                aria-expanded={open === n}
                aria-label={`Show source ${n}`}
                onClick={() => setOpen((cur) => (cur === n ? null : n))}
                className={cn(
                  "grid h-5 min-w-5 place-items-center rounded-md px-1 text-[10.5px] font-semibold tabular-nums transition-colors focus-visible:outline-2 disabled:opacity-40",
                  open === n ? "bg-foreground text-background" : "bg-muted text-muted-foreground hover:bg-accent-soft/30 hover:text-foreground",
                )}
              >
                {n}
              </button>
            );
          })}
        </div>
      </div>
      {onLocate ? (
        <button
          type="button"
          onClick={() => onLocate(index)}
          className="group/claim mt-1.5 block w-full rounded-md text-left font-serif text-[13.5px] leading-snug text-foreground/90 transition-colors hover:text-foreground focus-visible:outline-2"
          title="Show in answer"
        >
          <span className="line-clamp-3">{text}</span>
          <span className="mt-1 inline-flex items-center gap-1 font-sans text-[11px] text-muted-foreground opacity-0 transition-opacity group-hover/claim:opacity-100 group-focus-visible/claim:opacity-100">
            <LocateFixed className="size-3" /> Show in answer
          </span>
        </button>
      ) : (
        <p className="mt-1.5 line-clamp-3 font-serif text-[13.5px] leading-snug text-foreground/90">{text}</p>
      )}
      {shown && (
        <div className="mt-2 rounded-lg border bg-card p-2.5">
          <SourcePreview source={shown} />
        </div>
      )}
    </li>
  );
}

interface VerificationBadgeProps {
  verification: Verification;
  sources: Source[];
  highlight: boolean;
  onHighlightChange: (on: boolean) => void;
  onLocate?: (index: number) => boolean;
  /** How many claims could be mapped onto the rendered answer (null = not computed). */
  mapped?: { count: number; total: number } | null;
}

/** "Grounded · 92%" pill with a popover: score bar, verdict counts, highlight toggle and every claim. */
export function VerificationBadge({ verification: v, sources, highlight, onHighlightChange, onLocate, mapped }: VerificationBadgeProps) {
  const [open, setOpen] = useState(false);
  const locating = useRef(false);
  const tone = toneOf(v);
  const canHighlight = supportsHighlights();
  const label = verificationLabel(v);

  const locate = onLocate
    ? (i: number) => {
        if (!highlight && canHighlight) onHighlightChange(true);
        locating.current = true;
        setOpen(false);
        // Let the highlight effect map the claims (and the popover close) first.
        setTimeout(() => onLocate(i), 120);
      }
    : undefined;

  const counts: { key: Verdict; n: number }[] = [
    { key: "supported", n: v.supported },
    { key: "partial", n: v.partial },
    { key: "unsupported", n: v.unsupported },
    { key: "uncited", n: v.uncited },
  ];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Answer check: ${label}. Show claims`}
          className={cn(
            "inline-flex h-7 max-w-full items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold ring-1 transition-[filter,box-shadow] ring-inset hover:brightness-105 focus-visible:outline-2 dark:hover:brightness-110",
            TONE_CLASS[tone],
          )}
        >
          <ToneIcon v={v} className="size-3.5 shrink-0" />
          <span className="truncate">{label}</span>
          {highlight && <Highlighter className="size-3 shrink-0 opacity-70" aria-label="(claims highlighted)" />}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        collisionPadding={12}
        onCloseAutoFocus={(e) => {
          // Returning focus to the badge would scroll the answer away from the claim being shown.
          if (locating.current) e.preventDefault();
          locating.current = false;
        }}
        className="scrollbar-thin max-h-(--radix-popover-content-available-height) w-[min(25rem,calc(100vw-1.5rem))] gap-0 overflow-x-hidden overflow-y-auto p-0"
      >
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-3">
            <span className={cn("grid size-9 shrink-0 place-items-center rounded-xl ring-1 ring-inset", TONE_CLASS[tone])}>
              <ToneIcon v={v} className="size-4.5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">Answer check</p>
              <p className="truncate text-xs text-muted-foreground first-letter:uppercase">{v.label}</p>
            </div>
            {tone !== "none" && (
              <div className="font-brand text-[1.7rem] leading-none font-semibold tabular-nums">{percent(v.score)}</div>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {checkable(v)} checkable claim{checkable(v) === 1 ? "" : "s"}
            {v.uncited ? ` · ${v.uncited} without citation${v.uncited === 1 ? "" : "s"}` : ""} — each cited sentence is tested for
            entailment against its sources.
          </p>
          <div className="space-y-1.5">
            <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden>
              <span className={cn("h-full rounded-full transition-[width] duration-700", TONE_BAR[tone])} style={{ width: percent(v.score) }} />
            </div>
            <ScoreBar v={v} />
          </div>
          <div className="grid grid-cols-2 gap-1.5 min-[400px]:grid-cols-4">
            {counts.map((c) => (
              <div key={c.key} className="rounded-lg bg-muted/60 px-2 py-1.5 text-center">
                <div className="text-sm font-semibold tabular-nums">{c.n}</div>
                <div className="flex items-center justify-center gap-1 text-[10.5px] text-muted-foreground">
                  <span className={cn("size-1.5 rounded-full", VERDICT_INFO[c.key].dot)} aria-hidden />
                  {VERDICT_INFO[c.key].label}
                </div>
              </div>
            ))}
          </div>
          <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2 text-sm">
            <Highlighter className="size-4 text-muted-foreground" />
            <span className="flex-1">
              Highlight claims
              <span className="block text-[11px] text-muted-foreground">
                {!canHighlight
                  ? "Needs a newer browser (CSS highlights)."
                  : highlight && mapped
                    ? `${mapped.count} of ${mapped.total} sentences marked in the answer`
                    : "Underline sentences in the answer by verdict"}
              </span>
            </span>
            <Switch checked={highlight && canHighlight} disabled={!canHighlight} onCheckedChange={onHighlightChange} />
          </label>
        </div>
        {v.sentences.length > 0 && (
          <ol className="divide-y border-t">
            {v.sentences.map((s, i) => (
              <ClaimItem key={`${i}-${s.start}`} sentence={s} index={i} sources={sources} onLocate={locate} />
            ))}
          </ol>
        )}
        <div className="flex items-center gap-1.5 border-t bg-muted/40 px-4 py-2 text-[11px] text-muted-foreground">
          <Info className="size-3 shrink-0" />
          <span className="min-w-0 truncate">
            Entailment check{v.model ? ` · ${v.model}` : ""}
          </span>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** Small floating card for the highlighted claim under the pointer. */
export function ClaimTooltip({ hovered, sources }: { hovered: HoveredClaim | null; sources: Source[] }) {
  if (!hovered) return null;
  const { sentence } = hovered.claim;
  const cited = sentence.sourceIndexes
    .map((n) => sources.find((s) => s.index === n))
    .filter((s): s is Source => !!s);
  const left = Math.min(hovered.x + 12, window.innerWidth - 272);
  const top = hovered.y + 18 + 120 > window.innerHeight ? hovered.y - 128 : hovered.y + 18;
  return createPortal(
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 w-64 rounded-lg bg-popover p-2.5 text-xs text-popover-foreground shadow-lg ring-1 ring-foreground/10"
      style={{ left: Math.max(8, left), top: Math.max(8, top) }}
    >
      <VerdictChip verdict={sentence.verdict} score={sentence.score} />
      <p className="mt-1.5 text-muted-foreground">{VERDICT_INFO[sentence.verdict].hint}</p>
      {cited.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {cited.slice(0, 3).map((s) => (
            <li key={s.index} className="flex items-center gap-1.5 truncate">
              <span className="rounded bg-muted px-1 text-[10px] font-semibold tabular-nums">{s.index}</span>
              <span className="truncate">{s.title}</span>
            </li>
          ))}
        </ul>
      )}
    </div>,
    document.body,
  );
}
