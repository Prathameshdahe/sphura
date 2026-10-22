import { useEffect, useMemo, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Brain, BrainCircuit, CircleAlert, Lock, MessageSquareText, Search, Trash, UserRound } from "lucide-react";
import { toast } from "sonner";
import { AddMemoryForm } from "@/components/features/memory/add-memory-form";
import { MemoryRow } from "@/components/features/memory/memory-row";
import { Page } from "@/components/layout/page";
import { PageHeader } from "@/components/layout/page-header";
import { Stagger, StaggerItem } from "@/components/motion";
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
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/api";
import { useDeleteMemory, useForgetEverything, useMemory, useSetMemoryEnabled } from "@/lib/feature-api/memory";
import type { MemoryItem } from "@/lib/feature-types";
import { cn } from "@/lib/utils";

const EXPLAINERS = [
  { icon: UserRound, title: "What it keeps", text: "Durable facts you share — income band, goals, risk comfort, preferences. At most two per conversation turn." },
  { icon: MessageSquareText, title: "How it's used", text: "The most relevant memories are added to Sphura's context so answers fit your situation." },
  { icon: Lock, title: "Your privacy", text: "Private to your account. Never account numbers, passwords or other secrets. Delete anything, anytime." },
];

/** Memory: toggle, add, review and forget what Sphura remembers about the user. */
export default function Memory() {
  const memory = useMemory();
  const setEnabled = useSetMemoryEnabled();
  const del = useDeleteMemory();
  const forget = useForgetEverything();
  const [confirmAll, setConfirmAll] = useState(false);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    document.title = "Memory · Sphura";
    return () => {
      document.title = "Sphura";
    };
  }, []);

  const state = memory.data;
  const items = useMemo(() => state?.items ?? [], [state]);
  // Keep the filter box while a filter is active, even if deletes drop the list to 5 or fewer items.
  const showFilter = items.length > 5 || filter !== "";
  const list = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return f ? items.filter((m) => m.content.toLowerCase().includes(f)) : items;
  }, [items, filter]);

  const toggle = (on: boolean) =>
    setEnabled.mutate(on, {
      onSuccess: () => toast.success(on ? "Memory is on" : "Memory is off", { description: on ? undefined : "Saved memories are kept but not used." }),
    });

  const remove = (m: MemoryItem) => del.mutate(m.id, { onSuccess: () => toast.success("Forgotten") });

  const forgetAll = () => {
    setConfirmAll(false);
    forget.mutate(undefined, { onSuccess: () => toast.success("Sphura forgot everything about you") });
  };

  const enabled = !!state?.enabled;

  return (
    <Page
      width="narrow"
      header={
        <PageHeader
          icon={Brain}
          title="Memory"
          subtitle="What Sphura remembers about you across chats, so answers get more personal over time. You stay in control."
          action={
            items.length > 0 ? (
              <Button variant="destructive" onClick={() => setConfirmAll(true)} disabled={forget.isPending}>
                <Trash /> Forget everything
              </Button>
            ) : null
          }
        />
      }
    >
      {memory.isPending ? (
        <div className="space-y-3" aria-busy="true" aria-label="Loading memory">
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-10 w-full rounded-lg" />
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      ) : memory.isError && !state ? (
        <div role="alert" className="mt-10 flex flex-col items-center gap-2 text-center text-sm text-muted-foreground">
          <CircleAlert className="size-6 text-destructive" aria-hidden />
          {errorMessage(memory.error)}
          <Button variant="outline" size="sm" onClick={() => void memory.refetch()}>
            Retry
          </Button>
        </div>
      ) : (
        <>
          <section
            aria-labelledby="memory-toggle-label"
            className={cn(
              "relative overflow-hidden rounded-2xl border bg-card p-4 shadow-xs transition-colors duration-200 sm:p-5",
              enabled && "border-brand/25",
            )}
          >
            <div className="relative flex items-start gap-4">
              <div
                className={cn(
                  "hidden size-10 shrink-0 place-items-center rounded-xl border transition-colors duration-200 min-[400px]:grid",
                  enabled ? "border-brand/20 bg-brand/8 text-brand" : "bg-muted text-muted-foreground",
                )}
                aria-hidden
              >
                <BrainCircuit className="size-5" strokeWidth={1.75} />
              </div>
              <div className="min-w-0 flex-1">
                <label id="memory-toggle-label" htmlFor="memory-toggle" className="block cursor-pointer text-sm font-semibold">
                  Let Sphura remember things about you
                </label>
                <p className="mt-1 text-sm text-muted-foreground">
                  {enabled
                    ? "On — Sphura recalls relevant memories in every chat and saves new durable facts it learns."
                    : "Off — Sphura won't read your memories or save new ones. Existing memories are kept until you delete them."}
                </p>
              </div>
              <Switch id="memory-toggle" checked={enabled} disabled={setEnabled.isPending} onCheckedChange={toggle} className="mt-1" />
            </div>
          </section>

          <div className="mt-6">
            <AddMemoryForm />
          </div>

          {items.length === 0 ? (
            <div className="relative mt-8 overflow-hidden rounded-2xl border bg-card px-5 py-10 text-center sm:px-8">
              <div className="relative">
                <div className="mx-auto grid size-11 place-items-center rounded-xl border bg-muted/60 text-muted-foreground">
                  <Brain className="size-5" strokeWidth={1.75} aria-hidden />
                </div>
                <h2 className="mt-4 font-brand text-xl font-normal sm:text-[1.4rem]">Nothing remembered yet</h2>
                <p className="mx-auto mt-1.5 max-w-md text-sm text-balance text-muted-foreground">
                  {enabled
                    ? "Chat normally — when you mention something lasting about your finances, Sphura will note it here. Or add a fact above."
                    : "Turn memory on and Sphura will start noting lasting facts about you. You can also add one above."}
                </p>
                <Stagger className="mx-auto mt-8 grid max-w-2xl gap-3 text-left sm:grid-cols-3" aria-label="How memory works">
                  {EXPLAINERS.map((e) => (
                    <StaggerItem key={e.title} className="rounded-xl border bg-background p-3.5">
                      <e.icon className="size-4 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                      <h3 className="mt-2 text-sm font-medium">{e.title}</h3>
                      <p className="mt-1 text-xs text-muted-foreground">{e.text}</p>
                    </StaggerItem>
                  ))}
                </Stagger>
              </div>
            </div>
          ) : (
            <section aria-labelledby="memory-list-title" className="mt-8">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="memory-list-title" className="text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">{items.length}</span> memor{items.length === 1 ? "y" : "ies"}
                </h2>
                {showFilter && (
                  <div className="relative w-full sm:w-56">
                    <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                    <input
                      type="search"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                      placeholder="Filter memories"
                      aria-label="Filter memories"
                      className="h-8 w-full rounded-lg border bg-card pr-3 pl-8 text-sm outline-none focus:border-ring/60 focus:ring-3 focus:ring-ring/20"
                    />
                  </div>
                )}
              </div>
              <ul className="mt-3 space-y-2.5">
                <AnimatePresence initial={false}>
                  {list.map((m) => (
                    <MemoryRow key={m.id} item={m} onDelete={remove} />
                  ))}
                </AnimatePresence>
                {list.length === 0 && filter && (
                  <li className="py-8 text-center text-sm text-muted-foreground">No memories match “{filter}”.</li>
                )}
              </ul>
              <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
                <Lock className="size-3.5 shrink-0" aria-hidden />
                Private to your account · never secrets or credentials · deleting is immediate
              </p>
            </section>
          )}
        </>
      )}

      <AlertDialog open={confirmAll} onOpenChange={setConfirmAll}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Forget everything?</AlertDialogTitle>
            <AlertDialogDescription>
              All {items.length} memor{items.length === 1 ? "y" : "ies"} will be permanently deleted. Your chats are not affected.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={forgetAll}>
              Forget everything
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Page>
  );
}
