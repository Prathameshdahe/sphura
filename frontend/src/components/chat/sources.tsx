import { useState } from "react";
import { ArrowUpRight, FileText } from "lucide-react";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { domainOf } from "@/lib/format";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

const hue = (s: string) => {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
};

function sourceLabel(s: Source): string {
  if (s.type === "web") return s.domain || domainOf(s.url) || s.title;
  return s.filename || s.title;
}

/** Letter tile instead of a remote favicon (no third-party requests). */
export function SourceIcon({ source, className }: { source: Source; className?: string }) {
  if (source.type === "doc") {
    return (
      <span className={cn("grid size-4 shrink-0 place-items-center rounded-full bg-accent text-brand", className)}>
        <FileText className="size-2.5" />
      </span>
    );
  }
  const label = sourceLabel(source);
  return (
    <span
      aria-hidden
      className={cn("grid size-4 shrink-0 place-items-center rounded-full font-sans text-[9px] font-semibold text-white uppercase", className)}
      style={{ background: `oklch(0.58 0.11 ${hue(label)})` }}
    >
      {label.slice(0, 1)}
    </span>
  );
}

export function SourcePreview({ source }: { source: Source }) {
  const where = source.type === "web" ? sourceLabel(source) : `${source.filename ?? "Document"}${source.page ? ` · page ${source.page}` : ""}`;
  return (
    <div className="space-y-1.5 font-sans">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <SourceIcon source={source} />
        <span className="truncate">{where}</span>
        <span className="ml-auto shrink-0 rounded bg-muted px-1.5 py-px text-[10px] font-medium tabular-nums">{source.index}</span>
      </div>
      <div className="line-clamp-2 text-sm leading-snug font-medium text-foreground">{source.title}</div>
      {source.snippet && (
        <p className="line-clamp-4 font-serif text-[13px] leading-relaxed text-muted-foreground">{source.snippet}</p>
      )}
      {source.type === "web" && source.url && (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 pt-0.5 text-xs font-medium text-foreground hover:underline"
        >
          Open source <ArrowUpRight className="size-3" />
        </a>
      )}
    </div>
  );
}

/** Inline [n] chip with a hover preview. */
export function CitationChip({ source }: { source: Source }) {
  const chip =
    "sphura-cite relative -top-[0.32em] mx-px inline-flex h-[1.2rem] min-w-[1.2rem] items-center justify-center rounded-md bg-muted px-1 align-baseline font-sans text-[0.68rem] leading-none font-semibold text-muted-foreground tabular-nums no-underline transition-colors hover:bg-accent-soft/30 hover:text-foreground focus-visible:outline-2";
  return (
    <HoverCard openDelay={120} closeDelay={80}>
      <HoverCardTrigger asChild>
        {source.type === "web" && source.url ? (
          <a href={source.url} target="_blank" rel="noopener noreferrer" className={chip} data-sphura-cite="" aria-label={`Source ${source.index}: ${source.title}`}>
            {source.index}
          </a>
        ) : (
          <button type="button" className={chip} data-sphura-cite="" aria-label={`Source ${source.index}: ${source.title}`}>
            {source.index}
          </button>
        )}
      </HoverCardTrigger>
      <HoverCardContent side="top" collisionPadding={12} className="w-[min(20rem,calc(100vw-1.5rem))] p-3">
        <SourcePreview source={source} />
      </HoverCardContent>
    </HoverCard>
  );
}

const COLLAPSED = 4;

export function SourcesRow({ sources }: { sources: Source[] }) {
  const [expanded, setExpanded] = useState(false);
  if (sources.length === 0) return null;
  const shown = expanded ? sources : sources.slice(0, COLLAPSED);
  const hidden = sources.length - shown.length;

  return (
    <div className="mt-5">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        Sources
        <span className="grid h-[18px] min-w-[18px] place-items-center rounded-full bg-muted px-1 text-[10.5px] font-semibold tabular-nums">{sources.length}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {shown.map((s) => {
          const inner = (
            <>
              <span className="text-[10px] font-semibold text-muted-foreground tabular-nums">{s.index}</span>
              <SourceIcon source={s} />
              <span className="truncate">{sourceLabel(s)}</span>
              {s.type === "doc" && s.page ? <span className="shrink-0 text-muted-foreground">p.{s.page}</span> : null}
            </>
          );
          const cls =
            "flex max-w-[15rem] items-center gap-1.5 rounded-full border bg-card py-1 pr-2.5 pl-1.5 text-xs text-foreground/90 shadow-xs transition-[color,background-color,border-color,transform] hover:-translate-y-px hover:border-brand/25 hover:bg-card focus-visible:outline-2 motion-reduce:hover:translate-y-0";
          return (
            <HoverCard key={`${s.index}-${s.title}`} openDelay={150} closeDelay={80}>
              <HoverCardTrigger asChild>
                {s.type === "web" && s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className={cls}>
                    {inner}
                  </a>
                ) : (
                  <button type="button" className={cls}>
                    {inner}
                  </button>
                )}
              </HoverCardTrigger>
              <HoverCardContent side="top" align="start" collisionPadding={12} className="w-[min(20rem,calc(100vw-1.5rem))] p-3">
                <SourcePreview source={s} />
              </HoverCardContent>
            </HoverCard>
          );
        })}
        {sources.length > COLLAPSED && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="rounded-full border border-dashed px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            {expanded ? "Show less" : `+${hidden} more`}
          </button>
        )}
      </div>
    </div>
  );
}
