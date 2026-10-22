// Memory API (docs/CONTRACT.md → "Memory") + React Query hooks with optimistic updates.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/lib/api";
import type { MemoryItem, MemoryState } from "@/lib/feature-types";

export const memoryKeys = { all: ["memory"] as const };

export const memoryApi = {
  list: () => request<MemoryState>("/memory"),
  add: (content: string) => request<MemoryItem>("/memory", { method: "POST", body: { content } }),
  remove: (id: string) => request<void>(`/memory/${encodeURIComponent(id)}`, { method: "DELETE" }),
  clear: () => request<void>("/memory", { method: "DELETE" }),
  setEnabled: (enabled: boolean) => request<{ enabled: boolean }>("/memory/settings", { method: "PUT", body: { enabled } }),
};

export function useMemory() {
  return useQuery({ queryKey: memoryKeys.all, queryFn: memoryApi.list });
}

/** Optimistically patch the cached state; roll back on error, refetch when settled. */
function useOptimistic<V, R>(mutationFn: (v: V) => Promise<R>, patch: (s: MemoryState, v: V) => MemoryState) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    onMutate: async (v: V) => {
      await qc.cancelQueries({ queryKey: memoryKeys.all });
      const snapshot = qc.getQueryData<MemoryState>(memoryKeys.all);
      if (snapshot) qc.setQueryData<MemoryState>(memoryKeys.all, patch(snapshot, v));
      return { snapshot };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.snapshot) qc.setQueryData(memoryKeys.all, ctx.snapshot);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: memoryKeys.all }),
  });
}

export function useAddMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: memoryApi.add,
    onSuccess: (item) =>
      qc.setQueryData<MemoryState>(memoryKeys.all, (old) =>
        old ? { ...old, items: [item, ...old.items.filter((m) => m.id !== item.id)] } : old,
      ),
    onSettled: () => qc.invalidateQueries({ queryKey: memoryKeys.all }),
  });
}

export function useDeleteMemory() {
  return useOptimistic(memoryApi.remove, (s, id: string) => ({ ...s, items: s.items.filter((m) => m.id !== id) }));
}

export function useForgetEverything() {
  return useOptimistic(() => memoryApi.clear(), (s) => ({ ...s, items: [] }));
}

export function useSetMemoryEnabled() {
  return useOptimistic(memoryApi.setEnabled, (s, enabled: boolean) => ({ ...s, enabled }));
}
