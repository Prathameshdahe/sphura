import { Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { Glyph } from "@/components/icons/glyphs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SPRING_SNAPPY } from "@/lib/motion";
import { SPACES, spaceIndex, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { useUi } from "@/stores/ui";

/** Chat returns to the conversation you had open; every other space is its own page. */
function useSpaceHref() {
  const lastChatPath = useUi((s) => s.lastChatPath);
  return (s: NavItem) => (s.to === "/" ? lastChatPath : s.to);
}

export type TaskbarLabels = "all" | "active" | "none";

/**
 * The taskbar: one floating pill with every space inline (crisp glyph + small uppercase label) and a filled
 * "New chat" pill at its end. The active space sits on a soft chip that slides between items. Narrow screens
 * show icons only and, if it ever has to, the row scrolls inside the pill.
 */
export function SpaceTaskbar({ labels = "all", newChatLabel = true, className }: { labels?: TaskbarLabels; newChatLabel?: boolean; className?: string }) {
  const { pathname } = useLocation();
  const current = spaceIndex(pathname);
  const href = useSpaceHref();
  const tight = labels === "none";

  return (
    <nav aria-label="Spaces" className={cn("min-w-0 max-w-full", className)}>
      <div className="flex min-w-0 items-center gap-1 rounded-full border bg-card/90 p-1 shadow-soft backdrop-blur-md">
        <ul className="flex min-w-0 items-center gap-0.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {SPACES.map((s, i) => {
            const active = i === current;
            const showLabel = labels === "all" || (labels === "active" && active);
            const link = (
              <Link
                to={href(s)}
                aria-current={active ? "page" : undefined}
                aria-label={s.title}
                className={cn(
                  "relative flex h-8 shrink-0 items-center gap-1.5 rounded-full text-[11px] font-semibold tracking-[0.12em] uppercase transition-colors duration-150 focus-visible:outline-2 focus-visible:-outline-offset-2 active:scale-[0.96] motion-reduce:active:scale-100",
                  tight ? "px-1.5" : "px-2.5",
                  active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="taskbar-active"
                    className="absolute inset-0 rounded-full bg-accent ring-1 ring-brand/35 ring-inset"
                    transition={SPRING_SNAPPY}
                    aria-hidden
                  />
                )}
                <s.icon className={cn("relative size-[17px] shrink-0", active && "text-accent-ink")} strokeWidth={1.9} />
                {showLabel && <span className="relative whitespace-nowrap">{s.label}</span>}
              </Link>
            );
            return (
              <li key={s.to} className="shrink-0">
                {showLabel ? (
                  link
                ) : (
                  <Tooltip>
                    <TooltipTrigger asChild>{link}</TooltipTrigger>
                    <TooltipContent side="bottom">{s.title}</TooltipContent>
                  </Tooltip>
                )}
              </li>
            );
          })}
        </ul>
        <motion.div whileTap={{ scale: 0.95 }} transition={SPRING_SNAPPY} className="shrink-0">
          <Link
            to="/"
            state={{ fresh: true }}
            aria-label="New chat"
            className={cn(
              "flex h-8 items-center gap-1.5 rounded-full bg-primary text-[11px] font-bold tracking-[0.12em] text-primary-foreground uppercase shadow-xs transition-[filter] hover:bg-[color-mix(in_oklch,var(--primary),black_10%)] focus-visible:outline-2",
              newChatLabel ? "pr-3.5 pl-2.5" : "w-8 justify-center",
            )}
          >
            <Glyph name="plus" className="size-4" strokeWidth={2.4} />
            {newChatLabel && <span>New chat</span>}
          </Link>
        </motion.div>
      </div>
    </nav>
  );
}
