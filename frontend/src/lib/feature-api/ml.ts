// Model Lab API (FINANCE_PLAN §8: /api/ml/report, /api/ml/train/{key}, /api/ml/verification) + React Query hooks.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/lib/api";
import type { ModelCard, ModelKey, ModelLabReport, VerificationStats } from "@/lib/feature-types";

export const mlKeys = {
  all: ["ml"] as const,
  report: ["ml", "report"] as const,
  verification: ["ml", "verification"] as const,
};

export const mlApi = {
  report: () => request<ModelLabReport>("/ml/report"),
  train: (key: ModelKey) => request<ModelCard>(`/ml/train/${key}`, { method: "POST" }),
  verification: () => request<VerificationStats>("/ml/verification"),
};

export function useModelLabReport() {
  return useQuery({ queryKey: mlKeys.report, queryFn: mlApi.report, staleTime: 5 * 60_000 });
}

export function useVerificationStats() {
  return useQuery({ queryKey: mlKeys.verification, queryFn: mlApi.verification });
}

/** Admin: retrain one classifier; the fresh card replaces the one in the cached report. */
export function useTrainModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (key: ModelKey) => mlApi.train(key),
    meta: { silent: true }, // the page shows a progress toast and resolves it itself
    onSuccess: (card) =>
      qc.setQueryData<ModelLabReport>(mlKeys.report, (old) =>
        old ? { ...old, models: old.models.map((m) => (m.key === card.key ? card : m)) } : old,
      ),
  });
}
