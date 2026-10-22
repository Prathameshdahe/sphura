import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CircleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SphuraLogo } from "@/components/ui/sphura-logo";
import { ApiError, api } from "@/lib/api";
import { fetchAuthProviders } from "@/lib/auth-providers";
import { EASE_OUT } from "@/lib/motion";
import { qk } from "@/lib/queries";
import { forgetSupabaseSession, sessionFromCallback } from "@/lib/supabase";

/** Turns whatever went wrong into one sentence a person can act on. */
function friendly(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 404 || e.status === 405) return "This server doesn't support Google sign-in yet. Sign in with your email instead.";
    if (e.status === 401 || e.status === 403) return e.detail || "Google confirmed who you are, but Sphura couldn't open a session for you.";
    return e.detail;
  }
  const message = e instanceof Error ? e.message : "";
  if (/verifier/i.test(message)) {
    return "This sign-in link has expired or was opened in a different tab. Start again from the sign-in page.";
  }
  if (/expired|invalid.*(grant|code)|already.*used/i.test(message)) {
    return "This sign-in link has already been used or has expired. Start again from the sign-in page.";
  }
  return message || "Something went wrong while signing you in.";
}

/** /auth/callback: Google → Supabase hands back `?code=`; exchange it, then trade the token for Sphura's own session. */
export default function AuthCallback() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    document.title = "Signing in · Sphura";
    return () => {
      document.title = "Sphura";
    };
  }, []);

  useEffect(() => {
    // StrictMode runs effects twice in development; an auth code can be redeemed only once.
    if (started.current) return;
    started.current = true;

    const query = new URLSearchParams(window.location.search);
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const providerError = query.get("error_description") ?? hash.get("error_description") ?? query.get("error") ?? hash.get("error");
    const code = query.get("code");

    void (async () => {
      try {
        if (providerError) throw new Error(providerError.replace(/\+/g, " "));
        if (!code) throw new Error("The sign-in link is missing its code. Start again from the sign-in page.");
        const { google } = await fetchAuthProviders();
        if (!google.enabled || !google.supabaseUrl || !google.anonKey) {
          throw new Error("Google sign-in isn't available on this server right now. Sign in with your email instead.");
        }
        const session = await sessionFromCallback(google.supabaseUrl, google.anonKey, code);
        const user = await api.oauthSupabase(session.access_token);
        forgetSupabaseSession();
        qc.setQueryData(qk.me, user);
        navigate("/", { replace: true });
      } catch (e) {
        forgetSupabaseSession();
        setError(friendly(e));
      }
    })();
  }, [navigate, qc]);

  return (
    <main className="grid min-h-dvh place-items-center bg-background px-6">
      {error ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.26, ease: EASE_OUT }}
          className="w-full max-w-sm text-center"
          role="alert"
        >
          <div className="mx-auto grid size-11 place-items-center rounded-xl border bg-card text-destructive shadow-xs">
            <CircleAlert className="size-5" aria-hidden />
          </div>
          <h1 className="mt-5 font-brand text-[1.75rem] leading-tight">We couldn't sign you in</h1>
          <p className="mt-2 text-sm text-pretty text-muted-foreground">{error}</p>
          <Button asChild className="mt-6">
            <Link to="/login" replace>
              Back to sign in
            </Link>
          </Button>
        </motion.div>
      ) : (
        <div className="flex flex-col items-center text-center" role="status" aria-live="polite">
          <SphuraLogo size={44} state="thinking" />
          <p className="mt-5 font-brand text-xl">Signing you in…</p>
          <p className="mt-1 text-sm text-muted-foreground">Confirming your Google account.</p>
        </div>
      )}
    </main>
  );
}
