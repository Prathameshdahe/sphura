import { useChatStore } from "@/stores/chat-store";
import { errorMessage, isAbortError } from "./api";
import { uid } from "./format";
import { queryClient } from "./query-client";
import { qk } from "./queries";
import { streamChat } from "./sse";
import { parseVerification } from "./verification";
import type { Verification } from "./feature-types";
import type {
  AttachmentRef,
  ChatRequest,
  ConversationDetail,
  ConversationSummary,
  Message,
  Source,
  ToolStep,
} from "./types";

/**
 * Runs one /api/chat stream outside React so it survives navigation ("/" → "/c/:id" on `start`).
 * Live state goes to the chat store; saved messages go straight into the React Query cache.
 */
export interface SendChatOptions {
  /** Store key; defaults to the conversation id or a fresh "new:*" key. */
  key?: string;
  request: ChatRequest;
  optimisticUser?: { content: string; attachments: AttachmentRef[] } | null;
  onStart?: (conversationId: string) => void;
  /** Aborting it stops the stream (same as the Stop button). */
  signal?: AbortSignal;
}

export interface SendChatResult {
  status: "done" | "error" | "stopped";
  /** False when nothing reached the server's conversation (failed/stopped before `start`). */
  started: boolean;
  conversationId: string | null;
  text: string;
  message: Message | null;
  error: string | null;
}

const FLUSH_MS = 32;

function setDetail(id: string, fn: (d: ConversationDetail) => ConversationDetail) {
  queryClient.setQueryData<ConversationDetail>(qk.conversation(id), (old) => (old ? fn(old) : old));
}

/**
 * Cancel an in-flight refetch of a cached conversation (rename/pin, revisit) so its older server
 * snapshot can't overwrite what we write next. False when uncached: cancelling a first load would strand it.
 */
async function settleDetail(id: string): Promise<boolean> {
  const key = qk.conversation(id);
  if (!queryClient.getQueryData(key)) return false;
  await queryClient.cancelQueries({ queryKey: key, exact: true });
  return true;
}

function provisionalTitle(content: string): string {
  const line = content.trim().split("\n")[0] ?? "";
  return line.length > 48 ? `${line.slice(0, 47).trimEnd()}…` : line || "New chat";
}

/** Edit → keep messages before the edited one (with new content); regenerate → drop the trailing answer. */
function truncateForRetry(d: ConversationDetail, req: ChatRequest): ConversationDetail {
  if (req.editMessageId) {
    const i = d.messages.findIndex((m) => m.id === req.editMessageId);
    if (i === -1) return d;
    return { ...d, messages: [...d.messages.slice(0, i), { ...d.messages[i], content: req.content }] };
  }
  let last = d.messages.length - 1;
  while (last >= 0 && d.messages[last].role !== "user") last--;
  return last === -1 ? d : { ...d, messages: d.messages.slice(0, last + 1) };
}

/** Insert or replace the saved user message; anything after it is gone server-side too. */
function upsertUserMessage(d: ConversationDetail, msg: Message): ConversationDetail {
  const i = d.messages.findIndex((m) => m.id === msg.id);
  return { ...d, messages: i === -1 ? [...d.messages, msg] : [...d.messages.slice(0, i), msg] };
}

function applyStart(req: ChatRequest, conversationId: string, userMessage: Message) {
  const key = qk.conversation(conversationId);
  if (queryClient.getQueryData<ConversationDetail>(key)) {
    setDetail(conversationId, (d) => upsertUserMessage(d, userMessage));
    return;
  }
  if (req.conversationId) {
    void queryClient.invalidateQueries({ queryKey: key, exact: true });
    return;
  }
  const summary: ConversationSummary = {
    id: conversationId,
    title: provisionalTitle(userMessage.content || req.content),
    mode: req.mode,
    pinned: false,
    createdAt: userMessage.createdAt,
    updatedAt: userMessage.createdAt,
  };
  queryClient.setQueryData<ConversationDetail>(key, { conversation: summary, messages: [userMessage] });
  queryClient.setQueryData<ConversationSummary[]>(qk.conversations(""), (old) => {
    if (!old || old.some((c) => c.id === conversationId)) return old;
    const firstUnpinned = old.findIndex((c) => !c.pinned);
    const at = firstUnpinned === -1 ? old.length : firstUnpinned;
    return [...old.slice(0, at), summary, ...old.slice(at)];
  });
}

function applyTitle(conversationId: string, title: string) {
  setDetail(conversationId, (d) => ({ ...d, conversation: { ...d.conversation, title } }));
  queryClient.setQueriesData<ConversationSummary[]>({ queryKey: qk.conversationsAll }, (old) =>
    old?.map((c) => (c.id === conversationId ? { ...c, title } : c)),
  );
}

function upsertStep(steps: ToolStep[], step: ToolStep): ToolStep[] {
  const i = steps.findIndex((s) => s.id === step.id);
  if (i === -1) return [...steps, step];
  const next = steps.slice();
  next[i] = { ...steps[i], ...step };
  return next;
}

