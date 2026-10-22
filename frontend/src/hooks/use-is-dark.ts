import { useSyncExternalStore } from "react";

function subscribe(cb: () => void) {
  const obs = new MutationObserver(cb);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => obs.disconnect();
}

const isDark = () => document.documentElement.classList.contains("dark");

/** True while the app renders in dark mode (follows the `.dark` class next-themes puts on <html>). */
export function useIsDark(): boolean {
  return useSyncExternalStore(subscribe, isDark, () => false);
}
