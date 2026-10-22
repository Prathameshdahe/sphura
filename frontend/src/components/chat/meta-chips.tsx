import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Brain, ChartCandlestick, PanelRight, Table2, TriangleAlert } from "lucide-react";
import { readMessageMeta, type MessageMeta } from "@/components/chat/message-meta";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { confidencePct, labelMeta } from "@/lib/intents";
import { chipSpring } from "@/lib/motion";
import { cn } from "@/lib/utils";

const chip =
  "inline-flex h-7 max-w-full items-center gap-1.5 rounded-full border bg-card/60 px-2.5 text-[11.5px] font-medium text-muted-foreground transition-colors hover:border-foreground/15 hover:text-foreground focus-visible:outline-2";

function Chip({
  icon,
  children,
  to,
  onClick,
  tone,
  card,
  label,
}: {
  icon: ReactNode;
  children: ReactNode;
  to?: string;
  onClick?: () => void;
  tone?: "warn" | "brand";
  card?: ReactNode;
  label?: string;
}) {
  const cls = cn(
    chip,
    tone === "warn" && "border-warning/35 bg-warning/10 text-foreground",
    tone === "brand" && "border-brand/25 bg-brand/8 text-foreground",
  );
  const body = (
    <>
      {icon}
      <span className="truncate">{children}</span>
    </>
  );
  const el = to ? (
    <Link to={to} className={cls} aria-label={label}>
      {body}
    </Link>
  ) : (
    <button type="button" className={cls} onClick={onClick} aria-label={label}>
      {body}
    </button>
  );
  const sprung = (
    <motion.span {...chipSpring} className="inline-flex max-w-full">
      {el}
    </motion.span>
  );
  if (!card) return sprung;
  return (
    <HoverCard openDelay={150} closeDelay={80}>
      <HoverCardTrigger asChild>{sprung}</HoverCardTrigger>
      <HoverCardContent side="top" align="start" collisionPadding={12} className="w-[min(20rem,calc(100vw-1.5rem))] p-3 text-xs">
        {card}
      </HoverCardContent>
    </HoverCard>
  );
}

interface MetaChipsProps {
  meta: Record<string, unknown> | null | undefined;
  /** Label of meta.fallbackFrom (the model that failed). */
  fallbackLabel?: string | null;
  /** Artifacts in this answer: opens the newest one. */
  artifactCount?: number;
  onOpenArtifact?: () => void;
}

/** Subtle chips under an answer: router intent + confidence, analytics, market data, memory, model fallback. */
export function MetaChips({ meta, fallbackLabel, artifactCount = 0, onOpenArtifact }: MetaChipsProps) {
  const m: MessageMeta = readMessageMeta(meta);
  const items: ReactNode[] = [];

  if (artifactCount > 0 && onOpenArtifact) {
    items.push(
      <Chip key="artifact" icon={<PanelRight className="size-3.5" />} onClick={onOpenArtifact} label="Open artifact panel">
        {artifactCount === 1 ? "Open chart" : `${artifactCount} charts`}
      </Chip>,
    );
  }
  if (m.router) {
    const r = m.router;
    const { icon: Icon, title, action } = labelMeta(r.label);
    items.push(
      <Chip
        key="router"
        icon={<Icon className="size-3.5 text-brand" />}
        to="/lab"
        label={`Router: ${title}, ${confidencePct(r.confidence)} confident`}
        card={
          <div className="space-y-1">
            <p className="font-medium text-foreground">Intent router</p>
            <p className="text-muted-foreground">
              Sphura's trained classifier read this as a <b className="text-foreground">{title.toLowerCase()}</b> question with{" "}
              {confidencePct(r.confidence)} confidence. {action}.
            </p>
          </div>
        }
      >
        {title}
        <span className="text-muted-foreground/80"> · {confidencePct(r.confidence)}</span>
      </Chip>,
    );
  }
  if (m.analyticsDocs > 0) {
    items.push(
      <Chip key="analytics" icon={<Table2 className="size-3.5 text-brand" />} to="/dashboard" tone="brand">
        Analytics
        <span className="hidden text-muted-foreground sm:inline">
          {" "}
          · {m.analyticsDocs} {m.analyticsDocs === 1 ? "statement" : "statements"}
        </span>
      </Chip>,
    );
  }
  if (m.market) {
    const first = m.market.symbols[0];
    const text = first ?? m.market.name ?? "Market data";
    items.push(
      <Chip
        key="market"
        icon={<ChartCandlestick className="size-3.5 text-brand" />}
        to={first ? `/markets?symbol=${encodeURIComponent(first)}` : "/markets"}
        tone="brand"
        card={
          <p className="text-muted-foreground">
            Quotes are delayed yfinance data, cached for a minute. Open Markets for the chart and the latest news.
          </p>
        }
      >
        Market · {text}
        {m.market.symbols.length > 1 && <span className="text-muted-foreground"> +{m.market.symbols.length - 1}</span>}
      </Chip>,
    );
  }
  if (m.memoryUsed > 0) {
    items.push(
      <Chip key="mem" icon={<Brain className="size-3.5" />} to="/memory">
        Used {m.memoryUsed} {m.memoryUsed === 1 ? "memory" : "memories"}
      </Chip>,
    );
  }
  if (m.memoriesAdded.length > 0) {
    items.push(
      <Chip
        key="mem-added"
        icon={<Brain className="size-3.5 text-brand" />}
        to="/memory"
        card={
          <div>
            <p className="mb-1.5 font-medium text-foreground">Sphura will remember</p>
            <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
              {m.memoriesAdded.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </div>
        }
      >
        Memory updated
      </Chip>,
    );
  }
  if (m.fallbackFrom) {
    items.push(
      <Chip
        key="fallback"
        tone="warn"
        icon={<TriangleAlert className="size-3.5 text-warning" />}
        card={
          <p className="text-muted-foreground">
            {fallbackLabel || m.fallbackFrom} was unavailable or failed, so Sphura switched to another model to finish this answer.
          </p>
        }
      >
        <span className="sm:hidden">Fallback model</span>
        <span className="hidden sm:inline">Fallback from {fallbackLabel || m.fallbackFrom}</span>
      </Chip>,
    );
  }

  if (!items.length) return null;
  return <>{items}</>;
}
