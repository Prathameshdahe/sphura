import { memo, useMemo, useRef } from "react";
import { Check, CircleAlert, Copy, OctagonX, RefreshCw, RotateCcw } from "lucide-react";
import { extractArtifacts } from "@/components/artifacts/artifact-utils";
import { FeedbackButtons } from "@/components/chat/feedback";
import { Markdown } from "@/components/chat/markdown";
import { h2Headings, isVerifying, readMessageMeta } from "@/components/chat/message-meta";
import { MetaChips } from "@/components/chat/meta-chips";
import { ReportHeader } from "@/components/chat/report-header";
import { SourcesRow } from "@/components/chat/sources";
import { StatusLine, StepsTimeline } from "@/components/chat/steps";
import { ClaimTooltip, VerificationBadge, VerificationPending, VerifyButton } from "@/components/chat/verification";
import { Glyph } from "@/components/icons/glyphs";
import { IconButton } from "@/components/icon-button";
import { Button } from "@/components/ui/button";
import { SphuraLogo } from "@/components/ui/sphura-logo";
import { ReadAloud } from "@/components/voice/read-aloud";
import { useClaimHighlights } from "@/hooks/use-claim-highlights";
import { useCopy } from "@/hooks/use-copy";
import { formatDuration } from "@/lib/format";
import type { Message } from "@/lib/types";
import { cn } from "@/lib/utils";
import { verificationFromMeta } from "@/lib/verification";
import { useArtifactPanel } from "@/stores/artifacts";
import type { ChatStream } from "@/stores/chat-store";
import { usePrefs } from "@/stores/prefs";
import { useSpeech } from "@/stores/speech";

interface AssistantMessageProps {
  /** Saved message; absent while the answer is still streaming. */
  message?: Message | null;
  stream?: ChatStream | null;
  isLast: boolean;
  /** A stream is running in this conversation (regenerate/retry disabled). */
  busy: boolean;
  justCompleted: boolean;
  modelLabel: string | null;
  /** Label of meta.fallbackFrom, when the first model failed. */
  fallbackLabel?: string | null;
  onRegenerate?: () => void;
}