export async function sendChat(opts: SendChatOptions): Promise<SendChatResult> {
  const { request } = opts;
  const store = useChatStore.getState;
  let key = opts.key ?? request.conversationId ?? `new:${uid()}`;
  let conversationId = request.conversationId ?? null;

  const busy = (): SendChatResult => ({
    status: "error",
    started: false,
    conversationId,
    text: "",
    message: null,
    error: "Sphura is still answering — stop it first.",
  });
  if (store().streams[key]) return busy();

  // Regenerate / edit hide what the server is about to replace (restored if nothing starts).
  // Settle first so the trim and the live draft appear in the same frame.
  const retryId = request.regenerate || request.editMessageId ? conversationId : null;
  const cached = retryId ? await settleDetail(retryId) : false;
  if (store().streams[key]) return busy();

  const controller = new AbortController();
  const abort = () => controller.abort();
  if (opts.signal?.aborted) abort();
  else opts.signal?.addEventListener("abort", abort, { once: true });

  store().begin({
    key,
    conversationId,
    assistantMessageId: null,
    started: false,
    optimisticUser: opts.optimisticUser ?? null,
    model: request.model ?? null,
    text: "",
    phase: "thinking",
    label: null,
    steps: [],
    sources: [],
    verification: null,
    startedAt: Date.now(),
    controller,
  });

  const snapshot = retryId && cached ? queryClient.getQueryData<ConversationDetail>(qk.conversation(retryId)) : undefined;
  if (snapshot && retryId) setDetail(retryId, (d) => truncateForRetry(d, request));

  let text = "";
  let pending = "";
  let timer: ReturnType<typeof setTimeout> | null = null;
  let started = false;
  let assistantId: string | null = null;
  let model = request.model ?? null;
  let steps: ToolStep[] = [];
  let sources: Source[] = [];
  let verification: Verification | null = null;
  let final: Message | null = null;
  let errorText: string | null = null;
  let stopped = false;

  const flush = () => {
    timer = null;
    if (!pending) return;
    const chunk = pending;
    pending = "";
    store().update(key, (s) => ({ text: s.text + chunk }));
  };

  try {
    for await (const ev of streamChat(request, controller.signal)) {
      if (ev.event === "start") {
        const d = ev.data;
        await settleDetail(d.conversationId);
        // From here on, cache + live state change in one tick (no frame shows the user message twice).
        started = true;
        conversationId = d.conversationId;
        assistantId = d.assistantMessageId;
        model = d.model || model;
        applyStart(request, d.conversationId, d.userMessage);
        if (key !== d.conversationId) {
          store().rekey(key, d.conversationId);
          key = d.conversationId;
        }
        store().update(key, () => ({
          started: true,
          conversationId: d.conversationId,
          assistantMessageId: d.assistantMessageId,
          model,
          optimisticUser: null,
        }));
        opts.onStart?.(d.conversationId);
      } else if (ev.event === "status") {
        store().update(key, () => ({ phase: ev.data.phase, label: ev.data.label }));
      } else if (ev.event === "step") {
        steps = upsertStep(steps, ev.data);
        store().update(key, () => ({ steps }));
      } else if (ev.event === "sources") {
        sources = ev.data.sources ?? [];
        store().update(key, () => ({ sources }));
      } else if (ev.event === "delta") {
        text += ev.data.text;
        pending += ev.data.text;
        timer ??= setTimeout(flush, FLUSH_MS);
      } else if (ev.event === "title") {
        applyTitle(ev.data.conversationId, ev.data.title);
      } else if (ev.event === "verification") {
        const parsed = parseVerification(ev.data?.verification);
        if (parsed) {
          verification = parsed;
          store().update(key, () => ({ verification: parsed }));
        }
      } else if (ev.event === "done") {
        final = ev.data.message;
        break;
      } else if (ev.event === "error") {
        errorText = ev.data.message || "Something went wrong while answering.";
        break;
      }
    }
  } catch (e) {
    if (controller.signal.aborted || isAbortError(e)) stopped = true;
    else errorText = errorMessage(e);
  } finally {
    if (timer) clearTimeout(timer);
    flush();
    opts.signal?.removeEventListener("abort", abort);
  }

  if (!final && !errorText && !stopped) errorText = "The response ended unexpectedly. Please try again.";
  // The saved message normally carries meta.verification already; keep the streamed one if it doesn't.
  if (final && verification && !final.meta?.verification) {
    final = { ...final, meta: { ...(final.meta ?? {}), verification } };
  }

  let message: Message | null = final;
  if (started && conversationId) {
    if (!message) {
      const now = new Date().toISOString();
      message = {
        id: assistantId ?? uid(),
        conversationId,
        role: "assistant",
        content: text,
        createdAt: now,
        model,
        status: stopped ? "stopped" : "error",
        error: stopped ? null : errorText,
        sources,
        steps: steps.map((s) =>
          s.status === "running" ? { ...s, status: "error", detail: s.detail ?? "Stopped", finishedAt: now } : s,
        ),
        attachments: [],
        meta: verification ? { verification } : null,
      };
    }
    const saved = message;
    // Write the answer and drop the live draft in the same tick, so the thread never flickers.
    if (await settleDetail(conversationId)) {
      setDetail(conversationId, (d) => ({ ...d, messages: [...d.messages.filter((m) => m.id !== saved.id), saved] }));
    } else {
      void queryClient.invalidateQueries({ queryKey: qk.conversation(conversationId), exact: true });
    }
  } else if (snapshot && conversationId) {
    queryClient.setQueryData(qk.conversation(conversationId), snapshot);
    // Stopped before `start`: the server may already have trimmed the thread.
    if (stopped) void queryClient.invalidateQueries({ queryKey: qk.conversation(conversationId), exact: true });
  }

  store().end(key, final ? final.id : null);
  if (started || !request.conversationId) void queryClient.invalidateQueries({ queryKey: qk.conversationsAll });

  return {
    status: final ? "done" : stopped ? "stopped" : "error",
    started,
    conversationId,
    text: final ? final.content : text,
    message,
    error: final || stopped ? null : errorText,
  };
}
