import { Suspense, useEffect, useState } from "react";
import { useLocation, useNavigate, useOutlet } from "react-router-dom";
import { AnimatePresence, motion, type Variants } from "framer-motion";
import { HistoryPanel } from "@/components/layout/sidebar";
import { AppTopBar } from "@/components/layout/top-bar";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { SphuraLogo } from "@/components/ui/sphura-logo";
import { useIsDesktop } from "@/hooks/use-media-query";
import { focusSheetItself } from "@/lib/focus";
import { EASE_OUT } from "@/lib/motion";
import { spaceIndex } from "@/lib/nav";
import { usePrefs } from "@/stores/prefs";
import { useUi } from "@/stores/ui";

/** Ctrl/⌘+K → search chats (opens the history panel) · Ctrl/⌘+Shift+O → new chat. */
function useGlobalShortcuts(isDesktop: boolean) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (!mod || e.altKey) return;
      const key = e.key.toLowerCase();
      if (key === "k" && !e.shiftKey) {
        e.preventDefault();
        if (spaceIndex(pathname) !== 0) navigate(useUi.getState().lastChatPath);
        if (isDesktop) usePrefs.getState().setSidebarCollapsed(false);
        else useUi.getState().setMobileSidebarOpen(true);
        useUi.getState().requestSearchFocus();
      } else if (key === "o" && e.shiftKey) {
        e.preventDefault();
        navigate("/", { state: { fresh: true } });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isDesktop, navigate, pathname]);
}

/** "/" and "/c/:id" are the same page (a stream survives the hop), so they share one transition key. */
const transitionKey = (pathname: string) => (pathname === "/" || pathname.startsWith("/c/") ? "chat" : pathname);

/** Space changes slide a little in the direction of the tab you picked, and cross-fade. */
const spaceVariants: Variants = {
  enter: (dir: number) => ({ opacity: 0, x: dir * 28 }),
  center: { opacity: 1, x: 0, transition: { duration: 0.24, ease: EASE_OUT } },
  exit: (dir: number) => ({ opacity: 0, x: dir * -20, transition: { duration: 0.14, ease: "easeIn" } }),
};

/**
 * Layout: one app bar on top (brand · space switcher · workplace dock · account), the chat history as a slim
 * collapsible panel on the left of the Chat space only, pages full-width below.
 */
export function AppShell() {
  const isDesktop = useIsDesktop();
  const collapsed = usePrefs((s) => s.sidebarCollapsed);
  const mobileOpen = useUi((s) => s.mobileSidebarOpen);
  const setMobileOpen = useUi((s) => s.setMobileSidebarOpen);
  const setLastChatPath = useUi((s) => s.setLastChatPath);
  const location = useLocation();
  const outlet = useOutlet();
  const space = spaceIndex(location.pathname);
  const onChat = space === 0;
  useGlobalShortcuts(isDesktop);

  // Direction of travel between spaces (for the slide), derived during render from the previous space.
  const [travel, setTravel] = useState({ space, dir: 0 });
  if (travel.space !== space) setTravel({ space, dir: space > travel.space ? 1 : -1 });
  const dir = travel.space !== space ? (space > travel.space ? 1 : -1) : travel.dir;

  useEffect(() => {
    setMobileOpen(false);
  }, [location.key, setMobileOpen]);

  useEffect(() => {
    if (onChat) setLastChatPath(location.pathname);
  }, [onChat, location.pathname, setLastChatPath]);

  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden">
      <AppTopBar />
      <div className="flex min-h-0 flex-1">
        {isDesktop ? (
          <AnimatePresence initial={false}>
            {onChat && !collapsed && (
              <motion.aside
                key="history"
                aria-label="Chat history"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 272, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ type: "spring", stiffness: 420, damping: 40, mass: 0.8 }}
                className="shrink-0 overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground backdrop-blur-xl"
              >
                <div className="h-full w-[17rem]">
                  <HistoryPanel />
                </div>
              </motion.aside>
            )}
          </AnimatePresence>
        ) : (
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetContent
              side="left"
              showCloseButton={false}
              onOpenAutoFocus={focusSheetItself}
              className="w-[86vw] max-w-[20rem] gap-0 border-sidebar-border bg-sidebar backdrop-blur-xl p-0 pt-[env(safe-area-inset-top)] text-sidebar-foreground outline-none"
            >
              <SheetTitle className="sr-only">Chat history</SheetTitle>
              <SheetDescription className="sr-only">Search, open or start chats</SheetDescription>
              <HistoryPanel mobile />
            </SheetContent>
          </Sheet>
        )}
        <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          <Suspense
            fallback={
              <div className="grid flex-1 place-items-center" role="status" aria-label="Loading">
                <SphuraLogo size={40} state="thinking" />
              </div>
            }
          >
            <AnimatePresence mode="popLayout" initial={false} custom={dir}>
              <motion.div
                key={transitionKey(location.pathname)}
                custom={dir}
                variants={spaceVariants}
                initial="enter"
                animate="center"
                exit="exit"
                className="flex h-full min-h-0 w-full flex-1 flex-col"
              >
                {outlet}
              </motion.div>
            </AnimatePresence>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
