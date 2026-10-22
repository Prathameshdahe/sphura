import type { Session, SupabaseClient } from "@supabase/supabase-js";

/*
 * Google sign-in runs through Supabase Auth (PKCE). Supabase only proves who the person is: the browser trades the
 * Supabase access token for Sphura's own httpOnly session cookie (POST /api/auth/oauth/supabase) and then forgets
 * the Supabase session again.
 *
 * Why `persistSession: true` here: with `persistSession: false` supabase-js keeps everything — including the PKCE
 * code verifier written by signInWithOAuth — in an in-memory object, so the verifier is gone after the redirect to
 * Google and back, and `exchangeCodeForSession` fails with "code verifier not found". The client therefore persists
 * into a small sessionStorage adapter under its own key (tab-scoped, never localStorage, no auto refresh), and
 * `forgetSupabaseSession()` wipes those keys as soon as the hand-off to the backend is done (or fails).
 */

const STORAGE_KEY = "sphura-google-auth";

const tabStorage = {
  getItem(key: string): string | null {
    try {
      return window.sessionStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem(key: string, value: string): void {
    try {
      window.sessionStorage.setItem(key, value);
    } catch {
      /* storage blocked (private mode): the redirect will fail with a readable error instead */
    }
  },
  removeItem(key: string): void {
    try {
      window.sessionStorage.removeItem(key);
    } catch {
      /* nothing stored */
    }
  },
};

const clients = new Map<string, Promise<SupabaseClient>>();

/** One lazily created client per Supabase project (the SDK is code-split: it loads only when Google is used). */
export function getSupabase(supabaseUrl: string, anonKey: string): Promise<SupabaseClient> {
  const cacheKey = `${supabaseUrl}|${anonKey}`;
  let client = clients.get(cacheKey);
  if (!client) {
    client = import("@supabase/supabase-js").then(({ createClient }) =>
      createClient(supabaseUrl, anonKey, {
        auth: {
          flowType: "pkce",
          persistSession: true,
          autoRefreshToken: false,
          detectSessionInUrl: true,
          storage: tabStorage,
          storageKey: STORAGE_KEY,
        },
      }),
    );
    client.catch(() => clients.delete(cacheKey));
    clients.set(cacheKey, client);
  }
  return client;
}

/** Sends the browser to Google (via Supabase); it comes back to /auth/callback?code=…. */
export async function startGoogleSignIn(supabaseUrl: string, anonKey: string): Promise<void> {
  const supabase = await getSupabase(supabaseUrl, anonKey);
  const { error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: `${window.location.origin}/auth/callback` },
  });
  if (error) throw error;
}

/**
 * Turns the `code` from the callback URL into a Supabase session. `detectSessionInUrl` may already have exchanged
 * it while the client initialised, so an existing session wins; otherwise exchange explicitly.
 */
export async function sessionFromCallback(supabaseUrl: string, anonKey: string, code: string): Promise<Session> {
  const supabase = await getSupabase(supabaseUrl, anonKey);
  const existing = await supabase.auth.getSession();
  if (existing.data.session) return existing.data.session;
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);
  if (data.session) return data.session;
  // A code can be redeemed only once: if the automatic exchange won the race, its session is in storage now.
  const again = await supabase.auth.getSession();
  if (again.data.session) return again.data.session;
  throw error ?? new Error("Google didn't return a session.");
}

/** Drops the temporary Supabase session and PKCE verifier from this tab. */
export function forgetSupabaseSession(): void {
  try {
    const store = window.sessionStorage;
    for (let i = store.length - 1; i >= 0; i--) {
      const key = store.key(i);
      if (key?.startsWith(STORAGE_KEY)) store.removeItem(key);
    }
  } catch {
    /* storage unavailable: nothing was stored */
  }
}
