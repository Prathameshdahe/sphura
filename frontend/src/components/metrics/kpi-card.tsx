import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, Minus, type LucideIcon } from "lucide-react";
import { CountUp } from "@/components/motion";
import { cn } from "@/lib/utils";
import { Panel } from "./section";

export interface KpiDelta {
  /** Display text, e.g. "+12.3 pp vs keyword rules". */
  text: string;
  /** Sign of the change (direction of the arrow). */
  direction: "up" | "down" | "flat";
  /** Whether this change is good news (colour of the chip). Defaults to up = good. */
  good?: boolean;
}

interface KpiCardProps {
  label: string;
  /** A number counts up from its previous value; anything else renders as-is. */
  value: ReactNode | number;
  /** Formats a numeric `value` ("₹12.3K", "94.2%"). */
  format?: (n: number) => string;
  icon?: LucideIcon;
  hint?: ReactNode;
  delta?: KpiDelta | null;
  /** Accent-coloured value text for the headline tile. */
  accent?: boolean;
  className?: string;
}

/** Stat tile: label, big tabular number (count-up), optional delta chip and hint. Equal height in a grid. */
export function KpiCard({ label, value, format, icon: Icon, hint, delta, accent, className }: KpiCardProps) {
  const good = delta ? (delta.good ?? delta.direction === "up") : false;
  const Arrow = delta?.direction === "up" ? ArrowUpRight : delta?.direction === "down" ? ArrowDownRight : Minus;
  return (
    <Panel className={cn("flex h-full min-w-0 flex-col gap-1.5 p-4 transition-colors hover:border-foreground/15", className)}>
      <div className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground">
        <span className="truncate">{label}</span>
        {Icon && <Icon className="size-3.5 shrink-0" aria-hidden />}
      </div>
      <div
        className={cn(
          "truncate font-brand text-[1.35rem] leading-tight font-normal tracking-[-0.01em] tabular-nums min-[380px]:text-2xl sm:text-[1.65rem]",
          accent && "text-brand",
        )}
      >
        {typeof value === "number" ? <CountUp value={value} format={format} /> : value}
      </div>
      {delta && (
        <div
          className={cn(
            "inline-flex w-fit max-w-full items-start gap-1 rounded-xl px-1.5 py-0.5 text-[11px] leading-tight font-medium",
            delta.direction === "flat" ? "bg-muted text-muted-foreground" : good ? "bg-success/12 text-success" : "bg-danger/12 text-danger",
          )}
        >
          <Arrow className="mt-px size-3 shrink-0" aria-hidden />
          <span>{delta.text}</span>
        </div>
      )}
      {hint && <div className="mt-auto text-xs text-muted-foreground">{hint}</div>}
    </Panel>
  );
}
