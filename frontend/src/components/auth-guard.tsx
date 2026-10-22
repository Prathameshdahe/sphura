import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { RotateCcw, ServerOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SphuraLogo } from "@/components/ui/sphura-logo";
import { ApiError, errorMessage, returnPath } from "@/lib/api";
import { useMe } from "@/lib/queries";

const Landing = lazy(() => import("@/pages/Landing"));

export function Splash() {
  return (
    <div className="grid min-h-dvh place-items-center bg-background" role="status" aria-label="Loading Sphura">
      <SphuraLogo size={56} state="thinking" />
    </div>
  );
}

function ServerDown({ error, onRetry, retrying }: { error: unknown; onRetry: () => void; retrying: boolean }) {
  return (
    <div className="relative grid min-h-dvh place-items-center overflow-hidden bg-background px-6">
      <div className="relative max-w-sm text-center">
        <div className="mx-auto grid size-11 place-items-center rounded-xl border bg-card shadow-xs">
          <ServerOff className="size-5 text-muted-foreground" />
        </div>
        <h1 className="mt-5 font-brand text-2xl">Sphura is offline</h1>
        <p className="mt-2 text-sm text-muted-foreground">{errorMessage(error)}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Start the API with <code className="rounded bg-muted px-1 py-0.5 font-mono">uvicorn app.main:app --port 8000</code>
        </p>
        <Button className="mt-6" onClick={onRetry} disabled={retrying}>
          <RotateCcw className={retrying ? "animate-spin" : undefined} /> Try again
        </Button>
      </div>
    </div>
  );
}

/**
 * Protects app routes via /api/auth/me. Signed-out visitors on "/" get the public landing page (signed-in people get
 * the chat there); any other protected path → /login, remembering where you were.
 */
export function RequireAuth() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <Splash />;
  if (me.isError) {
    if (me.error instanceof ApiError && me.error.status === 401) {
      if (location.pathname === "/") {
        return (
          <Suspense fallback={<Splash />}>
            <Landing />
          </Suspense>
        );
      }
      return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
    }
    return <ServerDown error={me.error} onRetry={() => void me.refetch()} retrying={me.isFetching} />;
  }
  return <Outlet />;
}

/** Login/signup are for signed-out visitors only. */
export function GuestOnly({ children }: { children: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <Splash />;
  // Same target as the login form's own redirect: this fires first once the session lands in the cache.
  if (me.isSuccess && me.data) return <Navigate to={returnPath(location.state)} replace />;
  return <>{children}</>;
}
