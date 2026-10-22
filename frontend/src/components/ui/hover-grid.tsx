import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Interactive background grid: invisible rounded squares that light up as frosted violet tiles under the cursor
 * (neighbours glow a little), then fade out over ~750 ms, leaving a short trail.
 *
 * Cheap by construction: one <canvas>, pointer handling coalesced into requestAnimationFrame, the loop only runs
 * while tiles are fading, nothing happens in a hidden tab. The canvas has pointer-events: none (never blocks clicks
 * or text selection) and renders nothing for reduced-motion or touch-only visitors.
 */
const FADE_MS = 750;
const NEIGHBOUR = 0.32;

function useEnabled(): boolean {
  const query = "(prefers-reduced-motion: no-preference) and (hover: hover) and (pointer: fine)";
  const [on, setOn] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const update = () => setOn(mql.matches);
    mql.addEventListener("change", update);
    return () => mql.removeEventListener("change", update);
  }, []);
  return on;
}

export function HoverGrid({ cell = 50, gap = 4, radius = 7, className }: { cell?: number; gap?: number; radius?: number; className?: string }) {
  const enabled = useEnabled();
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!enabled || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const pitch = cell + gap;
    const tiles = new Map<string, number>(); // "col,row" → intensity 0..1
    let width = 0;
    let height = 0;
    let dpr = 1;
    let raf = 0;
    let last = 0;
    let pending: { x: number; y: number } | null = null;
    let lastCell = "";

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      dpr = Math.min(2, window.devicePixelRatio || 1);
      width = r.width;
      height = r.height;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const light = (col: number, row: number, value: number) => {
      if (col < 0 || row < 0 || col * pitch > width || row * pitch > height) return;
      const key = `${col},${row}`;
      tiles.set(key, Math.max(tiles.get(key) ?? 0, value));
    };

    const draw = () => {
      const dark = document.documentElement.classList.contains("dark");
      ctx.clearRect(0, 0, width, height);
      for (const [key, v] of tiles) {
        const [col, row] = key.split(",").map(Number);
        const x = col * pitch + gap / 2;
        const y = row * pitch + gap / 2;
        const a = v * v; // ease the fade
        ctx.save();
        ctx.beginPath();
        ctx.roundRect(x, y, cell, cell, radius);
        if (dark) {
          ctx.shadowColor = `rgba(139, 92, 246, ${0.75 * a})`;
          ctx.shadowBlur = 18 * a;
          ctx.fillStyle = `rgba(139, 92, 246, ${0.5 * a})`;
        } else {
          ctx.shadowColor = `rgba(124, 58, 237, ${0.35 * a})`;
          ctx.shadowBlur = 12 * a;
          ctx.fillStyle = `rgba(124, 58, 237, ${0.3 * a})`;
        }
        ctx.fill();
        ctx.shadowBlur = 0;
        // frosted glass: a soft white sheen and a bright top edge
        const sheen = ctx.createLinearGradient(x, y, x + cell, y + cell);
        sheen.addColorStop(0, `rgba(255, 255, 255, ${(dark ? 0.22 : 0.4) * a})`);
        sheen.addColorStop(0.6, "rgba(255, 255, 255, 0)");
        ctx.fillStyle = sheen;
        ctx.fill();
        ctx.lineWidth = 1;
        ctx.strokeStyle = `rgba(255, 255, 255, ${(dark ? 0.35 : 0.6) * a})`;
        ctx.stroke();
        ctx.restore();
      }
    };

    const frame = (now: number) => {
      raf = 0;
      const dt = last ? Math.min(64, now - last) : 16;
      last = now;
      if (pending) {
        const { x, y } = pending;
        pending = null;
        const col = Math.floor(x / pitch);
        const row = Math.floor(y / pitch);
        const key = `${col},${row}`;
        if (key !== lastCell) {
          lastCell = key;
          for (let dc = -1; dc <= 1; dc++) for (let dr = -1; dr <= 1; dr++) if (dc || dr) light(col + dc, row + dr, NEIGHBOUR);
        }
        light(col, row, 1);
      }
      for (const [key, v] of tiles) {
        const next = v - dt / FADE_MS;
        if (next <= 0) tiles.delete(key);
        else tiles.set(key, next);
      }
      draw();
      if (tiles.size > 0 || pending) raf = requestAnimationFrame(frame);
      else last = 0;
    };

    const kick = () => {
      if (!raf && !document.hidden) raf = requestAnimationFrame(frame);
    };

    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      const r = canvas.getBoundingClientRect();
      const x = e.clientX - r.left;
      const y = e.clientY - r.top;
      if (x < 0 || y < 0 || x > r.width || y > r.height) return;
      pending = { x, y };
      kick();
    };
    const onVisibility = () => {
      if (document.hidden && raf) {
        cancelAnimationFrame(raf);
        raf = 0;
        last = 0;
        tiles.clear();
        ctx.clearRect(0, 0, width, height);
      }
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("visibilitychange", onVisibility);
      ro.disconnect();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [enabled, cell, gap, radius]);

  if (!enabled) return null;
  return <canvas ref={canvasRef} aria-hidden className={cn("pointer-events-none absolute inset-0 h-full w-full", className)} />;
}

export default HoverGrid;
