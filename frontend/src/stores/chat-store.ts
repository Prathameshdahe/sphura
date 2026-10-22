import { create } from "zustand";
import type { Verification } from "@/lib/feature-types";
import type { AttachmentRef, Phase, Source, ToolStep } from "@/lib/types";

/** One in-flight /api/chat stream. Keyed by conversation id (or a temporary "new:*" key before `start`). */
export interface ChatStream {
  key: string;
  conversationId: string | null;
  assistantMessageId: string | null;
  /** `start` received: the user message is saved and lives in the conversation cache. */
  started: boolean;
  /** Shown until `start` arrives (null for regenerate / edit, which patch the cache directly). */
  optimisticUser: { content: string; attachments: AttachmentRef[] } | null;
  model: string | null;
  text: string;
  phase: Phase | null;
  label: string | null;
  steps: ToolStep[];
  sources: Source[];
  /** Claim check from the `verification` event (arrives after the last delta, before `done`). */
  verification?: Verification | null;
  startedAt: number;
  controller: AbortController;
}

interface ChatStore {
  streams: Record<string, ChatStream>;
  /** Assistant message that just finished in this session (its logo plays the "answer" burst once). */
  lastCompletedId: string | null;
  begin: (stream: ChatStream) => void;
  update: (key: string, fn: (s: ChatStream) => Partial<ChatStream>) => void;
  rekey: (from: string, to: string) => void;
  end: (key: string, completedId?: string | null) => void;
}

export const useChatStore = create<ChatStore>()((set) => ({
  streams: {},
  lastCompletedId: null,
  begin: (stream) => set((s) => ({ streams: { ...s.streams, [stream.key]: stream } })),
  update: (key, fn) =>
    set((s) => {
      const cur = s.streams[key];
      if (!cur) return s;
      return { streams: { ...s.streams, [key]: { ...cur, ...fn(cur) } } };
    }),
  rekey: (from, to) =>
    set((s) => {
      const cur = s.streams[from];
      if (!cur || from === to) return s;
      const { [from]: _moved, ...rest } = s.streams;
      void _moved;
      return { streams: { ...rest, [to]: { ...cur, key: to } } };
    }),
  end: (key, completedId) =>
    set((s) => {
      const { [key]: _gone, ...rest } = s.streams;
      void _gone;
      return { streams: rest, lastCompletedId: completedId ?? s.lastCompletedId };
    }),
}));

export function stopStream(key: string | null | undefined): void {
  if (!key) return;
  useChatStore.getState().streams[key]?.controller.abort();
}

export function abortAllStreams(): void {
  for (const s of Object.values(useChatStore.getState().streams)) s.controller.abort();
}
