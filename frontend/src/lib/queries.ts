import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, request } from "./api";
import type { Verification } from "./feature-types";
import type { ConversationDetail, ConversationSummary, DocumentInfo, User } from "./types";
import { pendingIds, pollWhilePending } from "./poll";
import { parseVerification } from "./verification";

export const qk = {
  me: ["me"] as const,
  models: ["models"] as const,
  conversationsAll: ["conversations"] as const,
  conversations: (q = "") => ["conversations", q.trim()] as const,
  conversation: (id: string) => ["conversation", id] as const,
  documentsAll: ["documents"] as const,
  documents: (conversationId?: string | null) => ["documents", conversationId ?? "all"] as const,
};

const isPendingDoc = (d: DocumentInfo) => d.status === "queued" || d.status === "processing";

export function useMe() {
  return useQuery<User, Error>({
    queryKey: qk.me,
    queryFn: api.me,
    staleTime: 5 * 60_000,
    meta: { silent: true },
    retry: (count, error) => !(error instanceof ApiError && error.status > 0 && error.status < 500) && count < 2,
    // A failed "who am I" must not be re-fetched just because another component (e.g. the landing page shown for a
    // 401) mounts an observer: a refetch without data flips the query back to pending, which would unmount that
    // component and loop. Retries happen explicitly (ServerDown's button) or after the cache is cleared.
    retryOnMount: false,
  });
}

export function useModels() {
  return useQuery({
    queryKey: qk.models,
    queryFn: api.models,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useConversations(q = "") {
  return useQuery({
    queryKey: qk.conversations(q),
    queryFn: () => api.conversations(q),
    placeholderData: keepPreviousData,
  });
}

export function useConversation(id?: string) {
  return useQuery({
    queryKey: qk.conversation(id ?? ""),
    queryFn: () => api.conversation(id as string),
    enabled: !!id,
  });
}

export function useDocuments(conversationId?: string | null) {
  return useQuery({
    queryKey: qk.documents(conversationId),
    queryFn: () => api.documents(conversationId),
    refetchInterval: pollWhilePending((docs: DocumentInfo[]) => pendingIds(docs, isPendingDoc, (d) => d.id), 1500),
  });
}

/** Apply a change to every cached conversation list (all search variants). */
function patchLists(
  qc: ReturnType<typeof useQueryClient>,
  fn: (list: ConversationSummary[]) => ConversationSummary[],
) {
  qc.setQueriesData<ConversationSummary[]>({ queryKey: qk.conversationsAll }, (old) => (old ? fn(old) : old));
}

const sortSummaries = (list: ConversationSummary[]) =>
  [...list].sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt.localeCompare(a.updatedAt));

export function useUpdateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: { title?: string; pinned?: boolean } }) =>
      api.updateConversation(id, patch),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: qk.conversationsAll });
      const snapshot = qc.getQueriesData<ConversationSummary[]>({ queryKey: qk.conversationsAll });
      patchLists(qc, (list) => sortSummaries(list.map((c) => (c.id === id ? { ...c, ...patch } : c))));
      qc.setQueryData<ConversationDetail>(qk.conversation(id), (old) =>
        old ? { ...old, conversation: { ...old.conversation, ...patch } } : old,
      );
      return { snapshot };
    },
    onError: (_e, _v, ctx) => ctx?.snapshot.forEach(([key, data]) => qc.setQueryData(key, data)),
    onSettled: (_d, _e, { id }) => {
      void qc.invalidateQueries({ queryKey: qk.conversationsAll });
      void qc.invalidateQueries({ queryKey: qk.conversation(id) });
    },
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteConversation(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: qk.conversationsAll });
      const snapshot = qc.getQueriesData<ConversationSummary[]>({ queryKey: qk.conversationsAll });
      patchLists(qc, (list) => list.filter((c) => c.id !== id));
      return { snapshot };
    },
    onError: (_e, _v, ctx) => ctx?.snapshot.forEach(([key, data]) => qc.setQueryData(key, data)),
    onSuccess: (_d, id) => qc.removeQueries({ queryKey: qk.conversation(id) }),
    onSettled: () => qc.invalidateQueries({ queryKey: qk.conversationsAll }),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteDocument(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: qk.documentsAll });
      const snapshot = qc.getQueriesData<DocumentInfo[]>({ queryKey: qk.documentsAll });
      qc.setQueriesData<DocumentInfo[]>({ queryKey: qk.documentsAll }, (old) => old?.filter((d) => d.id !== id));
      return { snapshot };
    },
    onError: (_e, _v, ctx) => ctx?.snapshot.forEach(([key, data]) => qc.setQueryData(key, data)),
    onSettled: () => qc.invalidateQueries({ queryKey: qk.documentsAll }),
  });
}

/* ── wave 2: feedback ── */

export interface FeedbackBody {
  messageId: string;
  value: 1 | -1;
  comment?: string;
}

/** POST /api/feedback (one vote per user + message; the last one wins). */
export function useSendFeedback() {
  return useMutation({
    mutationFn: (body: FeedbackBody) => request<{ ok: boolean }>("/feedback", { method: "POST", body }),
    meta: { silent: true },
  });
}

/* ── wave 2: answer verification ── */

/**
 * POST /api/verify/{messageId}: (re)check a saved answer's claims and keep the result on the cached message.
 * Lets an answer that finished before the verification model was ready still get its meter.
 */
export function useVerifyMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId }: { messageId: string; conversationId: string }) =>
      request<Verification>(`/verify/${encodeURIComponent(messageId)}`, { method: "POST" }),
    meta: { silent: true },
    onSuccess: (raw, { messageId, conversationId }) => {
      const verification = parseVerification(raw);
      if (!verification) return;
      qc.setQueryData<ConversationDetail>(qk.conversation(conversationId), (old) =>
        old
          ? {
              ...old,
              messages: old.messages.map((m) => (m.id === messageId ? { ...m, meta: { ...(m.meta ?? {}), verification } } : m)),
            }
          : old,
      );
    },
  });
}
