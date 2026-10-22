import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { createOrb, EASE, type Ease, type OrbKey, type OrbProgram } from "@/lib/orb-engine";

export type { OrbProgram };

export interface SphuraOrbProps {
  /** 0 thinking · 1 searching · 2 reading/analyzing · 3 composing. Changes cross-fade. */
  program?: OrbProgram;
  /** Rendered px. Default 40. */
  size?: number;
  /** true = assembled + spinning; false = collapses and fades out. Default true. */
  active?: boolean;
  /** Play the resolve sweep (dots glow to the done colour). Default false. */
  done?: boolean;
  className?: string;
  "aria-label"?: string;
}

interface OrbState { program: OrbProgram; active: boolean; done: boolean }
interface Track { key: OrbKey; from: number | null; to: number; t0: number; t1: number; ease: Ease }

const tr = (key: OrbKey, to: number, t0: number, t1: number, ease: Ease = EASE.io): Track => ({ key, from: null, to, t0, t1, ease });

const assemblePlan = (done: boolean): Track[] => [
  tr("vortex", 0, 0, 300, EASE.out),
  tr("k", 1, 0, 800, EASE.out),
  tr("alpha", 1, 0, 600, EASE.out),
  tr("spin", done ? 0.3 : 0.9, 0, 800, EASE.out),
  tr("pop", 1.05, 0, 420, EASE.out),
  tr("pop", 1, 420, 800, EASE.io),
];
const COLLAPSE: () => Track[] = () => [
  tr("pop", 1.06, 0, 120, EASE.out),
  tr("k", 0, 120, 640, EASE.vortex),
  tr("vortex", 1.6, 120, 640, EASE.vortex),
  tr("alpha", 0, 400, 700, EASE.out),
  tr("pop", 1, 640, 700, EASE.out),
];
const RESOLVE: () => Track[] = () => [
  tr("sweep", 1, 0, 700, EASE.io),
  tr("spin", 0.3, 0, 700, EASE.out),
  tr("gain", 0, 0, 700, EASE.out),
  tr("floor", 0.95, 400, 900, EASE.out),
  tr("rad", 0.15, 400, 900, EASE.out),
  tr("pop", 1.04, 600, 800, EASE.out),
  tr("pop", 1, 800, 900, EASE.out),
];
const UNRESOLVE: () => Track[] = () => [
  tr("sweep", 0, 0, 500, EASE.io),
  tr("spin", 0.9, 0, 600, EASE.out),
  tr("gain", 1, 0, 400, EASE.out),
  tr("floor", 0, 0, 400, EASE.out),
  tr("rad", 0, 0, 400, EASE.out),
];

/** Sphere geometry for a given rendered size: fewer, slightly larger dots when small. */
function geometry(size: number) {
  const radius = size * 0.4;
  const rings = Math.max(6, Math.min(16, Math.round(16 * Math.sqrt(radius / 66))));
  const dotScale = Math.min(1, 0.7 + (0.3 * radius) / 66);
  return { radius, rings, dotScale };
}

