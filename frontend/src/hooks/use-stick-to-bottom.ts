import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

const THRESHOLD = 96;

/**
 * Keeps a scroll container pinned to the bottom while its content grows (streaming),
 * until the user scrolls up. Exposes `isAtBottom` for a "jump to latest" button.
 */
export function useStickToBottom<S extends HTMLElement, C extends HTMLElement>(enabled = true) {
  const scrollRef = useRef<S | null>(null);
  const contentRef = useRef<C | null>(null);
  const stuck = useRef(true);
  const enabledRef = useRef(enabled);
  const [isAtBottom, setIsAtBottom] = useState(true);

  useLayoutEffect(() => {
    enabledRef.current = enabled;
    const el = scrollRef.current;
    if (!el) return;
    if (enabled) {
      stuck.current = true;
      el.scrollTop = el.scrollHeight;
    } else {
      el.scrollTop = 0;
    }
  }, [enabled]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const el = scrollRef.current;
    if (!el || !enabledRef.current) return;
    stuck.current = true;
    setIsAtBottom(true);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? "auto" : behavior });
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    const content = contentRef.current;
    if (!el || !content) return;

    // Only upward movement un-sticks: a programmatic jump's scroll event lands a frame later, when the
    // content may already have grown, so "not at the bottom" alone doesn't mean the user scrolled away.
    let lastTop = el.scrollTop;
    const onScroll = () => {
      const top = el.scrollTop;
      const movedUp = top < lastTop - 1;
      lastTop = top;
      if (!enabledRef.current) return;
      const atBottom = el.scrollHeight - top - el.clientHeight < THRESHOLD;
      if (atBottom) stuck.current = true;
      else if (movedUp) stuck.current = false;
      setIsAtBottom(atBottom || stuck.current);
    };
    // Any upward intent un-sticks immediately, even while content is still growing
    // (but not on a view that can't scroll up yet, or a short answer would stop following).
    const onWheel = (e: WheelEvent) => {
      if (e.deltaY < 0 && el.scrollTop > 0) stuck.current = false;
    };
    let touchY = 0;
    const onTouchStart = (e: TouchEvent) => {
      touchY = e.touches[0]?.clientY ?? 0;
    };
    const onTouchMove = (e: TouchEvent) => {
      if ((e.touches[0]?.clientY ?? 0) > touchY + 4 && el.scrollTop > 0) stuck.current = false;
    };

    // Content growth (streaming) and viewport shrink (composer grows) both keep a stuck view pinned.
    const ro = new ResizeObserver(() => {
      if (!enabledRef.current) return;
      if (stuck.current) el.scrollTop = el.scrollHeight;
      else onScroll();
    });
    ro.observe(content);
    ro.observe(el);
    el.addEventListener("scroll", onScroll, { passive: true });
    el.addEventListener("wheel", onWheel, { passive: true });
    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: true });
    return () => {
      ro.disconnect();
      el.removeEventListener("scroll", onScroll);
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
    };
  }, []);

  return { scrollRef, contentRef, isAtBottom, scrollToBottom };
}
