import { useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { SphuraLogo } from "@/components/ui/sphura-logo";
import { EASE_OUT } from "@/lib/motion";

/** Calm single-column auth frame: mark in the corner, serif title, the form on a white card, a quiet footer. */
export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  useEffect(() => {
    document.title = `${title} · Sphura`;
    return () => {
      document.title = "Sphura";
    };
  }, [title]);

  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="pt-safe mx-auto flex h-16 w-full max-w-6xl shrink-0 items-center px-4 sm:px-6">
        <Link to="/welcome" aria-label="Sphura home" className="rounded-md text-foreground focus-visible:outline-2">
          <SphuraLogo size={30} withWordmark caption intro />
        </Link>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-4 pt-4 pb-12 sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, ease: EASE_OUT }}
          className="w-full max-w-[25rem]"
        >
          <div className="text-center">
            <h1 className="font-brand text-[2.1rem] leading-[1.1] font-normal tracking-[-0.015em] text-balance sm:text-[2.4rem]">{title}</h1>
            <p className="mt-2.5 text-[15px] text-pretty text-muted-foreground">{subtitle}</p>
          </div>
          <div className="mt-8 rounded-2xl border bg-card p-5 shadow-soft sm:p-6">{children}</div>
          <div className="mt-6 text-center text-sm text-muted-foreground">{footer}</div>
        </motion.div>
      </main>

      <footer className="pb-safe px-4 text-center text-xs text-muted-foreground">
        Educational only, not investment advice.
      </footer>
    </div>
  );
}
