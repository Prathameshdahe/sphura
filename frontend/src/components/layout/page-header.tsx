import type { ReactNode } from "react";
import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { EASE_OUT } from "@/lib/motion";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: ReactNode;
  /** One line. */
  subtitle?: ReactNode;
  icon?: LucideIcon;
  /** Primary action (a Button), right-aligned; wraps under the title on phones. */
  action?: ReactNode;
  className?: string;
}

/**
 * The one page header (FINANCE_PLAN §4): same height everywhere — brand-serif title, a one-line subtitle and the
 * page's primary action. Pages render it inside <Page>, which supplies the scroll container and the mobile top bar.
 */
export function PageHeader({ title, subtitle, icon: Icon, action, className }: PageHeaderProps) {
  return (
    <motion.header
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: EASE_OUT }}
      className={cn("flex min-h-[4.5rem] flex-wrap items-end justify-between gap-x-6 gap-y-3 pt-2 pb-6 sm:pt-3", className)}
    >
      <div className="flex min-w-0 items-center gap-3.5">
        {Icon && (
          <span className="hidden size-10 shrink-0 place-items-center rounded-xl border bg-card text-muted-foreground shadow-xs sm:grid" aria-hidden>
            <Icon className="size-[18px]" strokeWidth={1.75} />
          </span>
        )}
        <div className="min-w-0">
          <h1 className="truncate font-brand text-[1.8rem] leading-[1.1] font-light tracking-[-0.03em] sm:text-[2.3rem]">{title}</h1>
          {subtitle && <p className="mt-1 line-clamp-2 text-sm text-muted-foreground sm:line-clamp-1">{subtitle}</p>}
        </div>
      </div>
      {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
    </motion.header>
  );
}
