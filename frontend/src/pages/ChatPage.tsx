import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, MessageSquareDashed } from "lucide-react";
import { toast } from "sonner";
import { ArtifactPanel } from "@/components/artifacts/artifact-panel";
import { extractArtifacts, type Artifact } from "@/components/artifacts/artifact-utils";
import { ChatComposer } from "@/components/chat/composer";
import { Thread, ThreadSkeleton } from "@/components/chat/thread";
import { HoverGrid } from "@/components/ui/hover-grid";
import { Welcome } from "@/components/chat/welcome";
import { Button } from "@/components/ui/button";
import type { ComposerSubmit } from "@/components/ui/ai-mascot-input";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { focusSheetItself } from "@/lib/focus";
import { EASE_OUT, SPRING_SOFT } from "@/lib/motion";
import { VoiceMode } from "@/components/voice/voice-mode";
import { attachmentFromDoc, isSendable, toAttachmentRef, useAttachments } from "@/hooks/use-attachments";
import { useIsDesktop, useMediaQuery } from "@/hooks/use-media-query";
import { useModelChoice } from "@/hooks/use-model-choice";
import { useStickToBottom } from "@/hooks/use-stick-to-bottom";
import { ApiError } from "@/lib/api";
import { sendChat, type SendChatResult } from "@/lib/chat-runner";
import { isTabularDoc } from "@/lib/feature-api/finance";
import type { NewChatState } from "@/lib/feature-types";
import { stripEmoji } from "@/lib/emoji";
import { uid } from "@/lib/format";
import { useConversation, useDocuments, useMe } from "@/lib/queries";
import type { Starter } from "@/lib/starters";
import type { DocumentInfo, Message } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useArtifactPanel } from "@/stores/artifacts";
import { stopStream, useChatStore } from "@/stores/chat-store";
import { usePrefs } from "@/stores/prefs";
import { useSpeech, type LiveSpeech } from "@/stores/speech";
import { useUi } from "@/stores/ui";

/** Router state: the NewChatState hand-off from any page, or our own "/" → "/c/:id" hop. */
type NavState = (Partial<NewChatState> & { fromStart?: boolean }) | null;

const unique = (ids: string[]) => [...new Set(ids)];
const docIdsOf = (messages: Message[]) => unique(messages.flatMap((m) => m.attachments.map((a) => a.docId)));

function handoffDocs(state: NavState): DocumentInfo[] {
  const docs = [...(state?.attachDocs ?? []), ...(state?.attachDoc ? [state.attachDoc] : [])];
  return docs.filter((d, i) => d?.id && docs.findIndex((x) => x.id === d.id) === i);
}

function isInOverlay(): boolean {
  return !!document.querySelector("[role=dialog], [role=alertdialog], [role=menu], [data-radix-popper-content-wrapper]");
}

function reportFailure(res: SendChatResult) {
  if (!res.started && res.status === "error" && res.error) toast.error(res.error);
}

