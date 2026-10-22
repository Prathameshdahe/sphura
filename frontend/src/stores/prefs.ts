import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Effort } from "@/lib/types";

/** Per-viewer composer + layout preferences (localStorage; safe to lose). */
interface Prefs {
  modelId: string | null;
  effort: Effort;
  /** Forces the market / finance-news branch of the agent. */
  webSearch: boolean;
  sidebarCollapsed: boolean;
  /** Underline answer sentences by verification verdict. */
  highlightClaims: boolean;
  /** Read every finished answer aloud (voice questions are always answered out loud). */
  autoSpeak: boolean;
  setModelId: (id: string) => void;
  setEffort: (e: Effort) => void;
  setWebSearch: (on: boolean) => void;
  setSidebarCollapsed: (v: boolean) => void;
  setHighlightClaims: (on: boolean) => void;
  setAutoSpeak: (on: boolean) => void;
}

export const safeStorage = createJSONStorage(() => {
  try {
    const k = "__sphura_probe__";
    window.localStorage.setItem(k, k);
    window.localStorage.removeItem(k);
    return window.localStorage;
  } catch {
    const mem = new Map<string, string>();
    return {
      getItem: (k: string) => mem.get(k) ?? null,
      setItem: (k: string, v: string) => void mem.set(k, v),
      removeItem: (k: string) => void mem.delete(k),
    };
  }
});

export const usePrefs = create<Prefs>()(
  persist(
    (set) => ({
      modelId: null,
      effort: "balanced",
      webSearch: false,
      sidebarCollapsed: false,
      highlightClaims: false,
      autoSpeak: false,
      setModelId: (modelId) => set({ modelId }),
      setEffort: (effort) => set({ effort }),
      setWebSearch: (webSearch) => set({ webSearch }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setHighlightClaims: (highlightClaims) => set({ highlightClaims }),
      setAutoSpeak: (autoSpeak) => set({ autoSpeak }),
    }),
    {
      name: "sphura.prefs",
      storage: safeStorage,
      version: 2,
      // v1 stored the Chat / Research / Finance mode switch; the finance agent routes on its own now.
      migrate: (state) => {
        const s = (state ?? {}) as Record<string, unknown>;
        const { mode: _mode, ...rest } = s;
        void _mode;
        return rest as unknown as Prefs;
      },
    },
  ),
);
