import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useTheme } from "next-themes";
import { Brain, Laptop, LogOut, Moon, ShieldCheck, Sun } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { initials } from "@/lib/format";
import { useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { abortAllStreams } from "@/stores/chat-store";

export function UserAvatar({ name, email, className }: { name?: string; email?: string; className?: string }) {
  return (
    <span
      className={cn(
        "grid size-8 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold tracking-wide text-primary-foreground",
        className,
      )}
      aria-hidden
    >
      {initials(name, email)}
    </span>
  );
}

export function AdminBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1 rounded-full border border-brand/25 bg-accent px-1.5 text-[10.5px] font-semibold text-brand",
        className,
      )}
    >
      <ShieldCheck className="size-3" aria-hidden /> Admin
    </span>
  );
}

/** Top-right account button: avatar → theme, memory, sign out (plus an Admin badge for admins). */
export function UserMenu() {
  const { data: user } = useMe();
  const { theme, setTheme } = useTheme();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const logout = async () => {
    abortAllStreams();
    try {
      await api.logout();
    } catch {
      /* cookie may already be gone — still leave */
    }
    qc.clear();
    navigate("/login", { replace: true });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <motion.button
          type="button"
          aria-label={`Account: ${user?.name || user?.email || "you"}`}
          whileTap={{ scale: 0.92 }}
          className="relative grid size-9 shrink-0 place-items-center rounded-full ring-offset-2 ring-offset-background transition-shadow hover:ring-2 hover:ring-border focus-visible:outline-2 data-[state=open]:ring-2 data-[state=open]:ring-ring/60"
        >
          <UserAvatar name={user?.name} email={user?.email} />
          {user?.isAdmin && (
            <span className="absolute -right-0.5 -bottom-0.5 grid size-4 place-items-center rounded-full border-2 border-background bg-card text-brand" aria-hidden>
              <ShieldCheck className="size-2.5" />
            </span>
          )}
        </motion.button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="bottom" align="end" sideOffset={8} className="w-64">
        <DropdownMenuLabel className="flex items-center gap-2.5 py-2 font-normal">
          <UserAvatar name={user?.name} email={user?.email} className="size-9" />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5">
              <span className="truncate text-sm font-medium text-foreground">{user?.name || "You"}</span>
              {user?.isAdmin && <AdminBadge />}
            </span>
            <span className="block truncate text-xs text-muted-foreground">{user?.email}</span>
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme ?? "light"} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light">
            <Sun /> Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon /> Dark
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Laptop /> System
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/memory">
            <Brain /> Memory &amp; privacy
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void logout()}>
          <LogOut /> Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
