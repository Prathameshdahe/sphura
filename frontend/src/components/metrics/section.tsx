import type { ComponentProps, ReactNode, ComponentType } from "react";
import { motion } from "framer-motion";
import { Check, CircleAlert, Copy, RotateCcw, Terminal, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCopy } from "@/hooks/use-copy";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Card surface used across the studio pages (radius --radius, equal padding). */
export function Panel({ className, children, ...rest }: ComponentProps<"div">) {
  return (
    <div className={cn("min-w-0 overflow-hidden rounded-2xl border bg-card shadow-xs", className)} {...rest}>
      {children}
    </div>
  );
}

export function PanelHeader({ title, description, action, className }: { title: ReactNode; description?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 pt-4 sm:px-5 sm:pt-5", className)}>
      <div className="min-w-0">
        <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

interface SectionProps {
  id: string;
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  description: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}

/** One dashboard section: numbered eyebrow, serif title, one-line explanation, actions. */
export function Section({ id, icon: Icon, eyebrow, title, description, actions, children }: SectionProps) {
  return (
    <motion.section
      id={id}
      aria-labelledby={`${id}-title`}
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="scroll-mt-16"
    >
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 max-w-2xl">
          <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
            <span className="grid size-5 place-items-center rounded-md border bg-card text-brand">
              <Icon className="size-3" aria-hidden />
            </span>
            {eyebrow}
          </div>
          <h2 id={`${id}-title`} className="mt-2 font-brand text-2xl font-normal tracking-[-0.01em] sm:text-[1.7rem]">
            {title}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      <div className="mt-5">{children}</div>
    </motion.section>
  );
}

export function SectionSkeleton({ tiles = 4, chart = true }: { tiles?: number; chart?: boolean }) {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading">
      {tiles > 0 && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: tiles }, (_, i) => (
            <Panel key={i} className="space-y-3 p-4">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-7 w-24" />
              <Skeleton className="h-3 w-16" />
            </Panel>
          ))}
        </div>
      )}
      {chart && (
        <Panel className="p-5">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-4 h-56 w-full" />
        </Panel>
      )}
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  return (
    <Panel role="alert" className={cn("flex flex-col items-center gap-2 px-6 py-10 text-center", className)}>
      <CircleAlert className="size-6 text-destructive" aria-hidden />
      <p className="max-w-md text-sm text-muted-foreground">{errorMessage(error)}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-1" onClick={onRetry}>
          <RotateCcw /> Retry
        </Button>
      )}
    </Panel>
  );
}

function CommandLine({ command }: { command: string }) {
  const { copied, copy } = useCopy();
  return (
    <div className="group/cmd flex items-center gap-2 rounded-lg border bg-code py-1.5 pr-1.5 pl-3 font-mono text-xs">
      <span className="text-muted-foreground select-none" aria-hidden>
        $
      </span>
      <code className="min-w-0 flex-1 break-all">{command}</code>
      <button
        type="button"
        onClick={() => void copy(command)}
        aria-label={copied ? "Copied" : `Copy command: ${command}`}
        className="grid size-7 shrink-0 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
    </div>
  );
}

/** `{available: false}` → explain how to produce the artefact (optional CLI commands) + optional in-app action. */
export function NotAvailable({ title, description, commands = [], action }: { title: string; description: ReactNode; commands?: string[]; action?: ReactNode }) {
  return (
    <Panel className="relative overflow-hidden px-5 py-8 sm:px-8">
      <div className="relative mx-auto max-w-xl text-center">
        <div className="mx-auto grid size-10 place-items-center rounded-xl border bg-muted/60 text-muted-foreground">
          <Terminal className="size-[18px]" strokeWidth={1.75} aria-hidden />
        </div>
        <h3 className="mt-4 font-brand text-xl font-normal">{title}</h3>
        <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>
        {commands.length > 0 && (
          <div className="mt-5 space-y-2 text-left">
            {commands.map((c) => (
              <CommandLine key={c} command={c} />
            ))}
          </div>
        )}
        {action && <div className="mt-5 flex justify-center">{action}</div>}
      </div>
    </Panel>
  );
}

interface EmptyStateProps {
  icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  title: ReactNode;
  children?: ReactNode;
  /** Primary action (usually one Button). */
  action?: ReactNode;
  /** Small print under the action. */
  footnote?: ReactNode;
  className?: string;
}

/** Calm empty state for the studio pages: quiet icon tile, serif heading, one muted line, optional action. */
export function EmptyState({ icon: Icon, title, children, action, footnote, className }: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className={cn("rounded-2xl border bg-card px-6 py-12 text-center", className)}
    >
      <div className="mx-auto grid size-12 place-items-center rounded-2xl border bg-accent text-accent-ink">
        <Icon className="size-[22px]" strokeWidth={1.9} aria-hidden />
      </div>
      <h2 className="mt-4 font-brand text-xl font-light tracking-[-0.025em] sm:text-[1.6rem]">{title}</h2>
      {children && <div className="mx-auto mt-1.5 max-w-md text-sm text-balance text-muted-foreground">{children}</div>}
      {action && <div className="mt-6 flex flex-wrap justify-center gap-2">{action}</div>}
      {footnote && <p className="mx-auto mt-3 max-w-md text-xs text-muted-foreground">{footnote}</p>}
    </motion.div>
  );
}
