import type { Query } from "@tanstack/react-query";

const FAST_FOR_MS = 2 * 60_000;
const SLOW_MS = 10_000;
const GIVE_UP_AFTER_MS = 20 * 60_000;
const windows = new Map<string, { sig: string; since: number }>();

/**
 * `refetchInterval` for "poll while something is still processing". `pendingSig` returns a signature of what is
 * still pending (e.g. the pending ids) or null when nothing is. Polls every `ms` at first, every 10 s after two
 * minutes, and stops after twenty minutes of the same items pending — a stuck job must not poll forever; a new
 * pending item starts a fresh window. React Query already pauses polling while the tab is hidden.
 */
export function pollWhilePending<TData>(pendingSig: (data: TData) => string | null, ms: number) {
  return (query: Pick<Query<TData>, "queryHash" | "state">): number | false => {
    const key = query.queryHash;
    const sig = query.state.data === undefined ? null : pendingSig(query.state.data);
    if (sig === null) {
      windows.delete(key);
      return false;
    }
    const now = Date.now();
    let w = windows.get(key);
    if (!w || w.sig !== sig) {
      w = { sig, since: now };
      windows.set(key, w);
    }
    const age = now - w.since;
    if (age > GIVE_UP_AFTER_MS) return false;
    return age > FAST_FOR_MS ? SLOW_MS : ms;
  };
}

/** Signature of the items still being processed (null when none). */
export function pendingIds<T>(items: readonly T[] | undefined, isPending: (item: T) => boolean, id: (item: T) => string): string | null {
  const ids = (items ?? []).filter(isPending).map(id);
  return ids.length ? ids.sort().join(",") : null;
}
