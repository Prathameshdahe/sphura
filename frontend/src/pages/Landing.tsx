import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { animate, motion, useInView, useReducedMotion } from "framer-motion";
import { ArrowRight, ArrowUp } from "lucide-react";
import { GoogleButton } from "@/components/auth/google-button";
import { Glyph, type GlyphName } from "@/components/icons/glyphs";
import { HoverGrid } from "@/components/ui/hover-grid";
import { SphuraLogo } from "@/components/ui/sphura-logo";
import { EASE_OUT } from "@/lib/motion";
import { useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";

const YEAR = new Date().getFullYear();

/* ───────────────────────────── content ───────────────────────────── */

const FEATURES: { glyph: GlyphName; title: string; body: string }[] = [
  {
    glyph: "tools",
    title: "Calculations done by tools",
    body: "EMI, SIP growth and income tax are worked out by deterministic calculators, then explained in plain words, not estimated by a language model.",
  },
  {
    glyph: "dashboard",
    title: "Statements become a dashboard",
    body: "Upload a bank statement or a balance sheet as CSV or Excel to see cash flow by month, where the money goes and the key ratios.",
  },
  {
    glyph: "candles",
    title: "Markets, with context",
    body: "Delayed quotes and the recent trend, with finance news labelled positive, neutral or negative by a sentiment model.",
  },
  {
    glyph: "mic",
    title: "Hands-free voice",
    body: "Ask out loud and hear the answer read back, useful when your hands are full of receipts.",
  },
  {
    glyph: "shield",
    title: "Checked against its sources",
    body: "Every answer cites where its figures come from, and each cited claim is checked against that source before you rely on it.",
  },
];

const STEPS: { glyph: GlyphName; title: string; body: string }[] = [
  { glyph: "chat", title: "Your question", body: "Typed or spoken, in plain language." },
  { glyph: "route", title: "Intent router", body: "A trained classifier decides what kind of question it is." },
  { glyph: "tools", title: "Tools or your documents", body: "Calculators, market data, search or the files you uploaded." },
  { glyph: "pen", title: "Answer", body: "Written from those results, with citations." },
  { glyph: "shield", title: "Verification", body: "Each cited claim is checked against its source." },
];

const STATS: { value: number; decimals: number; suffix: string; label: string; detail: string }[] = [
  { value: 92.1, decimals: 1, suffix: "%", label: "Intent router", detail: "accuracy on phrasings it never saw in training" },
  {
    value: 98.1,
    decimals: 1,
    suffix: "%",
    label: "Transaction categoriser",
    detail: "on the test set; 64.9% on merchants never seen in training",
  },
  { value: 86.8, decimals: 1, suffix: "%", label: "Financial sentiment", detail: "accuracy on a held-out test split" },
  { value: 0.866, decimals: 3, suffix: "", label: "Hybrid retrieval", detail: "mean reciprocal rank on our document benchmark" },
];

/* ───────────────────────────── bits ───────────────────────────── */

function Reveal({ children, className, delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.45, delay, ease: EASE_OUT }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Counts up once when scrolled into view; screen readers get the final figure straight away. */
function StatValue({ value, decimals, suffix }: { value: number; decimals: number; suffix: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduced = useReducedMotion() ?? false;
  const [shown, setShown] = useState(0);

  useEffect(() => {
    if (!inView || reduced) return;
    const controls = animate(0, value, { duration: 0.7, ease: EASE_OUT, onUpdate: setShown });
    return () => controls.stop();
  }, [inView, reduced, value]);

  const final = `${value.toFixed(decimals)}${suffix}`;
  return (
    <>
      <span className="sr-only">{final}</span>
      <span ref={ref} aria-hidden className="tabular-nums">
        {(reduced ? value : shown).toFixed(decimals)}
        {suffix}
      </span>
    </>
  );
}

/** Small uppercase label, like the section tags of the reference. */
function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("text-[11px] font-semibold tracking-[0.18em] uppercase", className)}>{children}</p>;
}

/** Pill CTA with an arrow chip. */
function PillLink({ to, children, variant = "primary" }: { to: string; children: ReactNode; variant?: "primary" | "ghost" }) {
  return (
    <motion.div whileHover={{ y: -1 }} whileTap={{ scale: 0.97 }} transition={{ type: "spring", stiffness: 500, damping: 30 }}>
      <Link
        to={to}
        className={cn(
          "group inline-flex h-11 items-center gap-3 rounded-full pr-1.5 pl-5 text-[11.5px] font-semibold tracking-[0.16em] uppercase transition-colors focus-visible:outline-2",
          variant === "primary" ? "bg-primary text-primary-foreground hover:bg-[color-mix(in_oklch,var(--primary),black_12%)]" : "border bg-card text-foreground hover:bg-accent",
        )}
      >
        {children}
        <span
          className={cn(
            "grid size-8 place-items-center rounded-full transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:group-hover:translate-x-0",
            variant === "primary" ? "bg-primary-foreground/12" : "bg-muted",
          )}
        >
          <ArrowRight className="size-4" />
        </span>
      </Link>
    </motion.div>
  );
}

function CtaRow({ signedIn, className }: { signedIn: boolean; className?: string }) {
  if (signedIn) {
    return (
      <div className={cn("flex flex-wrap items-center justify-center gap-3", className)}>
        <PillLink to="/">Open Sphura</PillLink>
      </div>
    );
  }
  return (
    <div className={cn("flex flex-wrap items-center justify-center gap-3", className)}>
      <PillLink to="/signup">Get started</PillLink>
      <PillLink to="/login" variant="ghost">
        Sign in
      </PillLink>
      <GoogleButton block={false} />
    </div>
  );
}

/** A static illustration of one chat turn (real formula, correctly computed figures). */
function Glimpse() {
  return (
    <figure className="relative mx-auto w-full max-w-[40rem]">
      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, delay: 0.25, ease: EASE_OUT }}
        className="rounded-[1.75rem] border bg-card p-4 text-left shadow-pop sm:p-6"
      >
        <div className="flex justify-end">
          <p className="max-w-[88%] rounded-2xl rounded-br-md bg-bubble px-3.5 py-2.5 text-[14.5px] leading-relaxed">
            What&apos;s the EMI on a ₹25 lakh home loan at 8.5% for 20 years?
          </p>
        </div>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.55, ease: EASE_OUT }}
          className="mt-4 flex gap-3"
        >
          <SphuraLogo size={22} state="static" className="mt-0.5" />
          <div className="min-w-0 flex-1">
            <span className="inline-flex items-center gap-1.5 rounded-full border bg-background px-2.5 py-0.5 text-[10.5px] font-semibold tracking-[0.12em] text-muted-foreground uppercase">
              <Glyph name="tools" className="size-3.5 text-accent-ink" /> EMI calculator
            </span>
            <p className="mt-2.5 font-serif text-[15.5px] leading-relaxed">
              Your EMI comes to <strong className="font-semibold">₹21,696 a month</strong>. Over 20 years you would repay about ₹52.07
              lakh, of which ₹27.07 lakh is interest.
            </p>
            <p className="mt-2 overflow-x-auto font-mono text-[11.5px] whitespace-nowrap text-muted-foreground">
              EMI = P·r·(1+r)<sup>n</sup> ÷ ((1+r)<sup>n</sup> − 1), r = 8.5% ÷ 12, n = 240
            </p>
          </div>
        </motion.div>
        <div className="mt-5 flex items-center gap-2 rounded-full border bg-background py-1.5 pr-1.5 pl-4" aria-hidden>
          <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">Ask about EMI, SIP, tax or a statement…</span>
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground">
            <ArrowUp className="size-4" />
          </span>
        </div>
      </motion.div>
      <figcaption className="mt-3 text-center text-xs text-muted-foreground">An example answer, as it appears in a chat.</figcaption>
    </figure>
  );
}

