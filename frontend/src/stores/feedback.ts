import { create } from "zustand";
import { persist } from "zustand/middleware";
import { safeStorage } from "@/stores/prefs";

export type Vote = 1 | -1;

/** This viewer's thumbs on assistant messages (the API has no read endpoint, so we remember locally). */
interface FeedbackStore {
  votes: Record<string, Vote>;
  setVote: (messageId: string, vote: Vote | null) => void;
}

const MAX_KEPT = 500;

export const useFeedbackStore = create<FeedbackStore>()(
  persist(
    (set) => ({
      votes: {},
      setVote: (messageId, vote) =>
        set((s) => {
          const { [messageId]: _old, ...rest } = s.votes;
          void _old;
          if (vote === null) return { votes: rest };
          const keys = Object.keys(rest);
          // Keep the map small: drop the oldest entries (insertion order).
          for (const k of keys.slice(0, Math.max(0, keys.length - MAX_KEPT + 1))) delete rest[k];
          return { votes: { ...rest, [messageId]: vote } };
        }),
    }),
    { name: "sphura.feedback", storage: safeStorage, version: 1 },
  ),
);