export const AssistantMessage = memo(function AssistantMessage({
  message,
  stream,
  isLast,
  busy,
  justCompleted,
  modelLabel,
  fallbackLabel,
  onRegenerate,
}: AssistantMessageProps) {
  const { copied, copy } = useCopy();
  const answerRef = useRef<HTMLDivElement>(null);
  const live = !!stream;
  const id = message?.id ?? stream?.assistantMessageId ?? null;
  const text = stream ? stream.text : (message?.content ?? "");
  const sources = stream ? stream.sources : (message?.sources ?? []);
  const steps = stream ? stream.steps : (message?.steps ?? []);
  const status = message?.status ?? "complete";
  const phase = stream?.phase ?? null;
  const verifying = live && isVerifying(steps);
  // Once the claim check starts the answer is written: its chip (then badge) replaces the status line.
  const checked = steps.some((s) => s.name === "verify");
  const showStatus = live && (!text || (!checked && phase !== null && phase !== "composing"));
  const canRetry = isLast && !busy && !!onRegenerate;

  const meta = useMemo(() => readMessageMeta(message?.meta), [message?.meta]);
  const savedVerification = useMemo(() => verificationFromMeta(message?.meta), [message?.meta]);
  const verification = live ? (stream?.verification ?? null) : savedVerification;
  const speaking = useSpeech((s) => !!id && s.speakingId === id);
  const highlightPref = usePrefs((s) => s.highlightClaims);
  const setHighlight = usePrefs((s) => s.setHighlightClaims);
  const highlight = highlightPref && !!verification && !!text;
  const claims = useClaimHighlights(answerRef, id ?? "draft", verification, highlight, `${live}:${text.length}`);

  const artifacts = useMemo(() => (!live && id && text ? extractArtifacts(id, text) : []), [live, id, text]);
  // Long, structured answers (three or more sections) get a report banner with a table of contents.
  const headings = useMemo(() => (!live && status === "complete" ? h2Headings(text) : []), [live, status, text]);
  const words = useMemo(() => (headings.length >= 3 ? text.split(/\s+/).length : 0), [headings.length, text]);
  const showReport = headings.length >= 3 && words >= 350;
  // Sourced answer saved without a claim check (model still loading, or it timed out): offer one.
  const canVerify = !live && !verification && status === "complete" && !!text && sources.length > 0;

  const openArtifact = () => {
    const last = artifacts[artifacts.length - 1];
    if (last) useArtifactPanel.getState().show(last);
  };

  return (
    <div className="group/assistant flex gap-3 sm:gap-4">
      <div className="relative mt-0.5 grid size-7 shrink-0 place-items-center" aria-label={live ? (verifying ? "Sphura is checking its claims" : "Sphura is working") : undefined} role={live ? "status" : undefined}>
        <SphuraLogo size={26} state={live ? "thinking" : justCompleted ? "answer" : "static"} interactive={!live} />
      </div>

      <div className="min-w-0 flex-1 pt-0.5">
        {meta.ensemble && (
          <p
            className="mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[12.5px] text-muted-foreground"
            title={meta.ensemble.members.map((m) => `${m.label}${m.ok ? (m.ms != null ? ` · ${formatDuration(m.ms)}` : "") : " · failed"}`).join("; ")}
          >
            <Glyph name="merge" className="size-4 text-brand" />
            <span className="font-semibold text-foreground">Sphura Ensemble</span>
            <span aria-hidden>·</span>
            <span>
              merged from {meta.ensemble.members.filter((m) => m.ok).length} model{meta.ensemble.members.filter((m) => m.ok).length === 1 ? "" : "s"}
            </span>
          </p>
        )}
        {showStatus && <StatusLine phase={phase} label={verifying ? "Checking claims against sources" : (stream?.label ?? null)} />}
        <StepsTimeline steps={steps} live={live} />

        {showReport && <ReportHeader headings={headings} sources={sources.length} words={words} answerRef={answerRef} />}

        {text ? (
          <div ref={answerRef} onPointerMove={claims.onPointerMove} onPointerLeave={claims.onPointerLeave}>
            <Markdown text={text} sources={sources} streaming={live} messageId={id ?? undefined} />
          </div>
        ) : !live && status === "complete" ? (
          <p className="text-sm text-muted-foreground italic">No response.</p>
        ) : null}

        {!live && status === "stopped" && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <OctagonX className="size-4" />
            <span>Response stopped</span>
            {canRetry && (
              <Button variant="ghost" size="xs" onClick={onRegenerate} className="text-foreground">
                <RotateCcw /> Retry
              </Button>
            )}
          </div>
        )}

        {!live && status === "error" && (
          <div className="mt-3 flex items-start gap-3 rounded-xl border border-destructive/25 bg-destructive/5 px-3.5 py-3 text-sm">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-foreground">Sphura couldn't finish this answer</p>
              <p className="mt-0.5 break-words text-muted-foreground">{message?.error || "Something went wrong."}</p>
            </div>
            {canRetry && (
              <Button variant="outline" size="sm" onClick={onRegenerate} className="shrink-0">
                <RotateCcw /> Retry
              </Button>
            )}
          </div>
        )}

        <SourcesRow sources={sources} />

        <div className="mt-3 flex flex-wrap items-center gap-1.5 empty:hidden">
          {verification ? (
            <VerificationBadge
              verification={verification}
              sources={sources}
              highlight={highlight}
              onHighlightChange={setHighlight}
              onLocate={claims.locate}
              mapped={claims.mapped}
            />
          ) : verifying && text ? (
            <VerificationPending />
          ) : canVerify && message ? (
            <VerifyButton messageId={message.id} conversationId={message.conversationId} />
          ) : null}
          {!live && (
            <MetaChips
              meta={message?.meta}
              fallbackLabel={fallbackLabel}
              artifactCount={artifacts.length}
              onOpenArtifact={openArtifact}
            />
          )}
        </div>

        {!live && (
          <div
            className={cn(
              "mt-2 -ml-1.5 flex flex-wrap items-center gap-0.5 text-muted-foreground transition-opacity",
              !isLast && !speaking && "md:opacity-0 md:group-hover/assistant:opacity-100 md:focus-within:opacity-100",
            )}
          >
            {text && (
              <IconButton label={copied ? "Copied" : "Copy"} onClick={() => void copy(text)}>
                {copied ? <Check /> : <Copy />}
              </IconButton>
            )}
            {text && id && <ReadAloud id={id} text={text} />}
            {id && message && <FeedbackButtons messageId={id} />}
            {isLast && onRegenerate && status === "complete" && (
              <IconButton label="Regenerate" onClick={onRegenerate} disabled={busy}>
                <RefreshCw />
              </IconButton>
            )}
            {(modelLabel || meta.durationMs) && (
              <span className="ml-1.5 truncate text-xs">
                {modelLabel}
                {modelLabel && meta.durationMs ? " · " : ""}
                {meta.durationMs ? formatDuration(meta.durationMs) : ""}
              </span>
            )}
          </div>
        )}
      </div>
      {highlight && <ClaimTooltip hovered={claims.hovered} sources={sources} />}
    </div>
  );
});
