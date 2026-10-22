import { useEffect, useId, useState } from "react";
import { motion, useReducedMotion, type TargetAndTransition, type Transition } from "framer-motion";
import { cn } from "@/lib/utils";

export type LogoState = "idle" | "thinking" | "answer" | "static";

export interface SphuraLogoProps {
  /** px of the mark. Default 32. */
  size?: number;
  /** idle (still) · thinking (blocks build in a loop) · answer (one ripple) · static. Default "idle". */
  state?: LogoState;
  /** Lowercase "sphura" wordmark next to the mark. Default false. */
  withWordmark?: boolean;
  /** Small tracked "FINANCE AI" caption under the wordmark (needs `withWordmark`). Default false. */
  caption?: boolean;
  /** Blocks drop in and assemble the S on mount. Default false. */
  intro?: boolean;
  /** Hovering nudges a loose block. Default true. */
  interactive?: boolean;
  className?: string;
}

/* ───────────────────────────── geometry (viewBox 64) ─────────────────────────────
   A bold S built from 15 blocks on a 5 × 7 grid (7-unit cells, 6.2-unit blocks with a darker
   bottom/right edge for depth), plus two small loose blocks. Blocks are listed in stroke order
   (top-right → top row → left → middle → right → bottom row) so loops read as the S being drawn. */
const CELL = 7;
const BLOCK = 6.2;
const OX = 14.5;
const OY = 7.5;
const S_CELLS: [number, number][] = [
  [4, 0], [3, 0], [2, 0], [1, 0],
  [0, 1], [0, 2],
  [1, 3], [2, 3], [3, 3],
  [4, 4], [4, 5],
  [3, 6], [2, 6], [1, 6], [0, 6],
];
const S_BLOCKS = S_CELLS.map(([c, r]) => ({ x: OX + c * CELL, y: OY + r * CELL }));
const LOOSE = [
  { x: 53.5, y: 3, s: 5, rot: 16 },
  { x: 5, y: 54.5, s: 4.2, rot: -12 },
];

const FACE = "var(--logo-face, #7c3aed)";
const EDGE = "var(--logo-edge, #c084fc)";
const EASE: Transition["ease"] = [0.22, 1, 0.36, 1];

function Block({ x, y, s, rx = 1.5 }: { x: number; y: number; s: number; rx?: number }) {
  return (
    <>
      <rect x={x + 0.9} y={y + 0.9} width={s} height={s} rx={rx} fill={EDGE} />
      <rect x={x} y={y} width={s} height={s} rx={rx} fill={FACE} />
    </>
  );
}

