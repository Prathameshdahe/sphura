import { useState, type RefObject } from "react";
import { ChevronRight, FileText, ListTree } from "lucide-react";
import { cn } from "@/lib/utils";
import "./chat-extras.css";

interface ReportHeaderProps {
  headings: string[];
  sources: number;
  words: number;
  /** The rendered answer: TOC entries scroll to its n-th <h2>. */
  answerRef: RefObject<HTMLElement | null>;
}

/** Banner for long, structured answers: reading stats and a table of contents built from the ## headings. */
export function ReportHeader({ headings, sources, words, answerRef }: ReportHeaderProps) {
  // Contents start open on wide screens, folded on phones.
  const [open, setOpen] = useState(() => window.matchMedia("(min-width: 640px)").matches);
  const minutes = Math.max(1, Math.round(words / 230));
  const stats = [`${headings.length} sections`, sources ? `${sources} sources` : null, `${minutes} min read`].filter(Boolean);

  const jump = (i: number) => {
    const h = answerRef.current?.querySelectorAll("h2")[i];
    if (!h) return;
    h.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    h.classList.add("sphura-flash");
    setTimeout(() => h.classList.remove("sphura-flash"), 1400);
  };

  return (
    <div className="relative mb-5 overflow-hidden rounded-2xl border bg-card/70">
      <div className="sphura-gradient-bg absolute inset-x-0 top-0 h-0.5 opacity-80" aria-hidden />
      <div className="flex items-center gap-3 px-4 pt-3.5 pb-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand/12 text-brand">
          <FileText className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold tracking-wider whitespace-nowrap text-muted-foreground uppercase">Report</p>
          <p className="line-clamp-2 text-xs text-muted-foreground">{stats.join(" · ")}</p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="inline-flex h-7 shrink-0 items-center gap-1 rounded-md px-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2"
        >
          <ListTree className="size-3.5" />
          <span className="hidden min-[400px]:inline">Contents</span>
          <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
        </button>
      </div>
      {open && (
        <nav aria-label="Report contents" className="border-t px-2 py-2">
          <ol className="grid gap-0.5 sm:grid-cols-2">
            {headings.map((h, i) => (
              <li key={`${i}-${h}`}>
                <button
                  type="button"
                  onClick={() => jump(i)}
                  className="flex w-full items-baseline gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] text-foreground/85 transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2"
                >
                  <span className="w-4 shrink-0 text-right text-[11px] font-semibold text-muted-foreground tabular-nums">{i + 1}</span>
                  <span className="line-clamp-1">{h}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
      )}
    </div>
  );
}