/** "/" (new chat) and "/c/:conversationId" share this page so a stream survives the start-navigation. */
export default function ChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const me = useMe();
  const detail = useConversation(conversationId);
  const choice = useModelChoice();
  const isDesktop = useIsDesktop();
  // Side-by-side artifact panel only where chat (340 px) + panel (320 px) fit next to the open sidebar.
  const isSplit = useMediaQuery("(min-width: 1024px)");
  const effort = usePrefs((s) => s.effort);
  const webSearch = usePrefs((s) => s.webSearch);

  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const navState = location.state as NavState;
  const [draft, setDraft] = useState(() => (navState?.fromStart ? "" : (navState?.prompt ?? "")));
  const [voiceOpen, setVoiceOpen] = useState(false);
  const attachments = useAttachments(conversationId);
  const activeKey = conversationId ?? pendingKey;
  const stream = useChatStore((s) => (activeKey ? s.streams[activeKey] : undefined));
  const lastCompletedId = useChatStore((s) => s.lastCompletedId);

  // Read by async stream callbacks to know whether the user is still looking at this view.
  const viewKey = useRef(activeKey);
  useLayoutEffect(() => {
    viewKey.current = activeKey;
  }, [activeKey]);

  // Fresh view on every navigation, except our own "/" → "/c/:id" hop when a stream starts.
  const [seenNavKey, setSeenNavKey] = useState(location.key);
  if (seenNavKey !== location.key) {
    setSeenNavKey(location.key);
    if (!navState?.fromStart) {
      setPendingKey(null);
      setDraft(navState?.prompt ?? "");
      setVoiceOpen(false);
    }
  }
  const resetAttachments = attachments.reset;
  const autoOpen = useRef<{ seen: string | null; pending: string | null }>({ seen: lastCompletedId, pending: null });
  useEffect(() => {
    const state = location.state as NavState;
    if (state?.fromStart) return;
    resetAttachments(handoffDocs(state).map(attachmentFromDoc));
    useArtifactPanel.getState().reset();
    autoOpen.current.pending = null;
  }, [location.key, location.state, resetAttachments]);

  const messages = useMemo(
    () => (conversationId ? (detail.data?.messages ?? []) : []),
    [conversationId, detail.data?.messages],
  );
  const conversation = conversationId ? detail.data?.conversation : undefined;
  const showWelcome = !conversationId && !stream;
  const { scrollRef, contentRef, isAtBottom, scrollToBottom } = useStickToBottom<HTMLDivElement, HTMLDivElement>(!showWelcome);
  const notFound = !!conversationId && detail.error instanceof ApiError && [404, 403, 422].includes(detail.error.status);
  const loadFailed = !!conversationId && detail.isError && !notFound && !detail.data;
  // Starter cards look at the library: a ready statement → analyse it, else go and upload one.
  const docs = useDocuments(undefined);

  useLayoutEffect(() => {
    scrollToBottom("auto");
  }, [conversationId, conversation?.id, scrollToBottom]);

  useEffect(() => {
    document.title = conversation?.title ? `${conversation.title} · Sphura` : "Sphura";
  }, [conversation?.title]);

  // Read-aloud stops when you leave its chat (its player controls would no longer be on screen) — but not on our own
  // "/" → "/c/:id" hop when a new chat starts, where a spoken reply may already be playing.
  const prevConversation = useRef(conversationId);
  useEffect(() => {
    const prev = prevConversation.current;
    prevConversation.current = conversationId;
    if (prev !== conversationId && prev !== undefined) useSpeech.getState().stop();
  }, [conversationId]);
  useEffect(() => () => useSpeech.getState().stop(), []);

  // Esc stops generation (unless a menu/dialog is open and wants the key).
  const controller = stream?.controller;
  useEffect(() => {
    if (!controller) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || isInOverlay()) return;
      controller.abort();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [controller]);

  const send = useCallback(
    async ({ prompt, modelId, effort: eff, webSearch: web }: ComposerSubmit): Promise<SendChatResult | null> => {
      if (stream) return null;
      const typed = prompt.trim();
      if (conversationId && !detail.data) {
        // Earlier attachments come from the loaded thread; keep the text until it's there.
        setDraft((d) => d || typed);
        toast("Hang on — this chat is still loading.");
        return null;
      }
      if (attachments.items.some((a) => a.status === "uploading")) {
        setDraft((d) => d || typed);
        toast("Hang on — your files are still uploading.");
        return null;
      }
      const ready = attachments.items.filter(isSendable);
      // Attachment-only send → a sensible default question.
      const content =
        typed ||
        (ready.length === 1
          ? isTabularDoc({ filename: ready[0].name })
            ? `Analyse “${ready[0].name}”: where does the money go, and what should I watch?`
            : `Summarise “${ready[0].name}” and list its key figures.`
          : ready.length > 1
            ? `Summarise these ${ready.length} documents and how they relate.`
            : "");
      if (!content) return null;
      const sent = attachments.items;
      const key = conversationId ?? `new:${uid()}`;
      if (!conversationId) setPendingKey(key);
      setDraft("");
      attachments.reset([]);
      scrollToBottom("auto");

      const res = await sendChat({
        key,
        request: {
          conversationId: conversationId ?? null,
          content,
          model: modelId || choice.selected?.id || null,
          webSearch: web,
          docIds: unique([...ready.map((a) => a.docId as string), ...docIdsOf(messages)]),
          mode: "chat",
          effort: eff,
        },
        optimisticUser: { content, attachments: ready.map(toAttachmentRef) },
        onStart: (id) => {
          if (!conversationId && viewKey.current === key) navigate(`/c/${id}`, { state: { fromStart: true } });
        },
      });

      if (!res.started) {
        reportFailure(res);
        if (viewKey.current === key) {
          setDraft((d) => d || typed);
          attachments.reset(sent);
          if (!conversationId) setPendingKey(null);
        }
      }
      return res;
    },
    [attachments, choice.selected?.id, conversationId, detail.data, messages, navigate, scrollToBottom, stream],
  );

  const regenerate = useCallback(() => {
    if (!conversationId || stream) return;
    scrollToBottom("auto");
    void sendChat({
      key: conversationId,
      request: {
        conversationId,
        content: "",
        model: choice.selected?.id ?? null,
        webSearch,
        docIds: docIdsOf(messages),
        mode: "chat",
        effort,
        regenerate: true,
      },
    }).then(reportFailure);
  }, [choice.selected?.id, conversationId, effort, messages, scrollToBottom, stream, webSearch]);

  const edit = useCallback(
    (messageId: string, content: string) => {
      if (!conversationId || stream) return;
      const upto = messages.findIndex((m) => m.id === messageId);
      scrollToBottom("auto");
      void sendChat({
        key: conversationId,
        request: {
          conversationId,
          content,
          model: choice.selected?.id ?? null,
          webSearch,
          docIds: docIdsOf(upto === -1 ? messages : messages.slice(0, upto + 1)),
          mode: "chat",
          effort,
          editMessageId: messageId,
        },
      }).then(reportFailure);
    },
    [choice.selected?.id, conversationId, effort, messages, scrollToBottom, stream, webSearch],
  );

  const stop = useCallback(() => stopStream(activeKey), [activeKey]);

  /* ── auto-send: the workplace dock opens a new chat with its question already asked ── */
  const sendRef = useRef(send);
  useLayoutEffect(() => {
    sendRef.current = send;
  });
  const autoSent = useRef<string | null>(null);
  useEffect(() => {
    const st = location.state as NavState;
    if (!st?.autoSend || !st.prompt || autoSent.current === location.key) return;
    const key = location.key;
    const prompt = st.prompt;
    const web = st.webSearch ?? usePrefs.getState().webSearch;
    // Next tick: the fresh view (draft, attachments) has rendered, so `send` sees the clean state.
    const t = setTimeout(() => {
      if (autoSent.current === key) return;
      autoSent.current = key;
      void sendRef.current({ prompt, modelId: "", effort: usePrefs.getState().effort, webSearch: web });
    }, 0);
    return () => clearTimeout(t);
  }, [location.key, location.state]);

  /* ── voice mode: every utterance is a normal chat turn in this conversation ── */
  const voiceSend = useCallback(
    (text: string) => send({ prompt: text, modelId: choice.forVoice, effort, webSearch }),
    [choice.forVoice, effort, send, webSearch],
  );

  /* ── starter cards ── */
  const onStarter = useCallback(
    (s: Starter) => {
      const library = docs.data ?? [];
      const ready = library.filter((d) => d.status === "ready");
      if (s.id === "statement") {
        if (ready.some(isTabularDoc)) void send({ prompt: s.prompt ?? "", modelId: choice.selected?.id ?? "", effort, webSearch: false });
        else navigate("/dashboard");
        return;
      }
      if (s.id === "document") {
        const doc = ready.find((d) => !isTabularDoc(d));
        if (doc) {
          attachments.reset([attachmentFromDoc(doc)]);
          setDraft(s.prompt ?? "");
        } else navigate("/documents");
        return;
      }
      void send({ prompt: s.prompt ?? "", modelId: choice.selected?.id ?? "", effort, webSearch: s.id === "stock" });
    },
    [attachments, choice.selected?.id, docs.data, effort, navigate, send],
  );

  /* ── artifacts ── */
  const panelOpen = useArtifactPanel((s) => s.open);
  const activeArtifact = useArtifactPanel((s) => s.active);
  const artifactTab = useArtifactPanel((s) => s.tab);
  const artifacts = useMemo(
    () => messages.filter((m) => m.role === "assistant").flatMap((m) => extractArtifacts(m.id, m.content)),
    [messages],
  );
  const panelArtifacts = useMemo<Artifact[]>(
    () => (activeArtifact && !artifacts.some((a) => a.id === activeArtifact.id) ? [...artifacts, activeArtifact] : artifacts),
    [activeArtifact, artifacts],
  );
  const showPanel = panelOpen && !!activeArtifact && !showWelcome && !notFound;

  // Auto-open the panel once when an answer that just finished streaming contains an artifact.
  useEffect(() => {
    const r = autoOpen.current;
    if (lastCompletedId && lastCompletedId !== r.seen) {
      r.seen = lastCompletedId;
      r.pending = lastCompletedId;
    }
    if (!r.pending) return;
    const msg = messages.find((m) => m.id === r.pending);
    if (!msg) return;
    r.pending = null;
    if (voiceOpen) return;
    const list = extractArtifacts(msg.id, msg.content);
    const last = list[list.length - 1];
    const panel = useArtifactPanel.getState();
    if (!last || !panel.claimAutoOpen(msg.id)) return;
    // Wide screens: slide the panel in. Otherwise a sheet would hide the answer, so offer it instead.
    if (isSplit) panel.show(last);
    else toast(`${last.title} is ready`, { action: { label: "Open", onClick: () => useArtifactPanel.getState().show(last) } });
  }, [isSplit, lastCompletedId, messages, voiceOpen]);

  // Spoken replies: a question asked by voice (or every answer, with "Read aloud" on) is read out while it is still
  // being written: finished sentences are spoken as they arrive (see useSpeech.speakLive).
  const liveSpeech = useRef<{ key: string; handle: LiveSpeech; last: string } | null>(null);
  const streamText = stream?.text ?? "";
  const streamMessageId = stream?.assistantMessageId ?? null;
  useEffect(() => {
    const cur = liveSpeech.current;
    if (stream && streamMessageId && streamText) {
      if (!cur) {
        const ui = useUi.getState();
        if (voiceOpen || !(ui.speakNext || usePrefs.getState().autoSpeak)) return;
        ui.setSpeakNext(false);
        const handle = useSpeech.getState().speakLive(streamMessageId);
        liveSpeech.current = { key: streamMessageId, handle, last: streamText };
        handle.feed(streamText);
      } else if (cur.key === streamMessageId) {
        cur.last = streamText;
        cur.handle.feed(streamText);
      }
      return;
    }
    if (!stream && cur) {
      liveSpeech.current = null;
      // Finished normally → speak the rest; stopped or failed → stop talking.
      if (lastCompletedId === cur.key) void cur.handle.finish(cur.last);
      else useSpeech.getState().stop();
    }
  }, [stream, streamMessageId, streamText, lastCompletedId, voiceOpen]);

  const artifactPanel = activeArtifact ? (
    <ArtifactPanel
      artifacts={panelArtifacts}
      active={activeArtifact}
      tab={artifactTab}
      onTabChange={(t) => useArtifactPanel.getState().setTab(t)}
      onSelect={(a) => useArtifactPanel.getState().show(a, artifactTab)}
      onClose={() => useArtifactPanel.getState().close()}
    />
  ) : null;

  const composer = (
    <ChatComposer
      attachments={attachments}
      isStreaming={!!stream}
      onSend={(d) => void send(d)}
      onStop={stop}
      value={draft}
      onChange={setDraft}
      placeholder={showWelcome ? "Ask about a loan, tax, a budget or a stock…" : undefined}
      autoFocus={isDesktop}
      onVoiceMode={() => setVoiceOpen(true)}
      note={showWelcome ? undefined : "Educational only, not investment advice. Check important figures against the cited sources."}
    />
  );

  const chatColumn = (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <AnimatePresence initial={false}>
        {conversation && (
          <motion.div
            key={conversation.id}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: EASE_OUT }}
            className="flex h-10 shrink-0 items-center justify-center px-12"
          >
            <h1 className="max-w-xl truncate text-[13px] font-medium text-muted-foreground" title={stripEmoji(conversation.title) || "Untitled chat"}>
              {stripEmoji(conversation.title) || "Untitled chat"}
            </h1>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="relative min-h-0 flex-1">
        {showWelcome && <HoverGrid className="z-0" />}
        <div ref={scrollRef} className="scrollbar-thin relative z-[1] h-full overflow-x-hidden overflow-y-auto overscroll-contain">
          <div
            ref={contentRef}
            className={cn(
              "relative mx-auto w-full max-w-3xl px-4 sm:px-6",
              showWelcome ? "flex min-h-full flex-col justify-center py-8 sm:py-12" : "pt-3 pb-12 sm:pt-4",
            )}
          >
            {showWelcome ? (
              <Welcome
                name={me.data?.name}
                composer={
                  <motion.div layoutId="chat-composer" layout="position" transition={SPRING_SOFT}>
                    {composer}
                  </motion.div>
                }
                unavailable={choice.noneAvailable ? choice.models : null}
                onStarter={onStarter}
              />
            ) : notFound ? (
              <div className="flex flex-col items-center py-24 text-center">
                <MessageSquareDashed className="size-10 text-muted-foreground" />
                <h2 className="mt-4 font-brand text-2xl">Chat not found</h2>
                <p className="mt-1 text-sm text-muted-foreground">It may have been deleted, or it belongs to another account.</p>
                <Button asChild className="mt-6">
                  <Link to="/" state={{ fresh: true }}>
                    Start a new chat
                  </Link>
                </Button>
              </div>
            ) : loadFailed ? (
              <div className="flex flex-col items-center py-24 text-center">
                <p className="text-sm text-muted-foreground">Couldn't load this chat.</p>
                <Button variant="outline" className="mt-4" onClick={() => void detail.refetch()}>
                  Try again
                </Button>
              </div>
            ) : conversationId && detail.isPending && !stream ? (
              <ThreadSkeleton />
            ) : (
              <Thread
                threadKey={conversationId ?? null}
                messages={messages}
                stream={stream}
                lastCompletedId={lastCompletedId}
                modelLabel={choice.labelFor}
                onEdit={conversationId ? edit : undefined}
                onRegenerate={conversationId ? regenerate : undefined}
              />
            )}
          </div>
        </div>

        <AnimatePresence>
          {!isAtBottom && !showWelcome && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center"
            >
              <Button
                variant="outline"
                size="sm"
                onClick={() => scrollToBottom("smooth")}
                className="pointer-events-auto rounded-full bg-card/95 shadow-soft backdrop-blur"
              >
                <ArrowDown /> Jump to latest
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {!showWelcome && !notFound && (
        <div className="pb-safe mx-auto w-full max-w-3xl shrink-0 px-2 sm:px-6">
          <motion.div layoutId="chat-composer" layout="position" transition={SPRING_SOFT}>
            {composer}
          </motion.div>
        </div>
      )}
    </div>
  );

  return (
    <>
      <ResizablePanelGroup orientation="horizontal" className="min-h-0 flex-1">
        <ResizablePanel id="chat" minSize={340} className="min-w-0">
          {chatColumn}
        </ResizablePanel>
        {isSplit && showPanel && (
          <>
            <ResizableHandle withHandle aria-label="Resize artifact panel" />
            <ResizablePanel id="artifact" defaultSize="44" minSize={320} maxSize="72" className="min-w-0">
              <motion.div
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                className="h-full border-l"
              >
                {artifactPanel}
              </motion.div>
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>

      {!isSplit && (
        <Sheet open={showPanel} onOpenChange={(open) => !open && useArtifactPanel.getState().close()}>
          <SheetContent
            side="bottom"
            showCloseButton={false}
            onOpenAutoFocus={focusSheetItself}
            className="gap-0 overflow-hidden rounded-t-2xl p-0 outline-none data-[side=bottom]:h-[88dvh]"
          >
            <SheetTitle className="sr-only">{activeArtifact?.title ?? "Artifact"}</SheetTitle>
            <SheetDescription className="sr-only">Preview and code of the artifact</SheetDescription>
            {artifactPanel}
          </SheetContent>
        </Sheet>
      )}

      <VoiceMode open={voiceOpen} onClose={() => setVoiceOpen(false)} onSend={voiceSend} stream={stream} />
    </>
  );
}
