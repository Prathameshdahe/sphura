import type { ReactNode, SVGProps } from "react";

/* Sphura glyphs: one hand-drawn icon family (24-unit grid, 2px rounded strokes, a soft duotone fill in the same
   colour). Used for the spaces, the specialists, the starters, the landing page and for emoji that a model writes
   into an answer (they are swapped for these glyphs, never shown as raw emoji). */

export type GlyphName =
  | "chat"
  | "dashboard"
  | "markets"
  | "documents"
  | "lab"
  | "memory"
  | "plus"
  | "piggy"
  | "receipt"
  | "house-coin"
  | "candles"
  | "doc-search"
  | "statement"
  | "bulb"
  | "check"
  | "cross"
  | "warning"
  | "info"
  | "question"
  | "coin"
  | "bank"
  | "trend-up"
  | "trend-down"
  | "chart"
  | "target"
  | "calendar"
  | "document"
  | "home"
  | "star"
  | "pin"
  | "arrow"
  | "shield"
  | "mic"
  | "wave"
  | "route"
  | "tools"
  | "pen"
  | "merge"
  | "chip"
  | "sparkle";

const DUO = { fill: "currentColor", fillOpacity: 0.2, stroke: "none" } as const;

/** Each glyph: duotone fill shapes first (no stroke), then the 2px outline. */
const PATHS: Record<GlyphName, ReactNode> = {
  chat: (
    <>
      <path {...DUO} d="M3.5 5.5A2.5 2.5 0 0 1 6 3h7.5A2.5 2.5 0 0 1 16 5.5v4a2.5 2.5 0 0 1-2.5 2.5H9l-3.3 2.6c-.4.3-1 0-1-.5V12A2.5 2.5 0 0 1 3.5 9.5Z" />
      <path d="M3.5 5.5A2.5 2.5 0 0 1 6 3h7.5A2.5 2.5 0 0 1 16 5.5v4a2.5 2.5 0 0 1-2.5 2.5H9l-3.3 2.6c-.4.3-1 0-1-.5V12A2.5 2.5 0 0 1 3.5 9.5Z" />
      <path d="M16 7.5h2A2.5 2.5 0 0 1 20.5 10v4a2.5 2.5 0 0 1-2.5 2.5h-.5v2.6c0 .5-.6.8-1 .5L13.2 17H11a2.5 2.5 0 0 1-2.5-2.5V12" />
      <circle cx="7.3" cy="7.5" r=".9" fill="currentColor" stroke="none" />
      <circle cx="9.8" cy="7.5" r=".9" fill="currentColor" stroke="none" />
      <circle cx="12.3" cy="7.5" r=".9" fill="currentColor" stroke="none" />
    </>
  ),
  dashboard: (
    <>
      <rect {...DUO} x="3.5" y="3.5" width="7" height="7" rx="2" />
      <rect x="3.5" y="3.5" width="7" height="7" rx="2" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="2" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="2" />
      <path d="M14 20.5v-2.5M17.25 20.5v-4.5M20.5 20.5v-7" />
    </>
  ),
  markets: (
    <>
      <path {...DUO} d="M3.5 17.5 9 12l3.5 3 8-8v13.5h-17Z" />
      <path d="M3.5 17.5 9 12l3.5 3 8-8" />
      <path d="M15 7h5.5v5.5" />
    </>
  ),
  documents: (
    <>
      <path {...DUO} d="M9 3h6.5L20 7.5V16a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M9 3h6.5L20 7.5V16a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M15 3v4.5h5M10.5 11h6M10.5 14h4" />
      <path d="M7 6.5h-.5A2.5 2.5 0 0 0 4 9v9.5A2.5 2.5 0 0 0 6.5 21H14" />
    </>
  ),
  lab: (
    <>
      <path {...DUO} d="M7.1 14h7.8l1.9 3.4a1.6 1.6 0 0 1-1.4 2.4H6.6a1.6 1.6 0 0 1-1.4-2.4Z" />
      <path d="M8 3h5M9 3v5.6L3.8 17.4A2.4 2.4 0 0 0 5.9 21h9.2a2.4 2.4 0 0 0 2.1-3.6L12 8.6V3" />
      <path d="M6 14h9" />
      <circle cx="9" cy="17.3" r=".9" fill="currentColor" stroke="none" />
      <circle cx="12.1" cy="16.4" r=".6" fill="currentColor" stroke="none" />
      <path d="M18.5 3v4M16.5 5h4M20.5 9.5v2M19.5 10.5h2" />
    </>
  ),
  memory: (
    <>
      <rect {...DUO} x="6" y="6" width="12" height="12" rx="3" />
      <rect x="6" y="6" width="12" height="12" rx="3" />
      <rect x="9.5" y="9.5" width="5" height="5" rx="1.2" />
      <path d="M9.5 2.5V6M14.5 2.5V6M9.5 18v3.5M14.5 18v3.5M2.5 9.5H6M2.5 14.5H6M18 9.5h3.5M18 14.5h3.5" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  piggy: (
    <>
      <path {...DUO} d="M4.5 12.5a7.25 5.9 0 1 1 14.5 0 7.25 5.9 0 0 1-14.5 0Z" />
      <path d="M4.5 12.5a7.25 5.9 0 1 1 14.5 0 7.25 5.9 0 0 1-14.5 0Z" />
      <path d="M19 11h1.6a.9.9 0 0 1 .9.9v1.6a.9.9 0 0 1-.9.9H19M8.3 17.4V20M15.2 17.4V20M8.8 7.3 7.7 4.6l3 1.3M10.6 8.6h3" />
      <circle cx="15.6" cy="11" r=".95" fill="currentColor" stroke="none" />
    </>
  ),
  receipt: (
    <>
      <path {...DUO} d="M6 3h12v18l-3-2-3 2-3-2-3 2Z" />
      <path d="M6 3h12v18l-3-2-3 2-3-2-3 2Z" />
      <path d="M9.2 14.8 14.8 9.2" />
      <circle cx="9.6" cy="9.6" r="1.25" />
      <circle cx="14.4" cy="14.4" r="1.25" />
    </>
  ),
  "house-coin": (
    <>
      <path {...DUO} d="M5.5 9.5V19a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5V9.5L12 4.6Z" />
      <path d="M3 11 12 4l9 7" />
      <path d="M5.5 9.5V19a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5V9.5" />
      <circle cx="12" cy="15" r="3" />
      <path d="M12 13.6v2.8" />
    </>
  ),
  candles: (
    <>
      <rect {...DUO} x="5.5" y="6.5" width="3" height="9" rx="1" />
      <rect {...DUO} x="15.5" y="5.5" width="3" height="7.5" rx="1" />
      <path d="M7 3.5v3M7 15.5v4.5M12 6v3M12 17v3.5M17 3v2.5M17 13v4" />
      <rect x="5.5" y="6.5" width="3" height="9" rx="1" />
      <rect x="10.5" y="9" width="3" height="8" rx="1" />
      <rect x="15.5" y="5.5" width="3" height="7.5" rx="1" />
    </>
  ),
  "doc-search": (
    <>
      <circle {...DUO} cx="16" cy="16" r="3.4" />
      <path d="M12 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6.5L18 7.5v3" />
      <path d="M13.5 3v4.5H18M8 10.5h4.5M8 14h2.5" />
      <circle cx="16" cy="16" r="3.4" />
      <path d="m18.5 18.5 2.5 2.5" />
    </>
  ),
  statement: (
    <>
      <path {...DUO} d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v5h5M9 17.5v-3M12 17.5v-5.5M15 17.5v-2" />
    </>
  ),
  bulb: (
    <>
      <path {...DUO} d="M12 3a6 6 0 0 0-3.7 10.7c.7.6 1.2 1.4 1.2 2.3v.5h5V16c0-.9.5-1.7 1.2-2.3A6 6 0 0 0 12 3Z" />
      <path d="M12 3a6 6 0 0 0-3.7 10.7c.7.6 1.2 1.4 1.2 2.3v.5h5V16c0-.9.5-1.7 1.2-2.3A6 6 0 0 0 12 3Z" />
      <path d="M9.6 19h4.8M10.6 21.5h2.8M12 8.5v3.5" />
    </>
  ),
  check: (
    <>
      <circle {...DUO} cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.4 2.7 2.7 5.3-5.6" />
    </>
  ),
  cross: (
    <>
      <circle {...DUO} cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="9" />
      <path d="m9 9 6 6M15 9l-6 6" />
    </>
  ),
  warning: (
    <>
      <path {...DUO} d="M10.3 4.3a2 2 0 0 1 3.4 0l7.4 12.8a2 2 0 0 1-1.7 2.9H4.6a2 2 0 0 1-1.7-2.9Z" />
      <path d="M10.3 4.3a2 2 0 0 1 3.4 0l7.4 12.8a2 2 0 0 1-1.7 2.9H4.6a2 2 0 0 1-1.7-2.9Z" />
      <path d="M12 9.5v4" />
      <circle cx="12" cy="16.6" r=".7" fill="currentColor" />
    </>
  ),
  info: (
    <>
      <circle {...DUO} cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5.5" />
      <circle cx="12" cy="7.8" r=".7" fill="currentColor" />
    </>
  ),
  question: (
    <>
      <circle {...DUO} cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="9" />
      <path d="M9.6 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.4" />
      <circle cx="12" cy="16.8" r=".7" fill="currentColor" />
    </>
  ),
  coin: (
    <>
      <path {...DUO} d="M5 7c0-1.4 3.1-2.5 7-2.5s7 1.1 7 2.5-3.1 2.5-7 2.5S5 8.4 5 7Z" />
      <path d="M5 7c0-1.4 3.1-2.5 7-2.5s7 1.1 7 2.5-3.1 2.5-7 2.5S5 8.4 5 7Z" />
      <path d="M5 7v5c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V7M5 12v5c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-5" />
    </>
  ),
  bank: (
    <>
      <path {...DUO} d="M3 9.5 12 4l9 5.5Z" />
      <path d="M3 9.5 12 4l9 5.5ZM5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20.5h18" />
    </>
  ),
  "trend-up": (
    <>
      <path d="M3.5 17 9 11.5l3.5 3.5 8-8" />
      <path d="M15 7h5.5v5.5" />
    </>
  ),
  "trend-down": (
    <>
      <path d="M3.5 7 9 12.5 12.5 9l8 8" />
      <path d="M15 17h5.5v-5.5" />
    </>
  ),
  chart: (
    <>
      <rect {...DUO} x="10.5" y="7" width="3" height="11.5" rx="1" />
      <path d="M4 20.5h16" />
      <rect x="5.5" y="12" width="3" height="6.5" rx="1" />
      <rect x="10.5" y="7" width="3" height="11.5" rx="1" />
      <rect x="15.5" y="10" width="3" height="8.5" rx="1" />
    </>
  ),
  target: (
    <>
      <circle {...DUO} cx="12" cy="12" r="5.5" />
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5.5" />
      <circle cx="12" cy="12" r="1.8" fill="currentColor" />
    </>
  ),
  calendar: (
    <>
      <rect {...DUO} x="3.5" y="5" width="17" height="15.5" rx="2.5" />
      <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
      <path d="M3.5 9.5h17M8 3v4M16 3v4" />
      <circle cx="8.5" cy="14" r=".8" fill="currentColor" />
      <circle cx="12" cy="14" r=".8" fill="currentColor" />
      <circle cx="15.5" cy="14" r=".8" fill="currentColor" />
    </>
  ),
  document: (
    <>
      <path {...DUO} d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v5h5M8.5 13h7M8.5 16.5h4.5" />
    </>
  ),
  home: (
    <>
      <path {...DUO} d="M5.5 9.5V19a1.5 1.5 0 0 0 1.5 1.5h3.5v-5h3v5H17a1.5 1.5 0 0 0 1.5-1.5V9.5L12 4.6Z" />
      <path d="M3 11 12 4l9 7" />
      <path d="M5.5 9.5V19a1.5 1.5 0 0 0 1.5 1.5h3.5v-5h3v5H17a1.5 1.5 0 0 0 1.5-1.5V9.5" />
    </>
  ),
  star: (
    <>
      <path {...DUO} d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9Z" />
      <path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9Z" />
    </>
  ),
  pin: (
    <>
      <path {...DUO} d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z" />
      <path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z" />
      <circle cx="12" cy="10" r="2.3" />
    </>
  ),
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  shield: (
    <>
      <path {...DUO} d="M12 3 5 6v5.5c0 4.4 3 8.2 7 9.5 4-1.3 7-5.1 7-9.5V6Z" />
      <path d="M12 3 5 6v5.5c0 4.4 3 8.2 7 9.5 4-1.3 7-5.1 7-9.5V6Z" />
      <path d="m9 12 2.2 2.2L15.5 10" />
    </>
  ),
  mic: (
    <>
      <rect {...DUO} x="9" y="3" width="6" height="11" rx="3" />
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6" />
    </>
  ),
  wave: <path d="M3 12h2M7 8v8M11 5v14M15 8.5v7M19 10.5v3M21 12h0" />,
  route: (
    <>
      <circle {...DUO} cx="6" cy="18" r="2.5" />
      <circle {...DUO} cx="18" cy="6" r="2.5" />
      <circle cx="6" cy="18" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <path d="M8.5 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.5" />
    </>
  ),
  tools: (
    <>
      <path {...DUO} d="M14.5 3.5a4.5 4.5 0 0 0-4.3 5.9l-6 6a2 2 0 0 0 2.8 2.8l6-6a4.5 4.5 0 0 0 5.9-5.6l-2.6 2.6-2.4-.5-.5-2.4Z" />
      <path d="M14.5 3.5a4.5 4.5 0 0 0-4.3 5.9l-6 6a2 2 0 0 0 2.8 2.8l6-6a4.5 4.5 0 0 0 5.9-5.6l-2.6 2.6-2.4-.5-.5-2.4Z" />
    </>
  ),
  sparkle: <path fill="currentColor" stroke="none" d="M12 2.5c.6 4.3 2.2 7 4.2 8.2 1.4.8 3 1.2 5.3 1.3-2.3.1-3.9.5-5.3 1.3-2 1.2-3.6 3.9-4.2 8.2-.6-4.3-2.2-7-4.2-8.2-1.4-.8-3-1.2-5.3-1.3 2.3-.1 3.9-.5 5.3-1.3 2-1.2 3.6-3.9 4.2-8.2Z" />,
  merge: (
    <>
      <circle {...DUO} cx="18.5" cy="12" r="2.5" />
      <path d="M3.5 5.5H7c1.6 0 2.9.8 3.7 2.1L13 11.3c.4.5 1 .7 1.6.7H16M3.5 18.5H7c1.6 0 2.9-.8 3.7-2.1L13 12.7M3.5 12H16" />
      <circle cx="18.5" cy="12" r="2.5" />
    </>
  ),
  chip: (
    <>
      <rect {...DUO} x="5" y="5" width="14" height="14" rx="3" />
      <rect x="5" y="5" width="14" height="14" rx="3" />
      <path d="M9 9h6v6H9zM9 2.5V5M15 2.5V5M9 19v2.5M15 19v2.5M2.5 9H5M2.5 15H5M19 9h2.5M19 15h2.5" />
    </>
  ),
  pen: (
    <>
      <path {...DUO} d="m15 4.5 4.5 4.5L9 19.5l-5 1 1-5Z" />
      <path d="m15 4.5 4.5 4.5L9 19.5l-5 1 1-5ZM13 6.5l4.5 4.5" />
    </>
  ),
};

export interface GlyphProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: GlyphName;
  /** Accessible name; without it the glyph is decorative (aria-hidden). */
  title?: string;
}

/** One Sphura glyph. Size it with `size-*` classes (defaults to 1em); colour follows `currentColor`. */
export function Glyph({ name, title, className, ...rest }: GlyphProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}

/** Glyph as a component with a fixed name (drop-in where a `LucideIcon`-like component is expected). */
export function glyph(name: GlyphName) {
  function NamedGlyph({ className, strokeWidth }: { className?: string; strokeWidth?: number }) {
    return <Glyph name={name} className={className} strokeWidth={strokeWidth} />;
  }
  NamedGlyph.displayName = `Glyph(${name})`;
  return NamedGlyph;
}
