import { useEffect, useRef, useState, type ComponentProps, type ReactNode } from "react";
import { animate, motion, useReducedMotion } from "framer-motion";
import { EASE_OUT, riseItem, staggerParent } from "@/lib/motion";
import { cn } from "@/lib/utils";

type StaggerProps = Omit<ComponentProps<typeof motion.div>, "variants" | "initial" | "animate"> & {
  /** Animate when scrolled into view instead of on mount (long pages). */
  inView?: boolean;
};

/** Container whose direct `<StaggerItem>` children rise in one after another (40 ms apart). */
export function Stagger({ inView = false, children, ...rest }: StaggerProps) {
  return (
    <motion.div
      variants={staggerParent}
      initial="hidden"
      {...(inView ? { whileInView: "show", viewport: { once: true, margin: "-40px" } } : { animate: "show" })}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, ...rest }: ComponentProps<typeof motion.div>) {
  return (
    <motion.div variants={riseItem} {...rest}>
      {children}
    </motion.div>
  );
}

interface CountUpProps {
  value: number;
  /** Formats the animated number (defaults to a locale integer). */
  format?: (n: number) => string;
  /** Seconds; capped by the motion rules at 0.4. */
  duration?: number;
  className?: string;
}

/** Number that counts from its last value to `value` (400 ms). Honours prefers-reduced-motion (shows the value at once). */
export function CountUp({ value, format = (n) => Math.round(n).toLocaleString(), duration = 0.4, className }: CountUpProps) {
  const reduced = useReducedMotion() ?? false;
  const shownRef = useRef(0);
  const [animated, setAnimated] = useState(0);

  useEffect(() => {
    if (reduced || !Number.isFinite(value)) return;
    const controls = animate(shownRef.current, value, {
      duration: Math.min(0.4, duration),
      ease: EASE_OUT,
      onUpdate: (v) => {
        shownRef.current = v;
        setAnimated(v);
      },
    });
    return () => controls.stop();
  }, [value, reduced, duration]);

  const shown = reduced ? value : animated;
  return <span className={cn("tabular-nums", className)}>{Number.isFinite(value) ? format(shown) : "–"}</span>;
}

/** Shimmering placeholder block (CSS-driven, so it costs nothing while hidden). */
export function Shimmer({ className, children }: { className?: string; children?: ReactNode }) {
  return (
    <div className={cn("skeleton-shimmer rounded-md", className)} aria-hidden>
      {children}
    </div>
  );
}
