// component.tsx
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { clamp01, createOrb, EASE, lerp, ORB_KEYS, type Ease, type OrbProgram } from "@/lib/orb-engine";
import "@/styles/morph-orb-keyframes.css";
import "@/styles/morph-orb.css";

/* ───────────────────────────── copy ───────────────────────────── */
const COPY = {
  placeholder: "Ask anything…",
  labels: ["Thinking", "Searching", "Analyzing", "Composing"],
  done: "Done",
  answerTitle: "Answer",
  answerBody: "The answer goes here",
  failed: "Something went wrong. Please try again.",
  reset: "New question",
  send: "Send",
};

type Phase = "idle" | "launch" | "assemble" | "think" | "resolve" | "condense" | "unfold" | "answered" | "reset";

export interface MorphOrbProps {
  /** Resolve with the answer text. `signal` aborts when the run is cancelled (Escape, unmount): stop the work. */
  onSubmit?: (text: string, signal: AbortSignal) => Promise<string> | string;
  minThinkMs?: number;
  speed?: number;
  /** When set, shown instead of the timer-cycled labels while thinking (real agent status). */
  statusLabel?: string;
  /** When set, drives the orb light program instead of the timer. */
  statusProgram?: OrbProgram;
  /** Pill placeholder. Default "Ask anything…". */
  placeholder?: string;
}

/* ─────────────────────────── geometry ─────────────────────────── */
const PILL_H = 60, BALL_SMALL = 60, ORB_D = 132, ORB_R = 66, CANVAS = 220;
const CARD_H = 108;
const FLY_D = 138;
const pillW = () => Math.min(560, window.innerWidth - 32);
const cardW = () => Math.min(320, window.innerWidth - 32);
const homeDy = () => window.innerHeight * 0.54 - 96; // pill centre is 96px above the viewport bottom; stage centre is at top:46%
const wideW = () => Math.min(560, window.innerWidth - 32); // long answers widen the card to the pill width
const maxCardH = () => Math.round(window.innerHeight * 0.55);

/* ───────────────────────── math + easing ───────────────────────── */
// clamp01 / lerp / cubic-bezier easings live in lib/orb-engine (shared with SphuraOrb)
const fmt = (v: number) => String(Math.round(v * 1e4) / 1e4);
const E = EASE;

const bez = (t: number, p0: number, c: number, p2: number) => (1 - t) * (1 - t) * p0 + 2 * (1 - t) * t * c + t * t * p2;

/* ───────────────────────── timeline data ───────────────────────── */
interface Track { ch: string; from: number; to: number; t0: number; t1: number; ease?: Ease }
const T = (ch: string, from: number, to: number, t0: number, t1: number, ease: Ease = E.io): Track => ({ ch, from, to, t0, t1, ease });

interface Geo { pw: number; cw: number; H: number; dir: number }

const launchTracks = (g: Geo): Track[] => [
  T("w", g.pw, g.pw - 12, 0, 100, E.out),
  T("oInput", 1, 0, 0, 160, E.in),
  T("inScale", 1, 0.6, 0, 160, E.in),
  T("oGlow", 1, 0, 0, 300, E.out),
  T("oAur", 1, 0, 0, 300, E.out),
  T("w", g.pw - 12, BALL_SMALL, 100, 560, E.io),
  T("h", PILL_H, PILL_H + 6, 380, 500, E.out),
  T("h", PILL_H + 6, BALL_SMALL, 500, 620, E.out),
  T("oPill", 1, 0, 300, 560, E.out),
  T("oBall", 0, 1, 300, 560, E.out),
  T("u", 0, 1, 620, 1500, E.fly),
  T("w", BALL_SMALL, FLY_D, 620, 1300, E.grow),
  T("h", BALL_SMALL, FLY_D, 620, 1300, E.grow),
  T("w", FLY_D, ORB_D, 1300, 1500, E.out),
  T("h", FLY_D, ORB_D, 1300, 1500, E.out),
  T("cHalo", 0, 0.6, 620, 1500, E.out),
  T("trail", 0, 1, 700, 800, E.out),
  T("trail", 1, 0, 1300, 1500, E.in),
];

const ASSEMBLE: Track[] = [
  T("oRing", 1, 0, 0, 300, E.out),
  T("oBall", 1, 0, 0, 260, E.out),
  T("orb.k", 0, 1, 0, 800, E.out),
  T("orb.alpha", 0, 1, 0, 800, E.out),
  T("orb.spin", 0, 0.9, 0, 800, E.out),
  T("orb.pop", 1, 1.05, 0, 420, E.out),
  T("orb.pop", 1.05, 1, 420, 800, E.io),
  T("sOp", 0, 1, 300, 620, E.out),
  T("sTy", 6, 0, 300, 620, E.out),
];

