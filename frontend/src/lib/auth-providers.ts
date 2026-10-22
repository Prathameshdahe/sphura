import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

export interface GoogleProvider {
  enabled: boolean;
  supabaseUrl: string | null;
  anonKey: string | null;
}

const DISABLED: GoogleProvider = { enabled: false, supabaseUrl: null, anonKey: null };

export const authProvidersKey = ["auth-providers"] as const;

const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v.trim() : null);

/** Google is offered only when the server says so *and* hands over a project URL + anon key. */
function normalizeGoogle(raw: unknown): GoogleProvider {
  if (!raw || typeof raw !== "object") return DISABLED;
  const g = raw as { enabled?: unknown; supabaseUrl?: unknown; anonKey?: unknown };
  const supabaseUrl = str(g.supabaseUrl);
  const anonKey = str(g.anonKey);
  if (g.enabled !== true || !supabaseUrl || !anonKey) return DISABLED;
  return { enabled: true, supabaseUrl, anonKey };
}

export interface AuthProvidersState {
  google: GoogleProvider;
}

/** Never throws: an older backend without /api/auth/providers (404), or any failure, means "no Google button". */
export async function fetchAuthProviders(): Promise<AuthProvidersState> {
  try {
    const res = await api.authProviders();
    return { google: normalizeGoogle((res as { google?: unknown } | undefined)?.google) };
  } catch {
    return { google: DISABLED };
  }
}

/** `GET /api/auth/providers`, cached for five minutes; resolves to `google.enabled: false` on any failure. */
export function useAuthProviders() {
  return useQuery({
    queryKey: authProvidersKey,
    queryFn: fetchAuthProviders,
    staleTime: 5 * 60_000,
    retry: false,
    meta: { silent: true },
  });
}
