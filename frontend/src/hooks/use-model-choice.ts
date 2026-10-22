import { useMemo } from "react";
import type { ComposerModel } from "@/components/ui/ai-mascot-input";
import { PROVIDER_LABEL } from "@/lib/format";
import { useModels } from "@/lib/queries";
import type { ModelInfo } from "@/lib/types";
import { usePrefs } from "@/stores/prefs";

export const toComposerModel = (m: ModelInfo): ComposerModel => ({
  id: m.id,
  name: m.label,
  provider: PROVIDER_LABEL[m.provider] ?? m.provider,
  providerId: m.provider,
  description: m.description,
  available: m.available,
  reason: m.reason ?? null,
  supportsTools: m.supportsTools,
  supportsVision: m.supportsVision,
  isDefault: m.isDefault,
});

/**
 * Model for a spoken turn: the ensemble merges three answers (seconds of extra latency), so a voice question goes to
 * the fastest single model instead, preferring an available Groq model.
 */
export function voiceModelId(models: ModelInfo[], selectedId: string | null | undefined): string {
  if (!selectedId || !selectedId.startsWith("ensemble:")) return selectedId ?? "";
  const singles = models.filter((m) => m.available && m.provider !== "ensemble");
  return (singles.find((m) => m.provider === "groq") ?? singles[0])?.id ?? selectedId;
}

/** The offline "mock" provider is a test double: never offer it to people, even if a server lists it. */
const isRealModel = (m: ModelInfo) => m.provider !== "mock";

/** Models for the composer + the effective selection (stored pick → server default → first available). */
export function useModelChoice() {
  const query = useModels();
  const storedId = usePrefs((s) => s.modelId);
  const setModelId = usePrefs((s) => s.setModelId);
  const models = useMemo(() => (query.data ?? []).filter(isRealModel), [query.data]);

  const selected = useMemo<ModelInfo | null>(() => {
    const available = models.filter((m) => m.available);
    return (
      available.find((m) => m.id === storedId) ??
      available.find((m) => m.isDefault) ??
      available[0] ??
      null
    );
  }, [models, storedId]);

  const composerModels = useMemo(() => models.map(toComposerModel), [models]);
  const noneAvailable = query.isSuccess && !models.some((m) => m.available);

  const labelFor = (id?: string | null): string | null => {
    if (!id) return null;
    const hit = models.find((m) => m.id === id);
    if (hit) return hit.label;
    const i = id.indexOf(":");
    return i === -1 ? id : id.slice(i + 1);
  };

  const forVoice = voiceModelId(models, selected?.id);

  return { query, models, composerModels, selected, setModelId, noneAvailable, labelFor, forVoice };
}
