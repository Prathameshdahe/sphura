import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { KeyRound } from "lucide-react";
import { SpecialistDock } from "@/components/layout/workplace-dock";
import { SphuraLogo } from "@/components/ui/sphura-logo";
import { firstName, greeting } from "@/lib/format";
import { EASE_OUT, SPRING_SNAPPY } from "@/lib/motion";
import { STARTERS, type Starter } from "@/lib/starters";
import type { ModelInfo } from "@/lib/types";

interface WelcomeProps {
  name?: string | null;
  composer: ReactNode;
  onStarter: (starter: Starter) => void;
  /** Models list when none are available (shows setup hints). */
  unavailable?: ModelInfo[] | null;
}

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6, transition: { duration: 0.15 } },
  transition: { duration: 0.32, delay, ease: EASE_OUT },
});

/** Home screen: the block-S assembling, a serif greeting, the composer (robot on top) and starter chips. */
export function Welcome({ name, composer, onStarter, unavailable }: WelcomeProps) {
  const first = firstName(name);
  const reasons = [...new Set((unavailable ?? []).map((m) => m.reason).filter((r): r is string => !!r))].slice(0, 3);

  return (
    <div className="relative flex w-full flex-col items-center text-center">
      <motion.div {...rise(0)} className="flex flex-col items-center gap-4 sm:flex-row sm:gap-3.5">
        <SphuraLogo size={44} intro />
        <h1 className="font-brand text-[2.4rem] leading-[1.02] font-bold tracking-[-0.04em] text-balance sm:text-[3.3rem]">
          <span className="ink-gradient-text">
            {greeting()}
            {first ? "," : ""}
          </span>
          {first && <span className="sphura-gradient-text"> {first}</span>}
        </h1>
      </motion.div>
      <motion.p {...rise(0.06)} className="mt-3 max-w-md text-[15px] text-balance text-muted-foreground">
        Loans, tax, budgets, markets or your own statements. Ask, and Sphura works it out with tools and shows its sources.
      </motion.p>

      {unavailable && (
        <motion.div
          {...rise(0.1)}
          className="mt-5 flex w-full max-w-xl items-start gap-3 rounded-2xl border border-warning/30 bg-warning/8 px-4 py-3 text-left text-sm"
        >
          <KeyRound className="mt-0.5 size-4 shrink-0 text-warning" />
          <div>
            <p className="font-medium">No AI model is available yet</p>
            <p className="mt-0.5 text-muted-foreground">
              {reasons.length > 0 ? reasons.join(" · ") : "Add a GEMINI_API_KEY or GROQ_API_KEY to the server, or start Ollama, then reload."}
            </p>
          </div>
        </motion.div>
      )}

      <div className="mt-7 w-full text-left">{composer}</div>

      <motion.div {...rise(0.14)} className="mt-5 flex w-full justify-center">
        <SpecialistDock />
      </motion.div>

      <motion.ul
        className="mt-4 flex w-full flex-wrap justify-center gap-1.5"
        aria-label="Try one of these"
        initial="hidden"
        animate="show"
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.045, delayChildren: 0.18 } } }}
      >
        {STARTERS.map((s) => (
          <motion.li
            key={s.id}
            variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0, transition: { duration: 0.26, ease: EASE_OUT } } }}
          >
            <motion.button
              type="button"
              onClick={() => onStarter(s)}
              title={s.body}
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.96 }}
              transition={SPRING_SNAPPY}
              className="group inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2"
            >
              <s.icon className="size-4 text-accent-ink transition-transform group-hover:scale-110" />
              {s.title}
            </motion.button>
          </motion.li>
        ))}
      </motion.ul>

      <motion.p {...rise(0.32)} className="mt-6 text-[11.5px] text-muted-foreground">
        Educational only. Sphura is not a registered investment adviser.
      </motion.p>
    </div>
  );
}