/* ───────────────────────────── page ───────────────────────────── */

/** Public landing page: what Sphura is, what it does, how an answer is made and the models behind it. */
export default function Landing() {
  const me = useMe();
  const signedIn = me.isSuccess && !!me.data;

  useEffect(() => {
    document.title = "Sphura · a finance assistant that shows its working";
    return () => {
      document.title = "Sphura";
    };
  }, []);

  return (
    <div className="min-h-dvh overflow-x-hidden bg-background text-foreground">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:shadow-pop"
      >
        Skip to content
      </a>

      {/* floating pill navbar */}
      <header className="pt-safe sticky top-0 z-40 flex justify-center px-3 pt-3">
        <nav
          aria-label="Site"
          className="flex max-w-full items-center gap-1 rounded-full border bg-card/85 py-1 pr-1 pl-2 shadow-soft backdrop-blur-md"
        >
          <Link to="/welcome" aria-label="Sphura home" className="shrink-0 rounded-full px-1 py-0.5 focus-visible:outline-2">
            <SphuraLogo size={24} />
          </Link>
          <div className="mx-1 hidden items-center sm:flex">
            {[
              ["#what", "What"],
              ["#how", "How"],
              ["#models", "Models"],
            ].map(([href, label]) => (
              <a
                key={href}
                href={href}
                className="rounded-full px-3 py-1.5 text-[11px] font-semibold tracking-[0.16em] text-muted-foreground uppercase transition-colors hover:text-foreground focus-visible:outline-2"
              >
                {label}
              </a>
            ))}
          </div>
          {signedIn ? (
            <Link
              to="/"
              className="rounded-full bg-primary px-4 py-2 text-[11px] font-bold tracking-[0.16em] text-primary-foreground uppercase transition-colors hover:bg-[color-mix(in_oklch,var(--primary),black_12%)] focus-visible:outline-2"
            >
              Open
            </Link>
          ) : (
            <>
              <Link
                to="/login"
                className="rounded-full px-3 py-2 text-[11px] font-semibold tracking-[0.16em] text-muted-foreground uppercase transition-colors hover:text-foreground focus-visible:outline-2"
              >
                Sign in
              </Link>
              <Link
                to="/signup"
                className="rounded-full bg-primary px-4 py-2 text-[11px] font-bold tracking-[0.16em] text-primary-foreground uppercase transition-colors hover:bg-[color-mix(in_oklch,var(--primary),black_12%)] focus-visible:outline-2"
              >
                Start
              </Link>
            </>
          )}
        </nav>
      </header>

      <main id="main">
        {/* hero: Swiss two-tone headline, then a wall of glass bricks over a violet glow */}
        <section aria-labelledby="hero-title" className="relative isolate">
          <HoverGrid className="-z-10" />
          <div className="mx-auto max-w-6xl px-4 pt-10 pb-16 sm:px-6 sm:pt-14">
          <div className="flex items-start justify-between gap-4">
            <Label className="leading-[1.5] text-foreground/80">
              Sphura
              <br />
              <span className="text-muted-foreground">Finance AI</span>
            </Label>
            <SphuraLogo size={34} intro />
          </div>
          <motion.h1
            id="hero-title"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.05, ease: EASE_OUT }}
            className="mt-10 font-brand text-[3rem] leading-[0.95] font-bold tracking-[-0.045em] sm:mt-14 sm:text-[5.4rem] lg:text-[7rem]"
          >
            <span className="ink-gradient-text block pb-[0.06em]">Money questions,</span>
            <span className="flex flex-wrap items-start gap-x-3 sm:gap-x-5">
              <span className="sphura-gradient-text pb-[0.08em]">answered.</span>
              <Glyph name="sparkle" className="mt-[0.12em] size-[0.42em] shrink-0 text-highlight" />
              <span className="mt-[0.35em] text-[11px] leading-[1.45] font-semibold tracking-[0.2em] text-brand uppercase sm:text-xs">
                With the
                <br />
                working shown
              </span>
            </span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.12, ease: EASE_OUT }}
            className="mt-6 max-w-xl text-[16.5px] leading-relaxed text-pretty text-muted-foreground"
          >
            Sphura is a finance assistant that <span className="font-semibold text-foreground">computes with tools</span>, reads your
            statements and <span className="font-semibold text-foreground">cites its sources</span>.
          </motion.p>

          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.18, ease: EASE_OUT }}>
            <CtaRow signedIn={signedIn} className="mt-9 justify-start" />
          </motion.div>

          <div className="mt-14 sm:mt-16">
            <Glimpse />
          </div>
          </div>
        </section>

        {/* stats band */}
        <section id="models" aria-labelledby="models-title" className="scroll-mt-24 px-4 sm:px-6">
          <Reveal className="mx-auto max-w-6xl rounded-[2rem] border bg-band p-6 text-band-foreground sm:p-10">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <Label className="opacity-75">Models we trained</Label>
                <h2 id="models-title" className="mt-2 font-brand text-[1.7rem] leading-tight font-bold tracking-[-0.035em] sm:text-[2.2rem]">
                  Small models, measured honestly.
                </h2>
              </div>
              <p className="max-w-sm text-sm leading-relaxed opacity-80">Every figure comes from a held-out evaluation; the full reports live in Model Lab.</p>
            </div>
            <dl className="mt-8 grid gap-x-8 gap-y-7 sm:grid-cols-2 lg:grid-cols-4">
              {STATS.map((s) => (
                <div key={s.label} className="flex flex-col">
                  <dd className="order-first font-brand text-[2.8rem] leading-none font-light tracking-[-0.04em] sm:text-[3.2rem]">
                    <StatValue value={s.value} decimals={s.decimals} suffix={s.suffix} />
                  </dd>
                  <dt className="mt-3 text-sm font-semibold">{s.label}</dt>
                  <dd className="mt-1 text-[13px] leading-relaxed text-pretty opacity-80">{s.detail}</dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </section>

        {/* what it does */}
        <section id="what" aria-labelledby="what-title" className="scroll-mt-24 px-4 pt-6 sm:px-6">
          <Reveal className="mx-auto max-w-6xl rounded-[2rem] border bg-card p-6 shadow-soft sm:p-10 lg:grid lg:grid-cols-[1fr_1.5fr] lg:gap-14">
            <div>
              <Label className="text-accent-ink">What it does</Label>
              <h2 id="what-title" className="mt-3 font-brand text-[2.2rem] leading-[1] font-bold tracking-[-0.04em] text-balance sm:text-[3rem]">
                One place for your money questions.
              </h2>
              <p className="mt-4 max-w-md text-[15px] leading-relaxed text-pretty text-muted-foreground">
                Ask in plain language. The numbers come from tools and your own files, and every answer says where they came from.
              </p>
            </div>
            <ul className="mt-8 grid gap-3 sm:grid-cols-2 lg:mt-0">
              {FEATURES.map((f, i) => (
                <li key={f.title} className={cn(i === FEATURES.length - 1 && "sm:col-span-2")}>
                  <Reveal
                    delay={i * 0.04}
                    className="group h-full rounded-[1.4rem] border bg-background/60 p-5 transition-colors duration-200 hover:border-brand/40"
                  >
                    <span className="grid size-11 place-items-center rounded-2xl bg-accent text-accent-ink transition-transform duration-200 group-hover:-translate-y-0.5 motion-reduce:group-hover:translate-y-0">
                      <Glyph name={f.glyph} className="size-[22px]" strokeWidth={1.9} />
                    </span>
                    <h3 className="mt-4 text-[15.5px] font-semibold">{f.title}</h3>
                    <p className="mt-1.5 text-[14px] leading-relaxed text-pretty text-muted-foreground">{f.body}</p>
                  </Reveal>
                </li>
              ))}
            </ul>
          </Reveal>
        </section>

        {/* how it works */}
        <section id="how" aria-labelledby="how-title" className="scroll-mt-24 px-4 pt-6 sm:px-6">
          <Reveal className="mx-auto max-w-6xl rounded-[2rem] border bg-card p-6 shadow-soft sm:p-10">
            <Label className="text-accent-ink">How it works</Label>
            <h2 id="how-title" className="mt-3 font-brand text-[2.2rem] leading-[1] font-bold tracking-[-0.04em] text-balance sm:text-[3rem]">
              From question to checked answer.
            </h2>
            <ol className="mt-10 grid lg:grid-cols-5">
              {STEPS.map((s, i) => {
                const last = i === STEPS.length - 1;
                return (
                  <motion.li
                    key={s.title}
                    initial="hidden"
                    whileInView="show"
                    viewport={{ once: true, margin: "-40px" }}
                    className={cn("relative flex gap-4 lg:flex-col lg:gap-0 lg:pr-6", !last && "pb-8 lg:pb-0")}
                  >
                    {!last && (
                      <>
                        <motion.span
                          aria-hidden
                          variants={{ hidden: { scaleY: 0 }, show: { scaleY: 1, transition: { duration: 0.35, delay: 0.15 + i * 0.08, ease: EASE_OUT } } }}
                          className="absolute top-12 bottom-1 left-6 w-px origin-top bg-border lg:hidden"
                        />
                        <motion.span
                          aria-hidden
                          variants={{ hidden: { scaleX: 0 }, show: { scaleX: 1, transition: { duration: 0.35, delay: 0.15 + i * 0.08, ease: EASE_OUT } } }}
                          className="absolute top-6 right-3 left-[3.75rem] hidden origin-left items-center lg:flex"
                        >
                          <span className="h-px flex-1 bg-border" />
                          <svg viewBox="0 0 6 10" className="h-2.5 w-1.5 text-accent-ink" aria-hidden>
                            <path d="M1 1l4 4-4 4" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </motion.span>
                      </>
                    )}
                    <motion.span
                      variants={{ hidden: { opacity: 0, scale: 0.85 }, show: { opacity: 1, scale: 1, transition: { duration: 0.3, delay: i * 0.08, ease: EASE_OUT } } }}
                      className="relative z-10 grid size-12 shrink-0 place-items-center rounded-2xl border bg-background text-accent-ink"
                    >
                      <Glyph name={s.glyph} className="size-[22px]" strokeWidth={1.9} />
                    </motion.span>
                    <motion.div
                      variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.35, delay: 0.05 + i * 0.08, ease: EASE_OUT } } }}
                      className="min-w-0 pt-1 lg:pt-4"
                    >
                      <Label className="text-muted-foreground">Step 0{i + 1}</Label>
                      <h3 className="mt-1 text-[15px] font-semibold">{s.title}</h3>
                      <p className="mt-1 text-sm leading-relaxed text-pretty text-muted-foreground">{s.body}</p>
                    </motion.div>
                  </motion.li>
                );
              })}
            </ol>
          </Reveal>
        </section>

        {/* closing call to action */}
        <section aria-labelledby="cta-title" className="px-4 py-20 text-center sm:px-6 sm:py-28">
          <Reveal>
            <Label className="text-muted-foreground">Start with a loan, a SIP or last month&apos;s statement</Label>
            <h2 id="cta-title" className="mx-auto mt-4 max-w-4xl font-brand text-[2.6rem] leading-[0.98] font-bold tracking-[-0.045em] text-balance sm:text-[4.4rem]">
              Try it with your own numbers.
            </h2>
            <CtaRow signedIn={signedIn} className="mt-9" />
          </Reveal>
        </section>
      </main>

      <footer className="px-4 pb-6 sm:px-6">
        <div className="pb-safe mx-auto flex max-w-6xl flex-col gap-3 rounded-[1.4rem] border bg-card px-5 py-4 text-[13px] text-muted-foreground md:flex-row md:items-center md:justify-between">
          <div className="text-foreground">
            <SphuraLogo size={20} state="static" withWordmark />
          </div>
          <p className="max-w-2xl text-pretty md:text-right">
            Educational only, not investment advice. Check important figures against the cited sources. An AI/ML project-based learning
            project, {YEAR}.
          </p>
        </div>
      </footer>
    </div>
  );
}
