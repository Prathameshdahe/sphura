import { create } from "zustand";

/** Transient shell UI state shared by the sidebar, top bars and keyboard shortcuts. */
interface UiStore {
  mobileSidebarOpen: boolean;
  /** Bumped to ask the sidebar search box to focus itself (Ctrl+K). */
  searchFocusTick: number;
  /** Set by requestSearchFocus; cleared by whichever sidebar instance focuses its search box. */
  searchFocusPending: boolean;
  /** Last chat route ("/" or "/c/:id"), so the Chat space tab returns to the open conversation. */
  lastChatPath: string;
  /** The next finished answer should be read aloud (the question was asked by voice). */
  speakNext: boolean;
  setSpeakNext: (on: boolean) => void;
  setMobileSidebarOpen: (open: boolean) => void;
  setLastChatPath: (path: string) => void;
  requestSearchFocus: () => void;
  consumeSearchFocus: () => boolean;
}

export const useUi = create<UiStore>()((set, get) => ({
  mobileSidebarOpen: false,
  searchFocusTick: 0,
  searchFocusPending: false,
  lastChatPath: "/",
  speakNext: false,
  setSpeakNext: (speakNext) => set({ speakNext }),
  setMobileSidebarOpen: (mobileSidebarOpen) => set({ mobileSidebarOpen }),
  setLastChatPath: (lastChatPath) => set({ lastChatPath }),
  requestSearchFocus: () => set((s) => ({ searchFocusTick: s.searchFocusTick + 1, searchFocusPending: true })),
  consumeSearchFocus: () => {
    if (!get().searchFocusPending) return false;
    set({ searchFocusPending: false });
    return true;
  },
}));
