import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import { Ellipsis, MessageSquareDashed, PanelLeftClose, Pencil, Pin, PinOff, Search, SquarePen, Trash, X } from "lucide-react";
import { IconButton } from "@/components/icon-button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounced } from "@/hooks/use-media-query";
import { stripEmoji } from "@/lib/emoji";
import { groupConversations } from "@/lib/format";
import { EASE_OUT, SPRING_SNAPPY } from "@/lib/motion";
import { MOD } from "@/lib/platform";
import { useConversations, useDeleteConversation, useUpdateConversation } from "@/lib/queries";
import type { ConversationSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { stopStream, useChatStore } from "@/stores/chat-store";
import { usePrefs } from "@/stores/prefs";
import { useUi } from "@/stores/ui";

const MotionLink = motion.create(Link);

interface RowProps {
  c: ConversationSummary;
  active: boolean;
  onDelete: (c: ConversationSummary) => void;
}

function ConversationRow({ c, active, onDelete }: RowProps) {
  const [renaming, setRenaming] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const keepFocus = useRef(false);
  const committed = useRef(false);
  const streaming = useChatStore((s) => !!s.streams[c.id]);
  const update = useUpdateConversation();

  useEffect(() => {
    if (!renaming) return;
    const t = setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 0);
    return () => clearTimeout(t);
  }, [renaming]);

  const commit = (value: string) => {
    if (committed.current) return;
    committed.current = true;
    setRenaming(false);
    const title = value.trim();
    if (title && title !== c.title) update.mutate({ id: c.id, patch: { title } });
  };

  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.18, ease: EASE_OUT }}
      className="group/row relative"
    >
      {renaming ? (
        <input
          ref={inputRef}
          defaultValue={c.title}
          aria-label="Chat title"
          maxLength={200}
          onBlur={(e) => commit(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit(e.currentTarget.value);
            if (e.key === "Escape") {
              e.stopPropagation();
              committed.current = true;
              setRenaming(false);
            }
          }}
          className="h-8 w-full rounded-lg border border-ring bg-background px-2.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
        />
      ) : (
        <MotionLink
          to={`/c/${c.id}`}
          aria-current={active ? "page" : undefined}
          title={c.title}
          whileTap={{ scale: 0.98 }}
          transition={SPRING_SNAPPY}
          className={cn(
            "relative flex h-8 items-center gap-2 rounded-lg pr-8 pl-2.5 text-[13.5px] transition-colors duration-150 focus-visible:outline-2 focus-visible:-outline-offset-2",
            active ? "font-medium text-sidebar-accent-foreground" : "text-sidebar-foreground/75 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground",
          )}
        >
          {active && (
            <motion.span
              layoutId="history-active"
              className="absolute inset-0 rounded-lg bg-sidebar-accent"
              transition={SPRING_SNAPPY}
              aria-hidden
            />
          )}
          {streaming && <span className="relative size-1.5 shrink-0 animate-pulse rounded-full bg-primary" aria-label="Answering" />}
          {c.pinned && !streaming && <Pin className="relative size-3 shrink-0 text-muted-foreground" />}
          <span className="relative truncate">{stripEmoji(c.title) || "Untitled chat"}</span>
        </MotionLink>
      )}
      {!renaming && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label={`Options for ${c.title || "chat"}`}
              className={cn(
                "absolute top-1/2 right-1 z-10 grid size-6 -translate-y-1/2 place-items-center rounded-md text-muted-foreground transition-opacity hover:bg-background/70 hover:text-foreground focus-visible:opacity-100 data-[state=open]:opacity-100",
                active ? "opacity-100" : "opacity-100 md:opacity-0 md:group-hover/row:opacity-100",
              )}
            >
              <Ellipsis className="size-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            className="w-40"
            onCloseAutoFocus={(e) => {
              if (keepFocus.current) {
                e.preventDefault();
                keepFocus.current = false;
              }
            }}
          >
            <DropdownMenuItem
              onSelect={() => {
                keepFocus.current = true;
                committed.current = false;
                setRenaming(true);
              }}
            >
              <Pencil /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => update.mutate({ id: c.id, patch: { pinned: !c.pinned } })}>
              {c.pinned ? <PinOff /> : <Pin />} {c.pinned ? "Unpin" : "Pin"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => onDelete(c)}>
              <Trash /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </motion.li>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-2 px-1 pt-2" aria-busy="true" aria-label="Loading chats">
      <Skeleton className="mb-3 h-3 w-16" />
      {[78, 64, 88, 52, 70, 60].map((w, i) => (
        <Skeleton key={i} className="h-6" style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}

/** Conversation history: new chat, search and grouped chats. Page navigation lives in the top bar. */
export function HistoryPanel({ mobile = false }: { mobile?: boolean }) {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const setCollapsed = usePrefs((s) => s.setSidebarCollapsed);
  const setMobileOpen = useUi((s) => s.setMobileSidebarOpen);
  const focusTick = useUi((s) => s.searchFocusTick);
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim(), 250);
  const list = useConversations(q);
  const remove = useDeleteConversation();
  const [deleting, setDeleting] = useState<ConversationSummary | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Ctrl+K: focus search (also when this panel has just mounted inside the mobile sheet).
  useEffect(() => {
    if (!useUi.getState().searchFocusPending) return;
    const t = setTimeout(() => {
      if (useUi.getState().consumeSearchFocus()) searchRef.current?.focus();
    }, 60);
    return () => clearTimeout(t);
  }, [focusTick]);

  const groups = useMemo(() => {
    const items = list.data ?? [];
    return q ? [{ label: "Results", items }] : groupConversations(items);
  }, [list.data, q]);

  const confirmDelete = () => {
    const c = deleting;
    if (!c) return;
    setDeleting(null);
    stopStream(c.id);
    remove.mutate(c.id, { onSuccess: () => toast.success("Chat deleted") });
    if (conversationId === c.id) navigate("/", { replace: true, state: { fresh: true } });
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-12 shrink-0 items-center gap-1 pr-2 pl-4">
        <h2 className="font-brand text-[1.05rem] font-medium tracking-tight">Chats</h2>
        <div className="ml-auto flex items-center gap-0.5">
          <IconButton label="New chat" side="bottom" shortcut={`${MOD} ⇧ O`} onClick={() => navigate("/", { state: { fresh: true } })}>
            <SquarePen />
          </IconButton>
          {mobile ? (
            <IconButton label="Close" side="bottom" onClick={() => setMobileOpen(false)}>
              <X />
            </IconButton>
          ) : (
            <IconButton label="Hide chat history" side="bottom" onClick={() => setCollapsed(true)}>
              <PanelLeftClose />
            </IconButton>
          )}
        </div>
      </div>

      <div className="px-2.5">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={searchRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setQuery("");
                e.currentTarget.blur();
              }
            }}
            placeholder="Search chats"
            aria-label="Search chats"
            className="h-8 w-full rounded-lg border border-transparent bg-sidebar-accent/45 pr-12 pl-8 text-sm transition-colors outline-none placeholder:text-muted-foreground focus:border-ring/50 focus:bg-background focus:ring-3 focus:ring-ring/15 [&::-webkit-search-cancel-button]:hidden"
          />
          {query ? (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setQuery("")}
              className="absolute top-1/2 right-1.5 grid size-5 -translate-y-1/2 place-items-center rounded text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          ) : (
            <kbd className="pointer-events-none absolute top-1/2 right-2 hidden -translate-y-1/2 font-sans text-[10.5px] text-muted-foreground md:block">
              {MOD} K
            </kbd>
          )}
        </div>
      </div>

      <nav className="scrollbar-thin mt-2 min-h-0 flex-1 overflow-y-auto px-2.5 pb-4" aria-label="Chats">
        {list.isPending ? (
          <ListSkeleton />
        ) : list.isError && !list.data ? (
          <div className="px-2 py-6 text-center text-sm text-muted-foreground">
            Couldn't load chats.{" "}
            <button type="button" className="underline underline-offset-2" onClick={() => void list.refetch()}>
              Retry
            </button>
          </div>
        ) : groups.length === 0 || groups[0].items.length === 0 ? (
          <div className="flex flex-col items-center px-4 py-10 text-center text-sm text-muted-foreground">
            <MessageSquareDashed className="mb-2 size-5" aria-hidden />
            {q ? (
              <>No chats match “{q}”.</>
            ) : (
              <>
                <p className="font-medium text-foreground/80">No chats yet</p>
                <p className="mt-1 text-xs">Ask something and it will be kept here.</p>
              </>
            )}
          </div>
        ) : (
          groups.map((g) => (
            <section key={g.label} className="mt-4 first:mt-1">
              <h3 className="mb-1 px-2.5 text-[11.5px] font-medium text-muted-foreground">{g.label}</h3>
              <ul className="space-y-px">
                <AnimatePresence initial={false}>
                  {g.items.map((c) => (
                    <ConversationRow key={c.id} c={c} active={c.id === conversationId} onDelete={setDeleting} />
                  ))}
                </AnimatePresence>
              </ul>
            </section>
          ))
        )}
      </nav>

      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this chat?</AlertDialogTitle>
            <AlertDialogDescription>
              “{deleting?.title || "Untitled chat"}” and all its messages will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