/** Imperative controller: owns the engine, the tween list and the visibility pausing. */
function createController(canvas: HTMLCanvasElement, size: number, init: OrbState, animateIn: boolean) {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  let reduced = mq.matches;
  let tracks: Track[] = [];
  let clock = 0;
  let state = { ...init };

  const step = (dt: number) => {
    if (!tracks.length) return false;
    clock += dt * 1000;
    for (const t of tracks) {
      if (clock < t.t0) continue;
      if (t.from === null) t.from = orb.P[t.key];
      const p = Math.min(1, (clock - t.t0) / Math.max(1, t.t1 - t.t0));
      orb.P[t.key] = t.from + (t.to - t.from) * t.ease(p);
    }
    tracks = tracks.filter((t) => clock < t.t1);
    return tracks.length > 0;
  };

  const g = geometry(size);
  const orb = createOrb(canvas, {
    size,
    radius: g.radius,
    rings: g.rings,
    dotScale: g.dotScale,
    maxDpr: 3,
    tone: "auto",
    isReduced: () => reduced,
    stopWhenStill: true,
    onFrame: step,
  });
  const P = orb.P;

  /** Jump every pending track to its end value (reduced motion). */
  const settle = () => {
    for (const t of tracks) P[t.key] = t.to;
    tracks = [];
    orb.snap();
  };

  const play = (plan: Track[]) => {
    const keys = new Set(plan.map((t) => t.key));
    tracks = tracks.filter((t) => !keys.has(t.key));
    for (const t of plan) tracks.push({ ...t, t0: t.t0 + clock, t1: t.t1 + clock });
    if (reduced) settle();
  };

  /* initial state */
  P.prog = init.program;
  orb.snap();
  if (init.active) {
    if (init.done) {
      P.sweep = 1; P.gain = 0; P.floor = 0.95; P.rad = 0.15;
    }
    if (animateIn && !reduced) play(assemblePlan(init.done));
    else { P.k = 1; P.alpha = 1; P.spin = init.done ? 0.3 : 0.9; }
  }
  orb.ensure(true);

  const update = (next: OrbState) => {
    const prev = state;
    state = { ...next };
    if (next.program !== prev.program) {
      P.prog = next.program;
      if (reduced) orb.snap();
    }
    if (next.active !== prev.active) {
      if (next.active) {
        if (P.k < 0.05) { P.rot = 0; P.vortex = 0; }
        play(assemblePlan(next.done));
        if (next.done !== prev.done) play(next.done ? RESOLVE() : UNRESOLVE());
      } else {
        play(COLLAPSE());
      }
    } else if (next.done !== prev.done && next.active) {
      play(next.done ? RESOLVE() : UNRESOLVE());
    } else if (next.done !== prev.done) {
      P.sweep = next.done ? 1 : 0; P.gain = next.done ? 0 : 1; P.floor = next.done ? 0.95 : 0; P.rad = next.done ? 0.15 : 0;
    }
    orb.ensure(true);
  };

  /* pause offscreen / hidden tab */
  let onScreen = true;
  const sync = () => orb.setPaused(!onScreen || document.hidden);
  const io = typeof IntersectionObserver !== "undefined"
    ? new IntersectionObserver((es) => { onScreen = es[es.length - 1]?.isIntersecting ?? true; sync(); }, { rootMargin: "48px" })
    : null;
  io?.observe(canvas);
  document.addEventListener("visibilitychange", sync);

  const onMq = (e: MediaQueryListEvent) => {
    reduced = e.matches;
    if (reduced) settle();
    orb.ensure(true);
  };
  mq.addEventListener("change", onMq);

  return {
    update,
    destroy() {
      io?.disconnect();
      document.removeEventListener("visibilitychange", sync);
      mq.removeEventListener("change", onMq);
      orb.destroy();
    },
  };
}

type Controller = ReturnType<typeof createController>;

/** The Sphura "thinking" orb: a rotating dotted sphere whose light program follows the agent phase. */
export function SphuraOrb({
  program = 0,
  size = 40,
  active = true,
  done = false,
  className,
  "aria-label": ariaLabel,
}: SphuraOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ctlRef = useRef<Controller | null>(null);
  const stateRef = useRef<OrbState>({ program, active, done });
  const sizeRef = useRef(size);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const animateIn = sizeRef.current === size; // fresh mount (incl. StrictMode remount), not a resize
    sizeRef.current = size;
    const ctl = createController(canvas, size, stateRef.current, animateIn);
    ctlRef.current = ctl;
    return () => {
      ctl.destroy();
      ctlRef.current = null;
    };
  }, [size]);

  useEffect(() => {
    stateRef.current = { program, active, done };
    ctlRef.current?.update(stateRef.current);
  }, [program, active, done]);

  return (
    <span
      className={cn("relative inline-block shrink-0 align-middle", className)}
      style={{ width: size, height: size }}
      role={ariaLabel ? "img" : undefined}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel ? undefined : true}
    >
      <canvas ref={canvasRef} className="block" style={{ width: size, height: size }} />
    </span>
  );
}

export default SphuraOrb;
