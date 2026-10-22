import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuthProviders } from "@/lib/auth-providers";
import { EASE_OUT } from "@/lib/motion";
import { startGoogleSignIn } from "@/lib/supabase";
import { cn } from "@/lib/utils";

/** Google's multicolour "G" (brand colours as published in Google's sign-in button guidelines). */
export function GoogleG({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={cn("size-[18px] shrink-0", className)} aria-hidden="true" focusable="false">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

interface GoogleButtonProps {
  className?: string;
  /** Full-width form button (auth pages) or an inline CTA (landing). */
  block?: boolean;
  size?: "default" | "lg";
}

/** "Continue with Google": renders nothing unless /api/auth/providers says Google is enabled. */
export function GoogleButton({ className, block = true, size = "lg" }: GoogleButtonProps) {
  const providers = useAuthProviders();
  const google = providers.data?.google;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!google?.enabled || !google.supabaseUrl || !google.anonKey) return null;
  const { supabaseUrl, anonKey } = google;

  const start = async () => {
    setError(null);
    setLoading(true);
    try {
      await startGoogleSignIn(supabaseUrl, anonKey);
      // The browser is on its way to Google; keep the spinner until the page unloads.
    } catch (e) {
      setLoading(false);
      setError(e instanceof Error && e.message ? `Couldn't start Google sign-in: ${e.message}` : "Couldn't start Google sign-in.");
    }
  };

  return (
    <div className={cn(block && "w-full", className)}>
      <Button
        type="button"
        variant="outline"
        size={size}
        onClick={() => void start()}
        disabled={loading}
        aria-busy={loading || undefined}
        className={cn("gap-2.5 bg-card font-medium shadow-xs hover:bg-muted", block && "h-10 w-full text-sm", !block && "h-10 px-4")}
      >
        {loading ? <LoaderCircle className="animate-spin" /> : <GoogleG />}
        {loading ? "Opening Google…" : "Continue with Google"}
      </Button>
      <AnimatePresence initial={false}>
        {error && (
          <motion.p
            role="alert"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.18, ease: EASE_OUT }}
            className="overflow-hidden pt-2 text-xs text-destructive"
          >
            {error}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Google button + an "or" divider above the email form; nothing at all when Google is off. */
export function GoogleSignIn() {
  const providers = useAuthProviders();
  if (!providers.data?.google.enabled) return null;
  return (
    <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, ease: EASE_OUT }}>
      <GoogleButton />
      <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground" role="separator" aria-label="or">
        <span className="h-px flex-1 bg-border" aria-hidden />
        <span aria-hidden>or</span>
        <span className="h-px flex-1 bg-border" aria-hidden />
      </div>
    </motion.div>
  );
}