const RESOLVE: Track[] = [
  T("orb.sweep", 0, 1, 0, 700, E.io),
  T("orb.spin", 0.9, 0.3, 0, 700, E.out),
  T("orb.gain", 1, 0, 0, 700, E.out),
  T("orb.floor", 0, 0.95, 400, 900, E.out),
  T("orb.rad", 0, 0.15, 400, 900, E.out),
  T("orb.pop", 1, 1.04, 600, 800, E.out),
  T("orb.pop", 1.04, 1, 800, 900, E.out),
];

const CONDENSE: Track[] = [
  T("orb.pop", 1, 1.06, 0, 120, E.out),
  T("sOp", 1, 0, 0, 160, E.in),
  T("sTy", 0, -6, 0, 160, E.in),
  T("orb.k", 1, 0, 120, 640, E.vortex),
  T("orb.vortex", 0, 1.6, 120, 640, E.vortex),
  T("oGreen", 0, 1, 260, 700, E.spring),
  T("gs", 0.55, 1, 260, 700, E.spring),
  T("pulse", 0, 1, 320, 760, E.out),
  T("oHalo", 0, 0.35, 380, 700, E.out),
  T("orb.alpha", 1, 0, 500, 800, E.out),
];

const unfoldTracks = (g: Geo, tw: number): Track[] => [
  T("w", ORB_D, 124, 0, 90, E.in),
  T("h", ORB_D, 124, 0, 90, E.in),
  T("w", 124, g.cw, 90, 700, E.card),
  T("h", 124, CARD_H, 90, 700, E.out),
  T("r", ORB_D / 2, 20, 90, 700, E.io),
  T("oGreen", 1, 0, 200, 560, E.out),
  T("oCard", 0, 1, 200, 560, E.out),
  T("oHalo", 0.35, 0, 300, 700, E.out),
  T("cHalo", 0.6, 0.22, 300, 700, E.out),
  T("hOp", 0, 1, 520, 840, E.out),
  T("dotS", 0, 1, 520, 840, E.spring),
  T("wp", 0, 1, 600, 600 + tw, E.lin),
  T("bloom", 1, 0.625, 700, 1200, E.io),
];

/* reduced-motion: pure cross-fades */
const R_OUT: Track[] = [
  T("oInput", 1, 0, 0, 140, E.out),
  T("oPill", 1, 0, 0, 200, E.out),
  T("oGlow", 1, 0, 0, 200, E.out),
  T("oAur", 1, 0, 0, 200, E.out),
  T("oRing", 1, 0, 0, 200, E.out),
];
const R_IN: Track[] = [
  T("orb.alpha", 0, 1, 0, 200, E.out),
  T("sOp", 0, 1, 0, 200, E.out),
  T("cHalo", 0, 0.6, 0, 200, E.out),
];
const R_RESOLVE: Track[] = [T("orb.sweep", 0, 1, 0, 250, E.io), T("orb.floor", 0, 0.95, 0, 250, E.out)];
const R_CONDENSE: Track[] = [
  T("oGreen", 0, 1, 0, 250, E.out),
  T("orb.alpha", 1, 0, 0, 250, E.out),
  T("sOp", 1, 0, 0, 250, E.out),
];
const R_GREEN_OUT: Track[] = [T("oGreen", 1, 0, 0, 120, E.out)];
const rCardIn = (tw: number): Track[] => [
  T("oCard", 0, 1, 0, 250, E.out),
  T("hOp", 0, 1, 0, 250, E.out),
  T("wp", 0, 1, 0, tw, E.lin),
  T("bloom", 1, 0.625, 0, 250, E.out),
];

const FADE = ["oGlow", "oAur", "oPill", "oBall", "oGreen", "oCard", "oRing", "oInput", "oHalo", "sOp", "orb.alpha", "trail"];

const INIT: Record<string, number> = {
  h: PILL_H, r: 999, oGlow: 1, oHalo: 0, oPill: 1, oBall: 0, oGreen: 0, oCard: 0, oRing: 1, oInput: 1, inScale: 1, oAur: 1,
  gs: 0.55, cs: 1, hOp: 0, dotS: 0, bloom: 1, u: 0, yOff: 0, trail: 0, pulse: -1, sOp: 0, sTy: 6, cHalo: 0, wp: 0,
  "orb.k": 0, "orb.alpha": 0, "orb.spin": 0, "orb.pop": 1, "orb.sweep": 0, "orb.vortex": 0, "orb.gain": 1, "orb.floor": 0, "orb.rad": 0,
};

/* ─────────────────────────── async utils ─────────────────────────── */
const ABORT = Symbol("abort");

