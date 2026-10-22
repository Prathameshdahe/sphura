import { Link, useLocation } from "react-router-dom";
import { PanelLeft, PanelLeftClose } from "lucide-react";
import { IconButton } from "@/components/icon-button";
import { SpaceTaskbar } from "@/components/layout/space-switcher";
import { UserMenu } from "@/components/layout/user-menu";
import { SphuraLogo } from "@/components/ui/sphura-logo";
import { useIsDesktop, useMediaQuery } from "@/hooks/use-media-query";
import { MOD } from "@/lib/platform";
import { spaceIndex } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { usePrefs } from "@/stores/prefs";
import { useUi } from "@/stores/ui";

/**
 * The app bar: history toggle + block-S brand on the left, the floating taskbar (every space + New chat) in the
 * centre, the account avatar on the right. Phones keep the taskbar between the two, icons only.
 */
export function AppTopBar({ className }: { className?: string }) {
  const { pathname } = useLocation();
  const isDesktop = useIsDesktop();
  const centred = useMediaQuery("(min-width: 640px)");
  const roomy = useMediaQuery("(min-width: 1024px)");
  const allLabels = useMediaQuery("(min-width: 1180px)");
  const onChat = spaceIndex(pathname) === 0;
  const collapsed = usePrefs((s) => s.sidebarCollapsed);
  const setCollapsed = usePrefs((s) => s.setSidebarCollapsed);
  const setMobileOpen = useUi((s) => s.setMobileSidebarOpen);

  const historyOpen = isDesktop && !collapsed;
  const toggleHistory = () => (isDesktop ? setCollapsed(!collapsed) : setMobileOpen(true));
  const labels = allLabels ? "all" : centred ? "active" : "none";

  return (
    <header
      className={cn(
        "pt-safe relative z-30 flex h-16 shrink-0 items-center gap-1.5 bg-background/80 px-2 backdrop-blur-md sm:px-4",
        className,
      )}
    >
      <div className="flex shrink-0 items-center gap-0.5">
        {onChat && (
          <IconButton
            label={historyOpen ? "Hide chat history" : "Chat history"}
            side="bottom"
            shortcut={`${MOD} K`}
            onClick={toggleHistory}
            aria-expanded={historyOpen || undefined}
          >
            {historyOpen ? <PanelLeftClose /> : <PanelLeft />}
          </IconButton>
        )}
        <Link
          to="/"
          state={{ fresh: true }}
          aria-label="Sphura, new chat"
          className="flex items-center rounded-lg px-1 py-1 text-foreground focus-visible:outline-2"
        >
          <SphuraLogo size={26} withWordmark={roomy} intro />
        </Link>
      </div>

      {centred ? (
        <div className="pointer-events-none absolute inset-x-0 top-[env(safe-area-inset-top)] flex h-16 items-center justify-center">
          <SpaceTaskbar labels={labels} newChatLabel={roomy} className="pointer-events-auto" />
        </div>
      ) : (
        <div className="flex min-w-0 flex-1 justify-center">
          <SpaceTaskbar labels="none" newChatLabel={false} />
        </div>
      )}

      <div className="relative ml-auto flex shrink-0 items-center">
        <UserMenu />
      </div>
    </header>
  );
}