/** The Sphura block-S mark, optionally with the lowercase wordmark and "FINANCE AI" caption. */
export function SphuraLogo({
  size = 32,
  state = "idle",
  withWordmark = false,
  caption = false,
  intro = false,
  interactive = true,
  className,
}: SphuraLogoProps) {
  const reduced = useReducedMotion() ?? false;
  const uid = useId();

  /* "answer" plays one ripple, then settles to idle */
  const [prevState, setPrevState] = useState(state);
  const [settled, setSettled] = useState(false);
  if (state !== prevState) {
    setPrevState(state);
    setSettled(false);
  }
  useEffect(() => {
    if (state !== "answer") return;
    const t = setTimeout(() => setSettled(true), 900);
    return () => clearTimeout(t);
  }, [state]);
  const mode: LogoState = reduced ? "static" : state === "answer" && settled ? "idle" : state;

  /* hover: a loose block hops, one S block lifts (cycles through the S on repeated hovers) */
  const [nudge, setNudge] = useState(0);
  const canNudge = interactive && mode === "idle";
  const lifted = nudge > 0 ? (nudge * 7) % S_BLOCKS.length : -1;

  const blockMotion = (i: number): { animate: TargetAndTransition; transition: Transition } => {
    if (mode === "thinking") {
      return {
        animate: { opacity: [0.22, 1, 0.22], y: [0, -1.2, 0] },
        transition: { duration: 1.25, repeat: Infinity, delay: i * 0.075, ease: "easeInOut" },
      };
    }
    if (mode === "answer") {
      return {
        animate: { opacity: 1, y: [0, -2.4, 0] },
        transition: { duration: 0.42, delay: i * 0.025, ease: "easeOut" },
      };
    }
    if (i === lifted) {
      return { animate: { opacity: 1, y: [0, -2.2, 0] }, transition: { duration: 0.38, ease: "easeOut" } };
    }
    return {
      animate: { opacity: 1, y: 0 },
      transition: intro ? { type: "spring", stiffness: 620, damping: 30, mass: 0.6, delay: 0.04 + i * 0.032 } : { duration: 0.25, ease: EASE },
    };
  };

  const looseMotion = (k: number): { animate: TargetAndTransition; transition: Transition } => {
    const base = LOOSE[k];
    if (mode === "thinking") {
      return {
        animate: { opacity: [0.4, 1, 0.4], y: [0, -2, 0], rotate: [base.rot, base.rot + 18, base.rot] },
        transition: { duration: 1.6, repeat: Infinity, delay: k * 0.5, ease: "easeInOut" },
      };
    }
    if (k === 0 && nudge > 0 && mode === "idle") {
      return {
        animate: { opacity: 1, scale: 1, y: [0, -4, 0], rotate: [base.rot, base.rot + 40, base.rot] },
        transition: { duration: 0.5, ease: "easeOut" },
      };
    }
    return {
      animate: { opacity: 1, scale: 1, y: 0, rotate: base.rot },
      transition: intro ? { duration: 0.35, delay: 0.55 + k * 0.08, ease: EASE } : { duration: 0.25 },
    };
  };

  const still = mode === "static";

  const mark = (
    <motion.svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      aria-hidden="true"
      className="shrink-0 overflow-visible"
      onHoverStart={canNudge ? () => setNudge((n) => n + 1) : undefined}
    >
      {S_BLOCKS.map((b, i) =>
        still ? (
          <g key={i}>
            <Block x={b.x} y={b.y} s={BLOCK} />
          </g>
        ) : (
          <motion.g
            key={`${uid}-${i}`}
            initial={intro ? { opacity: 0, y: -14 } : false}
            {...blockMotion(i)}
          >
            <Block x={b.x} y={b.y} s={BLOCK} />
          </motion.g>
        ),
      )}
      {LOOSE.map((l, k) =>
        still ? (
          <g key={`l${k}`} transform={`rotate(${l.rot} ${l.x + l.s / 2} ${l.y + l.s / 2})`}>
            <Block x={l.x} y={l.y} s={l.s} rx={1.1} />
          </g>
        ) : (
          <motion.g
            key={`l${k}-${k === 0 ? nudge : 0}`}
            style={{ transformBox: "fill-box", transformOrigin: "center" }}
            initial={intro && nudge === 0 ? { opacity: 0, scale: 0.4, rotate: l.rot } : { rotate: l.rot }}
            {...looseMotion(k)}
          >
            <Block x={l.x} y={l.y} s={l.s} rx={1.1} />
          </motion.g>
        ),
      )}
    </motion.svg>
  );

  if (!withWordmark) {
    return (
      <span role="img" aria-label="Sphura" className={cn("inline-flex shrink-0 align-middle", className)}>
        {mark}
      </span>
    );
  }

  return (
    <span
      role="img"
      aria-label={caption ? "Sphura, finance AI" : "Sphura"}
      className={cn("inline-flex shrink-0 items-center align-middle", className)}
      style={{ gap: Math.round(size * 0.28) }}
    >
      {mark}
      <span className="flex flex-col justify-center" aria-hidden="true">
        <span
          className="select-none whitespace-nowrap text-current"
          style={{
            fontFamily: "var(--font-round)",
            fontSize: Math.round(size * (caption ? 0.74 : 0.78)),
            fontWeight: 800,
            letterSpacing: "-0.02em",
            lineHeight: 0.95,
          }}
        >
          sphura
        </span>
        {caption && (
          <span
            className="select-none whitespace-nowrap text-brand"
            style={{
              fontFamily: "var(--font-sans)",
              fontSize: Math.max(8, Math.round(size * 0.22)),
              fontWeight: 700,
              letterSpacing: "0.24em",
              lineHeight: 1,
              marginTop: Math.max(2, Math.round(size * 0.08)),
            }}
          >
            FINANCE AI
          </span>
        )}
      </span>
    </span>
  );
}

export default SphuraLogo;
