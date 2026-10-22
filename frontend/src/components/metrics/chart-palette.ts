// Categorical chart palette, violet-led: violet, lilac, slate, teal, amber, rose — separated in hue and lightness so
// neighbouring series stay distinguishable. Assign in fixed order: colour follows the entity, never its rank.
// Light values sit on white cards, dark values on #17171C.
import type { ChartConfig } from "@/components/ui/chart";

export interface ThemeColor {
  light: string;
  dark: string;
}

export const SERIES: readonly ThemeColor[] = [
  { light: "#7c3aed", dark: "#a78bfa" }, // violet
  { light: "#c084fc", dark: "#e9d5ff" }, // lilac
  { light: "#64748b", dark: "#94a3b8" }, // slate
  { light: "#0d9488", dark: "#2dd4bf" }, // teal
  { light: "#d97706", dark: "#fbbf24" }, // amber
  { light: "#e11d48", dark: "#fb7185" }, // rose
];

/** Neutral for an aggregated "Other" bucket. */
export const OTHER: ThemeColor = { light: "#d4d4d8", dark: "#3f3f46" };

export const VIOLET = SERIES[0];
export const LILAC = SERIES[1];
export const SLATE = SERIES[2];
export const TEAL = SERIES[3];
export const AMBER = SERIES[4];
export const ROSE = SERIES[5];

export function seriesConfig(entries: { key: string; label: string; color: ThemeColor }[]): ChartConfig {
  const config: ChartConfig = {};
  for (const e of entries) config[e.key] = { label: e.label, theme: { light: e.color.light, dark: e.color.dark } };
  return config;
}

/** Recharts enter animation: within the 400 ms motion budget, and off for people who asked for less motion. */
const reducedMotion = typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
export const CHART_ANIM = { isAnimationActive: !reducedMotion, animationDuration: 400, animationEasing: "ease-out" } as const;
