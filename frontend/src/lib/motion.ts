import type { Variants } from "framer-motion";

/* Motion vocabulary (FINANCE_PLAN §4): page fade + 8 px rise 220 ms · lists stagger 40 ms · springs for chips ·
   number count-up on KPIs · nothing longer than 400 ms except the orb. MotionConfig reducedMotion="user" in main.tsx
   disables transforms for people who asked for less motion; CountUp (components/motion.tsx) checks the same preference. */

export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

/** Route-level transition (AppShell wraps the outlet in AnimatePresence). */
export const pageMotion = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
  transition: { duration: 0.22, ease: EASE_OUT },
} as const;

export const staggerParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.04, delayChildren: 0.02 } },
};

export const riseItem: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.28, ease: EASE_OUT } },
};

/** Snappy, non-bouncy spring for presses, hovers and small layout moves. */
export const SPRING_SNAPPY = { type: "spring", stiffness: 520, damping: 34, mass: 0.7 } as const;
/** Softer spring for larger layout moves (composer hand-off, dock width). */
export const SPRING_SOFT = { type: "spring", stiffness: 340, damping: 32, mass: 0.9 } as const;

/** Press feedback for buttons / chips: spread onto any motion element (`<motion.button {...press}>`). */
export const press = { whileTap: { scale: 0.97 }, transition: SPRING_SNAPPY } as const;
/** Press feedback for small icon buttons. */
export const pressIcon = { whileTap: { scale: 0.92 }, transition: SPRING_SNAPPY } as const;

/** Popover / dialog entrance: a short scale-in from 96 %. */
export const popIn = {
  initial: { opacity: 0, scale: 0.96, y: -4 },
  animate: { opacity: 1, scale: 1, y: 0 },
  exit: { opacity: 0, scale: 0.97, y: -2 },
  transition: { duration: 0.16, ease: EASE_OUT },
} as const;

/** Chip / badge entrance: a small spring, no overshoot longer than ~300 ms. */
export const chipSpring = {
  initial: { opacity: 0, scale: 0.85 },
  animate: { opacity: 1, scale: 1 },
  transition: { type: "spring", stiffness: 480, damping: 30, mass: 0.6 },
} as const;