function sleep(ms: number, sig: AbortSignal) {
  return new Promise<void>((res) => {
    if (sig.aborted) return res();
    let id = 0;
    const onAbort = () => { window.clearTimeout(id); res(); };
    id = window.setTimeout(() => { sig.removeEventListener("abort", onAbort); res(); }, Math.max(0, ms));
    sig.addEventListener("abort", onAbort, { once: true });
  });
}

function abortable<V>(p: Promise<V>, sig: AbortSignal) {
  return new Promise<V | undefined>((res) => {
    if (sig.aborted) return res(undefined);
    const onAbort = () => res(undefined);
    sig.addEventListener("abort", onAbort, { once: true });
    p.then(
      (v) => { sig.removeEventListener("abort", onAbort); res(v); },
      () => { sig.removeEventListener("abort", onAbort); res(undefined); }
    );
  });
}

/* ───────────────────────────── dotted orb ───────────────────────────── */
// The renderer lives in lib/orb-engine (shared with SphuraOrb); dots follow the theme (.dark on <html>).

/* ───────────────────────────── runtime ───────────────────────────── */
interface UI {
  setPhase(p: Phase): void;
  swapLabel(name: string): void;
  resetLabel(): void;
  setAnswer(s: string): void;
  clearInput(): void;
  live(s: string): void;
  lock(on: boolean): void;
  idleReady(): void;
  focusAnswer(): void;
}
interface Env {
  root: HTMLElement; mover: HTMLElement; actor: HTMLElement; form: HTMLElement; ghosts: HTMLElement[];
  canvas: HTMLCanvasElement; pulse: HTMLElement; status: HTMLElement;
  getBody: () => HTMLElement | null;
  ui: UI; getSpeed: () => number; isReduced: () => boolean;
  /** Natural height of the answer content laid out at `width` px. */
  measureAnswer: (width: number) => number;
}
interface RunCfg { onSubmit: (text: string, signal: AbortSignal) => Promise<string> | string; minThink: number }
interface Runtime {
  start(text: string, cfg: RunCfg): boolean;
  escape(): void;
  reset(): void;
  hard(): void;
  home(): void;
  busy(): boolean;
  /** External agent status (statusLabel / statusProgram props); undefined fields fall back to the timer. */
  status(label: string | undefined, program: OrbProgram | undefined): void;
  destroy(): void;
}
interface Sample { t: number; x: number; y: number; d: number }

function sampleAt(h: Sample[], t: number, out: Sample) {
  const n = h.length;
  const copy = (s: Sample) => { out.x = s.x; out.y = s.y; out.d = s.d; };
  if (n === 0) { out.x = 0; out.y = 0; out.d = 0; return; }
  if (t <= h[0].t) return copy(h[0]);
  for (let i = n - 1; i > 0; i--) {
    const a = h[i - 1], b = h[i];
    if (t >= a.t) {
      if (t >= b.t) return copy(b);
      const k = (t - a.t) / (b.t - a.t || 1);
      out.x = lerp(a.x, b.x, k); out.y = lerp(a.y, b.y, k); out.d = lerp(a.d, b.d, k);
      return;
    }
  }
  copy(h[n - 1]);
}

