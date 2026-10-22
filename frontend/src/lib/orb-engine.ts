/* Dotted-sphere renderer shared by MorphOrb (ai-thiking-orb-and-input.tsx) and SphuraOrb.
   Extracted verbatim from MorphOrb and parameterised by canvas size, sphere radius and colour tone. */

/* ───────────────────────── math + easing ───────────────────────── */
export type Ease = (t: number) => number;
export const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const TAU = Math.PI * 2;

export function mulberry32(a: number) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function cubicBezier(x1: number, y1: number, x2: number, y2: number): Ease {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sx = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sy = (t: number) => ((ay * t + by) * t + cy) * t;
  const dx = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  const solve = (x: number) => {
    let t = x;
    for (let i = 0; i < 8; i++) {
      const e = sx(t) - x;
      if (Math.abs(e) < 1e-6) return t;
      const d = dx(t);
      if (Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    let lo = 0, hi = 1;
    t = x;
    for (let i = 0; i < 40; i++) {
      const e = sx(t);
      if (Math.abs(e - x) < 1e-6) break;
      if (x > e) lo = t; else hi = t;
      t = (hi - lo) / 2 + lo;
    }
    return t;
  };
  return (x) => (x <= 0 ? 0 : x >= 1 ? 1 : sy(solve(x)));
}

/** Shared easing table (same curves MorphOrb's timelines use). */
export const EASE = {
  out: cubicBezier(0.22, 1, 0.36, 1),
  io: cubicBezier(0.65, 0, 0.35, 1),
  in: cubicBezier(0.4, 0, 1, 1),
  fly: cubicBezier(0.5, 0, 0.1, 1),
  grow: cubicBezier(0.3, 0, 0.2, 1),
  vortex: cubicBezier(0.6, 0, 0.2, 1),
  spring: cubicBezier(0.34, 1.4, 0.64, 1),
  card: cubicBezier(0.65, 0, 0.2, 1),
  lin: (t: number) => t,
};

/* ───────────────────────────── theme ───────────────────────────── */
/** Theme the orb sits on: "dark" draws light dots, "light" draws dark dots. */
export type OrbTone = "dark" | "light";

export const isDarkTheme = () =>
  typeof document !== "undefined" && document.documentElement.classList.contains("dark");

const themeListeners = new Set<(dark: boolean) => void>();
let themeObserver: MutationObserver | null = null;
let themeLast = false;

/** Subscribe to the `.dark` class on <html> (one shared MutationObserver). */
export function onThemeChange(cb: (dark: boolean) => void): () => void {
  if (typeof document === "undefined") return () => {};
  themeListeners.add(cb);
  if (!themeObserver) {
    themeLast = isDarkTheme();
    themeObserver = new MutationObserver(() => {
      const d = isDarkTheme();
      if (d === themeLast) return;
      themeLast = d;
      themeListeners.forEach((fn) => fn(d));
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  }
  return () => {
    themeListeners.delete(cb);
    if (themeListeners.size === 0 && themeObserver) {
      themeObserver.disconnect();
      themeObserver = null;
    }
  };
}

/* ───────────────────────────── dot sets ───────────────────────────── */
const FULL_RINGS = 16;

interface DotSet { n: number; rings: number; dx: Float32Array; dy: Float32Array; dz: Float32Array; du: Float32Array; ds: Float32Array }
const dotCache = new Map<number, DotSet>();

/** Latitude rings of dots; 16 rings reproduces MorphOrb's original sphere exactly. */
function getDots(rings: number): DotSet {
  const hit = dotCache.get(rings);
  if (hit) return hit;
  const rand = mulberry32(7);
  const perRing = (30 * rings) / FULL_RINGS;
  const out: { x: number; y: number; z: number; u: number; seed: number }[] = [];
  for (let k = 0; k < rings; k++) {
    const y = 1 - ((k + 0.5) / rings) * 2;
    const r = Math.sqrt(1 - y * y);
    const m = Math.max(4, Math.round(perRing * r));
    for (let j = 0; j < m; j++) {
      const a = (j / m) * TAU + k * 0.35;
      out.push({ x: Math.cos(a) * r, y, z: Math.sin(a) * r, u: (1 - y) / 2, seed: rand() * 6.283 });
    }
  }
  const set: DotSet = {
    n: out.length,
    rings,
    dx: Float32Array.from(out, (d) => d.x),
    dy: Float32Array.from(out, (d) => d.y),
    dz: Float32Array.from(out, (d) => d.z),
    du: Float32Array.from(out, (d) => d.u),
    ds: Float32Array.from(out, (d) => d.seed),
  };
  dotCache.set(rings, set);
  return set;
}

/* ───────────────────────────── colours ───────────────────────────── */
const G_STEPS = 24, A_STEPS = 48;
type RGB = readonly [number, number, number];
const TONES: Record<OrbTone, { base: RGB; done: RGB }> = {
  dark: { base: [235, 235, 235], done: [52, 211, 153] },
  light: { base: [32, 32, 40], done: [5, 150, 105] },
};
const colorCache = new Map<OrbTone, string[]>();

/** rgba strings indexed by [sweep step * (A_STEPS + 1) + alpha step]. */
function getColors(tone: OrbTone): string[] {
  const hit = colorCache.get(tone);
  if (hit) return hit;
  const { base, done } = TONES[tone];
  const out: string[] = [];
  for (let gi = 0; gi <= G_STEPS; gi++) {
    const g = gi / G_STEPS;
    const r = Math.round(lerp(base[0], done[0], g)), gg = Math.round(lerp(base[1], done[1], g)), b = Math.round(lerp(base[2], done[2], g));
    for (let ai = 0; ai <= A_STEPS; ai++) out.push(`rgba(${r},${gg},${b},${(ai / A_STEPS).toFixed(3)})`);
  }
  colorCache.set(tone, out);
  return out;
}

/* ───────────────────────────── renderer ───────────────────────────── */
export type OrbProgram = 0 | 1 | 2 | 3;

export interface OrbParams {
  k: number; alpha: number; spin: number; rot: number; sweep: number; pop: number;
  vortex: number; gain: number; floor: number; rad: number; prog: number;
}
export const ORB_KEYS = ["k", "alpha", "spin", "sweep", "pop", "vortex", "gain", "floor", "rad"] as const;
export type OrbKey = (typeof ORB_KEYS)[number];

export interface OrbOptions {
  /** CSS px of the square canvas. */
  size: number;
  /** Sphere radius in CSS px. */
  radius: number;
  getSpeed?: () => number;
  isReduced?: () => boolean;
  /** "auto" follows the `.dark` class on <html>. Default "auto". */
  tone?: OrbTone | "auto";
  /** Number of latitude rings (MorphOrb: 16). */
  rings?: number;
  /** Multiplier on dot radius. Default 1. */
  dotScale?: number;
  /** DPR cap. Default 2. */
  maxDpr?: number;
  /** Called every frame with the real (unscaled) dt in seconds; return true to keep the loop alive. */
  onFrame?: (dt: number) => boolean;
  /** Stop the loop once nothing changes under reduced motion (frames would be identical). */
  stopWhenStill?: boolean;
}

export interface OrbHandle {
  P: OrbParams;
  /** Start the frame loop if visible (or always when `force`). */
  ensure(force?: boolean): void;
  reset(): void;
  destroy(): void;
  setTone(tone: OrbTone): void;
  setPaused(paused: boolean): void;
  /** Jump the light-program cross-fade to the current program and clear afterglow. */
  snap(): void;
  /** Draw one frame without advancing time (used when the loop is idle). */
  redraw(): void;
}

export function createOrb(canvas: HTMLCanvasElement, opts: OrbOptions): OrbHandle {
  const size = opts.size, R = opts.radius;
  const getSpeed = opts.getSpeed ?? (() => 1);
  const isReduced = opts.isReduced ?? (() => false);
  const dotScale = opts.dotScale ?? 1;
  const D = getDots(Math.max(4, Math.round(opts.rings ?? FULL_RINGS)));
  const { n: N, dx: DX, dy: DY, dz: DZ, du: DU, ds: DS } = D;
  const full = getDots(FULL_RINGS).n;
  const chase = N / full; // keep loop period + highlight width independent of density
  const bandK = 0.02 * (FULL_RINGS / D.rings) ** 2;

  const P: OrbParams = { k: 0, alpha: 0, spin: 0, rot: 0, sweep: 0, pop: 1, vortex: 0, gain: 1, floor: 0, rad: 0, prog: 0 };
  const ctx = canvas.getContext("2d");
  const lit = new Float32Array(N);
  const SX = new Float32Array(N), SY = new Float32Array(N), SR = new Float32Array(N), SD = new Float32Array(N);
  const SC = new Int16Array(N);
  const pw = [1, 0, 0, 0];
  let time = 0, raf = 0, last = 0, dead = false, paused = false;

  const auto = (opts.tone ?? "auto") === "auto";
  let colors = getColors(auto ? (isDarkTheme() ? "dark" : "light") : (opts.tone as OrbTone));

  const reset = () => {
    P.k = 0; P.alpha = 0; P.spin = 0; P.rot = 0; P.sweep = 0; P.pop = 1; P.vortex = 0; P.gain = 1; P.floor = 0; P.rad = 0; P.prog = 0;
    lit.fill(0);
    pw[0] = 1; pw[1] = 0; pw[2] = 0; pw[3] = 0;
    time = isReduced() ? 1.2 : 0;
  };
  reset();

  if (!ctx) {
    const noop = () => {};
    return { P, ensure: noop, reset, destroy: noop, setTone: noop, setPaused: noop, snap: noop, redraw: noop };
  }

  const dpr = Math.min(opts.maxDpr ?? 2, window.devicePixelRatio || 1);
  canvas.width = Math.round(size * dpr);
  canvas.height = Math.round(size * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const S = 0.6, CP = Math.cos(0.35), SP = Math.sin(0.35), C0 = size / 2;

  const draw = (dt: number) => {
    ctx.clearRect(0, 0, size, size);
    time += dt;
    P.rot += P.spin * dt;
    const yaw = P.rot + P.vortex, cyw = Math.cos(yaw), syw = Math.sin(yaw);
    const stepW = dt / 0.35;
    for (let q = 0; q < 4; q++) {
      const d = (q === P.prog ? 1 : 0) - pw[q];
      pw[q] += Math.abs(d) <= stepW ? d : d > 0 ? stepW : -stepW;
    }
    const decay = Math.exp(-dt / 0.5);
    const h0 = (time * 300 * chase) % N, h3 = (time * 480 * chase) % N;
    const w0 = 16 * chase, w3 = 22 * chase;
    const a1 = time * 0.8, b1 = Math.sin(time * 0.5) * 0.9;
    const f1x = Math.cos(b1) * Math.cos(a1), f1y = Math.sin(b1), f1z = Math.cos(b1) * Math.sin(a1);
    const a2 = time * 0.55 + 2.1, b2 = Math.cos(time * 0.42) * 0.9;
    const f2x = Math.cos(b2) * Math.cos(a2), f2y = Math.sin(b2), f2z = Math.cos(b2) * Math.sin(a2);
    const lat = Math.sin(time * 2.2);
    const swirlK = P.vortex * 1.5;

    for (let n = 0; n < N; n++) {
      const dx = DX[n], dy = DY[n], dz = DZ[n], u = DU[n];

      /* light programs: dots are lit in turn */
      let pulse = 0;
      if (pw[0] > 0.001) {
        let dd = Math.abs(n - h0); if (dd > N - dd) dd = N - dd;
        const v = Math.max(0, 1 - dd / w0);
        pulse = Math.max(pulse, v * v * pw[0]);
      }
      if (pw[1] > 0.001) {
        const v1 = Math.max(0, (dx * f1x + dy * f1y + dz * f1z - 0.72) / 0.28);
        const v2 = Math.max(0, (dx * f2x + dy * f2y + dz * f2z - 0.72) / 0.28);
        const v = Math.max(v1, v2);
        pulse = Math.max(pulse, v * v * pw[1]);
      }
      if (pw[2] > 0.001) {
        const e = dy - lat;
        const v = Math.max(0, 1 - (e * e) / bandK);
        pulse = Math.max(pulse, v * v * pw[2]);
      }
      if (pw[3] > 0.001) {
        let dd = Math.abs(n - h3); if (dd > N - dd) dd = N - dd;
        const v = Math.max(0, 1 - dd / w3);
        pulse = Math.max(pulse, v * v * pw[3]);
      }
      const l = Math.max(lit[n] * decay, pulse * P.gain);
      lit[n] = l;

      /* per-dot appearance: top dots first, bottom collapse first */
      const ki = clamp01(P.k * (1 + S) - S * u);
      if (ki <= 0.001) { SC[n] = -1; continue; }
      const eo = EASE.out(ki), kk = eo * P.pop;

      const x1 = dx * cyw + dz * syw, z1 = -dx * syw + dz * cyw;
      const y2 = dy * CP - z1 * SP, z2 = dy * SP + z1 * CP;
      const f = 2.8 / (2.8 - z2), depth = (z2 + 1) / 2;
      let ox = x1 * R * kk * f, oy = -y2 * R * kk * f;
      if (swirlK > 0.001) {
        const sw = (1 - ki) * swirlK, cc = Math.cos(sw), ss = Math.sin(sw);
        const tx = ox * cc - oy * ss;
        oy = ox * ss + oy * cc;
        ox = tx;
      }

      const g = clamp01((P.sweep * 1.4 - u) / 0.4);
      let a = 0.1 + 0.035 * Math.sin(DS[n] + time * 1.6) * (1 - g) + 0.32 * depth * depth + 0.75 * l * (1 - g) + g * (0.55 + 0.4 * depth) + 2 * g * (1 - g);
      a = Math.max(a, P.floor * (0.7 + 0.3 * depth));
      if (a > 1) a = 1;
      a *= eo * P.alpha;

      SX[n] = C0 + ox;
      SY[n] = C0 + oy;
      SD[n] = depth;
      SR[n] = (1.15 * (0.45 + 0.75 * depth) * f + 0.9 * l + g * 0.25) * (1 + P.rad) * (0.4 + 0.6 * eo) * dotScale;
      const ai = Math.round(a * A_STEPS), gi = Math.round(g * G_STEPS);
      SC[n] = ai <= 0 ? -1 : gi * (A_STEPS + 1) + ai;
    }

    /* two passes: back half first, then front half */
    for (let pass = 0; pass < 2; pass++) {
      for (let n = 0; n < N; n++) {
        const c = SC[n];
        if (c < 0) continue;
        if ((SD[n] >= 0.5) !== (pass === 1)) continue;
        ctx.fillStyle = colors[c];
        ctx.beginPath();
        ctx.arc(SX[n], SY[n], SR[n], 0, TAU);
        ctx.fill();
      }
    }
  };

  const frame = (now: number) => {
    raf = 0;
    if (dead || paused) return;
    const real = Math.max(0, Math.min(0.05, (now - last) / 1000));
    const still = isReduced();
    const dt = still ? 0 : real * getSpeed();
    last = now;
    const keep = opts.onFrame ? opts.onFrame(real) : false;
    draw(dt);
    if (keep || (P.alpha > 0.002 && !(still && opts.stopWhenStill))) raf = requestAnimationFrame(frame);
    else if (P.alpha <= 0.002) ctx.clearRect(0, 0, size, size);
  };

  const ensure = (force = false) => {
    if (raf || dead || paused) return;
    if (!force && P.alpha <= 0.002) return;
    last = performance.now();
    raf = requestAnimationFrame(frame);
  };

  const redraw = () => {
    if (dead || raf) return;
    if (P.alpha <= 0.002) ctx.clearRect(0, 0, size, size);
    else draw(0);
  };

  const unsub = auto ? onThemeChange((d) => { colors = getColors(d ? "dark" : "light"); redraw(); }) : () => {};

  return {
    P,
    ensure,
    reset,
    destroy() {
      dead = true;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      unsub();
    },
    setTone(tone) {
      colors = getColors(tone);
      redraw();
    },
    setPaused(p) {
      if (p === paused) return;
      paused = p;
      if (p && raf) { cancelAnimationFrame(raf); raf = 0; }
      if (!p) ensure(!!opts.onFrame);
    },
    snap() {
      for (let q = 0; q < 4; q++) pw[q] = q === P.prog ? 1 : 0;
      lit.fill(0);
    },
    redraw,
  };
}
