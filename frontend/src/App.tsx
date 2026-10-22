import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { GuestOnly, RequireAuth, Splash } from "@/components/auth-guard";
import { ErrorBoundary } from "@/components/error-boundary";
import { AppShell } from "@/components/layout/app-shell";
import { setUnauthorizedHandler } from "@/lib/api";
import ChatPage from "@/pages/ChatPage";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import { abortAllStreams } from "@/stores/chat-store";

const AuthCallback = lazy(() => import("@/pages/AuthCallback"));
const Landing = lazy(() => import("@/pages/Landing"));
const Documents = lazy(() => import("@/pages/Documents"));
const Focus = lazy(() => import("@/pages/Focus"));
const Dashboard = lazy(() => import("@/pages/features/Dashboard"));
const Markets = lazy(() => import("@/pages/features/Markets"));
const Lab = lazy(() => import("@/pages/features/Lab"));
const Memory = lazy(() => import("@/pages/features/Memory"));

/** Session expiry anywhere → drop cached data and go to /login (soft, no reload). */
function useUnauthorizedRedirect() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  useEffect(() => {
    setUnauthorizedHandler(() => {
      abortAllStreams();
      qc.removeQueries();
      navigate("/login", { replace: true, state: { from: window.location.pathname + window.location.search } });
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate, qc]);
}

/** Keeps old links alive: /finance → /dashboard, /insights → /lab (query string preserved). */
function Redirect({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}

export default function App() {
  useUnauthorizedRedirect();
  const { pathname } = useLocation();
  return (
    <ErrorBoundary resetKey={pathname}>
      <Suspense fallback={<Splash />}>
        <Routes>
          <Route
            path="/login"
            element={
              <GuestOnly>
                <Login />
              </GuestOnly>
            }
          />
          <Route
            path="/signup"
            element={
              <GuestOnly>
                <Signup />
              </GuestOnly>
            }
          />
          {/* Public: the landing page (also what signed-out visitors see at "/") and the Google sign-in return. */}
          <Route path="/welcome" element={<Landing />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route element={<RequireAuth />}>
            {/* Dev-only full-screen orb (FINANCE_PLAN §1): not in the nav, still builds. */}
            <Route path="/focus" element={<Focus />} />
            <Route element={<AppShell />}>
              <Route path="/" element={<ChatPage />} />
              <Route path="/c/:conversationId" element={<ChatPage />} />
              <Route path="/documents" element={<Documents />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/markets" element={<Markets />} />
              <Route path="/lab" element={<Lab />} />
              <Route path="/memory" element={<Memory />} />
              <Route path="/finance" element={<Redirect to="/dashboard" />} />
              <Route path="/insights" element={<Redirect to="/lab" />} />
            </Route>
          </Route>
          {/* Removed pages (/papers, /workspace, /arena, /graph) and anything unknown → home. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
