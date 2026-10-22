import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useNow } from "@/hooks/use-now";
import { formatDuration } from "@/lib/format";

/** One tooltip row: swatch (identity), label and value in text ink — never the series colour. */
export function TooltipRow({ color, label, value }: { color?: string; label: ReactNode; value: ReactNode }) {
  return (
    <div className="flex w-full min-w-36 items-center gap-2">
      <span className="size-2.5 shrink-0 rounded-[2px]" style={{ background: color }} aria-hidden />
      <span className="flex-1 text-muted-foreground">{label}</span>
      <span className="font-mono font-medium text-foreground tabular-nums">{value}</span>
    </div>
  );
}

/** Long-running admin job (training / evaluation): indeterminate bar + live elapsed time. */
export function JobProgress({ label, detail, startedAt }: { label: string; detail?: string; startedAt: number }) {
  const now = useNow(true, 500);
  // `left` is not a transform, so MotionConfig's reducedMotion="user" would not stop the sweep by itself.
  const reduced = useReducedMotion() ?? false;
  return (
    <div role="status" aria-live="polite" className="rounded-xl border bg-muted/40 px-4 py-3">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="shimmer-text font-medium">{label}</span>
        <span className="font-mono text-xs text-muted-foreground tabular-nums">{formatDuration(startedAt > 0 ? Math.max(0, now - startedAt) : 0)}</span>
      </div>
      {detail && <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>}
      <div className="relative mt-2.5 h-1 overflow-hidden rounded-full bg-muted" aria-hidden>
        {reduced ? (
          <div className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-primary" />
        ) : (
          <motion.div
            className="absolute inset-y-0 w-1/3 rounded-full bg-primary"
            initial={{ left: "-35%" }}
            animate={{ left: "100%" }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
          />
        )}
      </div>
    </div>
  );
}