function createRuntime(env: Env): Runtime {
  const { actor, mover, root, status, pulse, ghosts, form } = env;
  const life = new AbortController();
  const geo: Geo = { pw: pillW(), cw: cardW(), H: homeDy(), dir: -1 };
  const orb = createOrb(env.canvas, { size: CANVAS, radius: ORB_R, getSpeed: env.getSpeed, isReduced: env.isReduced, tone: "auto" });
  const vals: Record<string, number> = {};
  const dirty = new Set<string>();
  const CH: Record<string, (v: number) => void> = {};

  let current: AbortController | null = null;
  let idleCtl: AbortController | null = null;
  let busy = false, idling = false, epoch = 0;
  let curX = 0, curY = 0, curD = BALL_SMALL, trailVis = 0, ghostsShown = false;
  let wStagger = 45, wDur = 320;
  const hist: Sample[] = [];
  const tmp: Sample = { t: 0, x: 0, y: 0, d: 0 };

  /* external status: values left over from the previous run are ignored until the parent changes them */
  const ext: { label?: string; program?: OrbProgram } = {};
  const stale: { label?: string; program?: OrbProgram } = {};
  let labelOn = false;
  const effStatus = () => ({
    label: ext.label && ext.label !== stale.label ? ext.label : undefined,
    program: ext.program !== undefined && ext.program !== stale.program ? ext.program : undefined,
  });

  const child = () => {
    const ac = new AbortController();
    if (life.signal.aborted) ac.abort();
    else life.signal.addEventListener("abort", () => ac.abort(), { once: true });
    return ac;
  };

  /* ── flight path + comet trail ── */
  const renderTrail = () => {
    if (trailVis <= 0.001) {
      if (ghostsShown) { ghosts.forEach((g) => (g.style.opacity = "0")); ghostsShown = false; }
      return;
    }
    ghostsShown = true;
    const now = performance.now();
    for (let i = 0; i < ghosts.length; i++) {
      sampleAt(hist, now - (i + 1) * 45, tmp);
      const k = (tmp.d * (1 - 0.08 * (i + 1))) / 100;
      const g = ghosts[i];
      g.style.transform = `translate3d(${(tmp.x - curX).toFixed(2)}px,${(tmp.y - curY).toFixed(2)}px,0) translate(-50%,-50%) scale(${k.toFixed(3)})`;
      g.style.opacity = (0.28 * Math.pow(1 - i / 6, 1.5) * trailVis).toFixed(3);
    }
  };

  const applyPath = () => {
    const u = vals.u ?? 0, H = geo.H;
    curX = bez(u, 0, geo.dir * 0.3 * H, 0);
    curY = bez(u, H, 0.6 * H, 0) + (vals.yOff ?? 0);
    mover.style.transform = `translate3d(${curX.toFixed(2)}px,${curY.toFixed(2)}px,0)`;
    const now = performance.now();
    hist.push({ t: now, x: curX, y: curY, d: curD });
    while (hist.length > 2 && hist[0].t < now - 500) hist.shift();
    renderTrail();
  };

  /* ── answer words ── */
  const applyWords = (v: number) => {
    const body = env.getBody();
    if (!body) return;
    const nodes = body.querySelectorAll<HTMLElement>(".mo-w");
    const total = (nodes.length - 1) * wStagger + wDur;
    const time = v * total;
    const reduced = env.isReduced();
    nodes.forEach((el, i) => {
      const p = E.out(clamp01((time - i * wStagger) / wDur));
      el.style.opacity = fmt(p);
      el.style.transform = p >= 0.999 || reduced ? "none" : `translateY(${fmt((1 - p) * 4)}px)`;
      el.style.filter = p >= 0.999 || reduced ? "none" : `blur(${fmt((1 - p) * 4)}px)`;
    });
  };

  /* ── channels ── */
  ["oGlow", "oHalo", "oPill", "oBall", "oGreen", "oCard", "oRing", "oInput", "oAur", "gs", "cs", "hOp", "dotS", "bloom"].forEach((n) => {
    CH[n] = (v) => actor.style.setProperty("--" + n, fmt(v));
  });
  ["w", "h", "r"].forEach((n) => {
    CH[n] = (v) => {
      actor.style.setProperty("--" + n, fmt(v) + "px");
      if (n === "w") curD = v;
    };
  });
  CH.inScale = (v) => {
    actor.style.setProperty("--inScale", fmt(v));
    form.style.filter = v >= 0.999 ? "none" : `blur(${fmt((1 - v) * 15)}px)`;
  };
  CH.sOp = (v) => status.style.setProperty("--sOp", fmt(v));
  CH.sTy = (v) => status.style.setProperty("--sTy", fmt(v));
  CH.cHalo = (v) => root.style.setProperty("--oCenter", fmt(v));
  CH.u = () => applyPath();
  CH.yOff = () => applyPath();
  CH.trail = (v) => { trailVis = v; renderTrail(); };
  CH.pulse = (v) => {
    if (v < 0) { pulse.style.opacity = "0"; return; }
    pulse.style.opacity = fmt(0.5 * (1 - v));
    pulse.style.transform = `scale(${fmt(1 + v)})`;
  };
  CH.wp = applyWords;
  ORB_KEYS.forEach((name) => {
    CH["orb." + name] = (v) => {
      orb.P[name] = v;
      if (name === "alpha") orb.ensure();
    };
  });

  const set = (ch: string, v: number) => { vals[ch] = v; dirty.add(ch); };
  const flush = () => { dirty.forEach((ch) => CH[ch]?.(vals[ch])); dirty.clear(); };
  const setNow = (ch: string, v: number) => { vals[ch] = v; CH[ch]?.(v); };
  const resetChannels = () => {
    setNow("w", geo.pw);
    for (const ch of Object.keys(INIT)) setNow(ch, INIT[ch]);
  };

  /* ── timeline engine ── */
  const play = (tracks: Track[], sig: AbortSignal) =>
    new Promise<void>((res) => {
      if (sig.aborted) return res();
      const end = tracks.reduce((m, k) => Math.max(m, k.t1), 0);
      const done = new Set<Track>();
      let raf = 0, t = 0, last = performance.now();
      const onAbort = () => { cancelAnimationFrame(raf); res(); };
      const finish = () => { sig.removeEventListener("abort", onAbort); res(); };
      const step = (now: number) => {
        const dt = Math.max(0, Math.min(100, now - last));
        last = now;
        t += dt * env.getSpeed();
        for (const k of tracks) {
          if (done.has(k) || t < k.t0) continue;
          const p = Math.min(1, (t - k.t0) / Math.max(1, k.t1 - k.t0));
          set(k.ch, k.from + (k.to - k.from) * (k.ease ?? E.io)(p));
          if (p === 1) done.add(k);
        }
        flush(); // one DOM write pass per frame
        if (t >= end) finish(); else raf = requestAnimationFrame(step);
      };
      sig.addEventListener("abort", onAbort, { once: true });
      raf = requestAnimationFrame(step);
    });

  /* ── thinking labels ── */
  const labelLoop = async (sig: AbortSignal, ctl: { stop: boolean }) => {
    let i = 0;
    for (;;) {
      await sleep(1150 / env.getSpeed(), sig);
      if (sig.aborted || ctl.stop) return;
      i = (i + 1) % COPY.labels.length;
      const st = effStatus();
      orb.P.prog = st.program ?? i % 4;
      if (st.label === undefined) env.ui.swapLabel(COPY.labels[i]);
    }
  };

  /* ── long answers: widen + grow the card to fit (max ~55vh, then it scrolls) ── */
  const fitCard = (reduced: boolean, sig: AbortSignal) => {
    if (env.measureAnswer(geo.cw) <= CARD_H + 1) return Promise.resolve();
    const w = Math.max(geo.cw, wideW());
    const h = Math.min(maxCardH(), Math.max(CARD_H, env.measureAnswer(w)));
    if (reduced) { setNow("w", w); setNow("h", h); return Promise.resolve(); }
    return play([T("w", geo.cw, w, 0, 480, E.card), T("h", CARD_H, h, 0, 480, E.card)], sig);
  };

  /* ── orchestrator ── */
  const run = async (text: string, sig: AbortSignal, cfg: RunCfg) => {
    const reduced = env.isReduced();
    const go = async (tracks: Track[]) => {
      await play(tracks, sig);
      if (sig.aborted) throw ABORT;
    };
    try {
      env.ui.setPhase("launch");
      hist.length = 0;
      if (!reduced) {
        await go(launchTracks(geo));
        setNow("r", ORB_D / 2);
        env.ui.setPhase("assemble");
        await go(ASSEMBLE);
      } else {
        await go(R_OUT);
        setNow("u", 1); setNow("w", ORB_D); setNow("h", ORB_D); setNow("r", ORB_D / 2);
        setNow("sTy", 0); setNow("orb.k", 1); setNow("orb.spin", 0);
        env.ui.setPhase("assemble");
        await go(R_IN);
      }

      /* think — until the answer settled AND the minimum time elapsed */
      env.ui.setPhase("think");
      const st0 = effStatus();
      if (st0.label) env.ui.swapLabel(st0.label);
      env.ui.live(st0.label ?? COPY.labels[0]);
      const ctl = { stop: false };
      void labelLoop(sig, ctl);
      const t0 = performance.now();
      const pending = Promise.resolve()
        .then(() => cfg.onSubmit(text, sig))
        .then((b) => (typeof b === "string" && b.trim() ? b : COPY.answerBody), () => COPY.failed);
      const got = await abortable(pending, sig);
      if (sig.aborted) throw ABORT;
      const body = got ?? COPY.answerBody;
      await sleep(cfg.minThink / env.getSpeed() - (performance.now() - t0), sig);
      ctl.stop = true;
      labelOn = false;
      if (sig.aborted) throw ABORT;

      const words = body.split(/\s+/).filter(Boolean);
      const n = Math.max(1, words.length);

      if (!reduced) {
        env.ui.setPhase("resolve");
        env.ui.swapLabel(COPY.done);
        await go(RESOLVE);

        env.ui.setPhase("condense");
        await go(CONDENSE);

        env.ui.setPhase("unfold");
        wDur = 320;
        wStagger = n > 1 ? Math.min(45, 280 / (n - 1)) : 0;
        env.ui.setAnswer(body);
        await go(unfoldTracks(geo, (n - 1) * wStagger + wDur));
      } else {
        env.ui.setPhase("resolve");
        env.ui.swapLabel(COPY.done);
        await go(R_RESOLVE);
        await sleep(350 / env.getSpeed(), sig);
        if (sig.aborted) throw ABORT;

        env.ui.setPhase("condense");
        setNow("gs", 1);
        await go(R_CONDENSE);

        env.ui.setPhase("unfold");
        wDur = 250;
        wStagger = 0;
        env.ui.setAnswer(body);
        await go(R_GREEN_OUT);
        setNow("w", geo.cw); setNow("h", CARD_H); setNow("r", 20); setNow("dotS", 1);
        await go(rCardIn(wDur));
      }

      await fitCard(reduced, sig);
      if (sig.aborted) throw ABORT;

      env.ui.setPhase("answered");
      env.ui.live("Answer ready: " + body);
      env.ui.focusAnswer();
    } catch (e) {
      if (e === ABORT) return;
      hard();
    }
  };

  /* ── return to the idle pill ── */
  const toIdle = async (kind: "reset" | "esc") => {
    if (idling) return;
    idling = true;
    const my = ++epoch;
    const ac = child();
    idleCtl = ac;
    const sig = ac.signal;
    const outMs = kind === "reset" ? 240 : 200;
    const inMs = kind === "reset" ? 420 : 200;
    labelOn = false;
    env.ui.setPhase("reset");

    const out: Track[] = [T("cHalo", vals.cHalo ?? 0, 0, 0, outMs, E.out)];
    for (const ch of FADE) {
      const v = vals[ch] ?? 0;
      if (v > 0.001) out.push(T(ch, v, 0, 0, outMs, E.out));
    }
    if (kind === "reset") out.push(T("cs", 1, 0.98, 0, outMs, E.out));
    await play(out, sig);
    if (sig.aborted || my !== epoch) return;

    setNow("pulse", -1);
    env.ui.setAnswer("");
    env.ui.resetLabel();
    env.ui.clearInput();
    orb.reset();
    hist.length = 0;
    geo.pw = pillW(); geo.cw = cardW(); geo.H = homeDy();
    resetChannels();
    const pillCh = ["oPill", "oInput", "oGlow", "oAur", "oRing"];
    pillCh.forEach((ch) => setNow(ch, 0));
    setNow("yOff", kind === "reset" ? 8 : 0);
    const inn: Track[] = pillCh.map((ch) => T(ch, 0, 1, 0, inMs, E.out));
    if (kind === "reset") inn.push(T("yOff", 8, 0, 0, inMs, E.out));
    await play(inn, sig);
    if (sig.aborted || my !== epoch) return;

    resetChannels();
    current = null; idleCtl = null; busy = false; idling = false;
    env.ui.lock(false);
    env.ui.setPhase("idle");
    env.ui.idleReady();
  };

  function hard() {
    epoch++;
    labelOn = false;
    current?.abort(); current = null;
    idleCtl?.abort(); idleCtl = null;
    orb.reset();
    hist.length = 0;
    env.ui.setAnswer("");
    env.ui.resetLabel();
    geo.pw = pillW(); geo.cw = cardW(); geo.H = homeDy();
    resetChannels();
    setNow("pulse", -1);
    busy = false; idling = false;
    env.ui.lock(false);
    env.ui.setPhase("idle");
    env.ui.idleReady();
  }

  resetChannels();

  return {
    start(text, cfg) {
      if (busy) return false;
      busy = true;
      geo.pw = pillW(); geo.cw = cardW(); geo.H = homeDy(); // snapshot once, never read layout in frames
      geo.dir = -geo.dir;
      orb.reset();
      stale.label = ext.label;
      stale.program = ext.program;
      labelOn = true;
      setNow("u", 0);
      const ac = child();
      current = ac;
      env.ui.lock(true);
      void run(text, ac.signal, cfg);
      return true;
    },
    escape() {
      if (!busy || idling) return;
      current?.abort();
      void toIdle("esc");
    },
    reset() {
      if (!busy || idling) return;
      void toIdle("reset");
    },
    hard,
    home() {
      if (busy) return;
      geo.pw = pillW(); geo.cw = cardW(); geo.H = homeDy();
      setNow("w", geo.pw);
      setNow("u", 0);
    },
    busy: () => busy,
    status(label, program) {
      label = label || undefined;
      if (label !== ext.label) { ext.label = label; stale.label = undefined; }
      if (program !== ext.program) { ext.program = program; stale.program = undefined; }
      if (!busy || idling || !labelOn) return;
      const st = effStatus();
      if (st.program !== undefined) orb.P.prog = st.program;
      if (st.label) { env.ui.swapLabel(st.label); env.ui.live(st.label); }
    },
    destroy() {
      life.abort();
      orb.destroy();
    },
  };
}

