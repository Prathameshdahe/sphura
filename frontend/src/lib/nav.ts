import type { ComponentType } from "react";
import { glyph } from "@/components/icons/glyphs";

type IconLike = ComponentType<{ className?: string; strokeWidth?: number }>;

export interface NavItem {
  to: string;
  label: string;
  /** Longer name for menus and tooltips. */
  title: string;
  icon: IconLike;
}

/** The six spaces of the app, in taskbar order. */
export const SPACES: NavItem[] = [
  { to: "/", label: "Chat", title: "Chat", icon: glyph("chat") },
  { to: "/dashboard", label: "Dashboard", title: "Dashboard", icon: glyph("dashboard") },
  { to: "/markets", label: "Markets", title: "Markets", icon: glyph("candles") },
  { to: "/documents", label: "Documents", title: "Documents", icon: glyph("documents") },
  { to: "/lab", label: "Lab", title: "Model Lab", icon: glyph("lab") },
  { to: "/memory", label: "Memory", title: "Memory", icon: glyph("memory") },
];

/** Index of the space a pathname belongs to ("/" and "/c/:id" are Chat). */
export function spaceIndex(pathname: string): number {
  if (pathname === "/" || pathname.startsWith("/c/")) return 0;
  const i = SPACES.findIndex((s) => s.to !== "/" && (pathname === s.to || pathname.startsWith(`${s.to}/`)));
  return i === -1 ? 0 : i;
}
