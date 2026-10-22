import { create } from "zustand";
import type { Artifact } from "@/components/artifacts/artifact-utils";

export type ArtifactTab = "preview" | "code";

/** The artifact side panel (desktop) / bottom sheet (mobile) of the chat page. */
interface ArtifactPanelStore {
  open: boolean;
  active: Artifact | null;
  tab: ArtifactTab;
  /** Assistant messages whose artifact already auto-opened this session (once per message). */
  autoOpened: Record<string, true>;
  show: (artifact: Artifact, tab?: ArtifactTab) => void;
  setTab: (tab: ArtifactTab) => void;
  close: () => void;
  /** Close and forget the artifact (navigating to another chat). */
  reset: () => void;
  /** True the first time it's called for a message id. */
  claimAutoOpen: (messageId: string) => boolean;
}

export const useArtifactPanel = create<ArtifactPanelStore>()((set, get) => ({
  open: false,
  active: null,
  tab: "preview",
  autoOpened: {},
  show: (active, tab = "preview") => set({ open: true, active, tab }),
  setTab: (tab) => set({ tab }),
  close: () => set({ open: false }),
  reset: () => set({ open: false, active: null, tab: "preview" }),
  claimAutoOpen: (messageId) => {
    if (get().autoOpened[messageId]) return false;
    set((s) => ({ autoOpened: { ...s.autoOpened, [messageId]: true } }));
    return true;
  },
}));