/* ───────────────────────────── component ───────────────────────────── */
const useIsoLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

export default function MorphOrb(props: MorphOrbProps) {
  const [phase, setPhaseState] = useState<Phase>("idle");
  const [value, setValue] = useState("");
  const [lbl, setLbl] = useState<{ cur: string; prev: string | null; n: number }>({ cur: COPY.labels[0], prev: null, n: 0 });
  const [answer, setAnswer] = useState("");
  const [dbgSpeed, setDbgSpeed] = useState(1);
  const [debug] = useState(() => typeof window !== "undefined" && /[?&]debug(?:[=&]|$)/.test(window.location.search));

  const rootRef = useRef<HTMLDivElement>(null);
  const moverRef = useRef<HTMLDivElement>(null);
  const actorRef = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pulseRef = useRef<HTMLDivElement>(null);
  const statusRef = useRef<HTMLDivElement>(null);
  const answerRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLParagraphElement>(null);
  const liveRef = useRef<HTMLDivElement>(null);
  const ghostRefs = useRef<(HTMLSpanElement | null)[]>([]);

  const propsRef = useRef(props);
  const speedRef = useRef(Math.max(0.05, props.speed ?? 1));
  useIsoLayoutEffect(() => {
    propsRef.current = props;
    speedRef.current = Math.max(0.05, (props.speed ?? 1) * dbgSpeed);
  });
  const phaseRef = useRef<Phase>("idle");
  const reducedRef = useRef(false);
  const rtRef = useRef<Runtime | null>(null);
  const lastTextRef = useRef("");
  const timers = useRef<{ typing?: number; shake?: number; flash?: number }>({});

  useIsoLayoutEffect(() => {
    const root = rootRef.current, mover = moverRef.current, actor = actorRef.current, canvas = canvasRef.current;
    const pulse = pulseRef.current, status = statusRef.current, form = formRef.current;
    const ghosts = ghostRefs.current.filter((g): g is HTMLSpanElement => !!g);
    if (!root || !mover || !actor || !canvas || !pulse || !status || !form) return;

    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    reducedRef.current = mq.matches;
    const onMq = (e: MediaQueryListEvent) => { reducedRef.current = e.matches; };
    mq.addEventListener("change", onMq);

    const rt = createRuntime({
      root, mover, actor, form, ghosts, canvas, pulse, status,
      getBody: () => bodyRef.current,
      getSpeed: () => speedRef.current,
      isReduced: () => reducedRef.current,
      measureAnswer: (width) => {
        const el = answerRef.current;
        if (!el) return 0;
        const s = el.style;
        const prev = [s.width, s.right, s.bottom, s.overflow];
        s.width = width + "px"; s.right = "auto"; s.bottom = "auto"; s.overflow = "visible";
        const h = el.offsetHeight;
        s.width = prev[0]; s.right = prev[1]; s.bottom = prev[2]; s.overflow = prev[3];
        return h;
      },
      ui: {
        setPhase: (p) => { phaseRef.current = p; setPhaseState(p); },
        swapLabel: (name) => setLbl((l) => (l.cur === name ? l : { cur: name, prev: l.cur, n: l.n + 1 })),
        resetLabel: () => setLbl((l) => ({ cur: COPY.labels[0], prev: null, n: l.n + 1 })),
        setAnswer: (s) => setAnswer(s),
        clearInput: () => setValue(""),
        live: (s) => { if (liveRef.current) liveRef.current.textContent = s; },
        lock: (on) => { form.toggleAttribute("inert", on); },
        idleReady: () => { inputRef.current?.focus({ preventScroll: true }); },
        focusAnswer: () => { answerRef.current?.focus({ preventScroll: true }); },
      },
    });
    rtRef.current = rt;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && phaseRef.current !== "idle" && phaseRef.current !== "reset") {
        e.preventDefault();
        rt.escape();
      }
    };
    const onResize = () => {
      if (phaseRef.current === "idle" && !rt.busy()) rt.home();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    inputRef.current?.focus({ preventScroll: true });

    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
      mq.removeEventListener("change", onMq);
      window.clearTimeout(timers.current.typing);
      window.clearTimeout(timers.current.shake);
      window.clearTimeout(timers.current.flash);
      rt.destroy();
      rtRef.current = null;
    };
  }, []);

  /* real agent status (optional): label + light program follow the parent while thinking */
  const { statusLabel, statusProgram } = props;
  useEffect(() => {
    rtRef.current?.status(statusLabel, statusProgram);
  }, [statusLabel, statusProgram]);

  const defaultSubmit = () =>
    new Promise<string>((res) => {
      window.setTimeout(() => res(COPY.answerBody), 4600 / speedRef.current);
    });
  const makeCfg = (): RunCfg => ({
    onSubmit: propsRef.current.onSubmit ?? defaultSubmit,
    minThink: propsRef.current.minThinkMs ?? 3450,
  });

  const shake = () => {
    const a = actorRef.current;
    if (!a) return;
    a.removeAttribute("data-shake");
    void a.offsetWidth;
    a.setAttribute("data-shake", "");
    a.setAttribute("data-flash", "");
    window.clearTimeout(timers.current.shake);
    window.clearTimeout(timers.current.flash);
    timers.current.shake = window.setTimeout(() => a.removeAttribute("data-shake"), 260);
    timers.current.flash = window.setTimeout(() => a.removeAttribute("data-flash"), 200);
  };

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValue(e.target.value);
    const a = actorRef.current;
    if (!a) return;
    a.setAttribute("data-typing", "");
    window.clearTimeout(timers.current.typing);
    timers.current.typing = window.setTimeout(() => a.removeAttribute("data-typing"), 300);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && (e.shiftKey || e.nativeEvent.isComposing)) e.preventDefault();
  };

  const onFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const rt = rtRef.current;
    if (!rt || rt.busy() || phaseRef.current !== "idle") return;
    const text = value.trim();
    if (!text) { shake(); return; }
    lastTextRef.current = text;
    rt.start(text, makeCfg());
  };

  const onReset = () => {
    if (phaseRef.current === "answered") rtRef.current?.reset();
  };

  const replay = () => {
    const rt = rtRef.current;
    if (!rt) return;
    const text = lastTextRef.current || "hello";
    lastTextRef.current = text;
    rt.hard();
    setValue(text);
    window.requestAnimationFrame(() => { rt.start(text, makeCfg()); });
  };

  const ready = value.trim().length > 0;
  const words = answer.split(/\s+/).filter(Boolean);

  const labelInner = (name: string) =>
    name === COPY.done ? (
      <span className="mo-lab-done">{name}</span>
    ) : (
      <>
        <span className="mo-lab-t">{name}</span>
        <span className="mo-dots" aria-hidden="true"><i /><i /><i /></span>
      </>
    );

  return (
    <div className="mo-root" data-phase={phase} ref={rootRef}>
      <div className="mo-bg" aria-hidden="true" />
      <div className="mo-halo" aria-hidden="true" />

      <div className="mo-mover" ref={moverRef}>
        {Array.from({ length: 6 }).map((_, i) => (
          <span key={i} className="mo-trail" aria-hidden="true" ref={(el) => { ghostRefs.current[i] = el; }} />
        ))}

        <div className="mo-actor" ref={actorRef}>
          <div className="mo-underglow" aria-hidden="true" />
          <div className="mo-halo-green" aria-hidden="true" />
          <div className="mo-surface" aria-hidden="true">
            <div className="mo-aurora"><i /><i /><i /><i /></div>
          </div>
          <div className="mo-ball" aria-hidden="true" />
          <div className="mo-green" aria-hidden="true" />
          <div className="mo-card" aria-hidden="true" />
          <div className="mo-ring" aria-hidden="true" />

          <form className="mo-input" ref={formRef} onSubmit={onFormSubmit} autoComplete="off">
            <svg className="mo-spark" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M10 3.5l1.7 4.8 4.8 1.7-4.8 1.7L10 16.5l-1.7-4.8L3.5 10l4.8-1.7L10 3.5z" />
              <path d="M18 14.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7.7-1.8z" />
            </svg>
            <input
              ref={inputRef}
              className="mo-field"
              type="text"
              value={value}
              maxLength={200}
              placeholder={props.placeholder ?? COPY.placeholder}
              aria-label="Ask anything"
              spellCheck={false}
              onChange={onChange}
              onKeyDown={onKeyDown}
            />
            <button type="submit" className="mo-send" aria-label={COPY.send} data-ready={ready ? "" : undefined}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 19V5" />
                <path d="M5.5 11.5L12 5l6.5 6.5" />
              </svg>
            </button>
          </form>

          <canvas className="mo-orb" ref={canvasRef} aria-hidden="true" />
          <div className="mo-pulse" ref={pulseRef} aria-hidden="true" />

          <div className="mo-answer" ref={answerRef} tabIndex={-1} role="group" aria-label={COPY.answerTitle}>
            <div className="mo-a-head">
              <i className="mo-a-dot" aria-hidden="true" />
              <span>{COPY.answerTitle}</span>
            </div>
            <p className="mo-a-body" ref={bodyRef}>
              {words.map((w, i) => (
                <React.Fragment key={i}>
                  <span className="mo-w">{w}</span>{" "}
                </React.Fragment>
              ))}
            </p>
          </div>
        </div>
      </div>

      <div className="mo-status" ref={statusRef} aria-hidden="true">
        {lbl.prev !== null && (
          <span key={"p" + lbl.n} className="mo-lab mo-out">{labelInner(lbl.prev)}</span>
        )}
        <span key={"c" + lbl.n} className="mo-lab mo-in">{labelInner(lbl.cur)}</span>
      </div>

      <button type="button" className="mo-reset" onClick={onReset}>{COPY.reset}</button>

      <div className="mo-live" ref={liveRef} role="status" aria-live="polite" />

      {debug && (
        <div className="mo-debug">
          <span className="mo-chip">{phase}</span>
          <label>
            <span>{dbgSpeed.toFixed(2)}×</span>
            <input
              type="range"
              min={0.25}
              max={2}
              step={0.05}
              value={dbgSpeed}
              aria-label="Speed"
              onChange={(e) => setDbgSpeed(parseFloat(e.target.value))}
            />
          </label>
          <button type="button" onClick={replay}>Replay</button>
        </div>
      )}
    </div>
  );
}
