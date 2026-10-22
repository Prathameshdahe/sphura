import type { ComponentProps, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface IconButtonProps extends Omit<ComponentProps<typeof Button>, "children" | "aria-label"> {
  label: string;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  shortcut?: string;
}

/** Icon-only button with an aria-label and a matching tooltip. */
export function IconButton({ label, children, side = "top", shortcut, className, variant = "ghost", size = "icon-sm", ...props }: IconButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button aria-label={label} variant={variant} size={size} className={cn("text-muted-foreground hover:text-foreground", className)} {...props}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side={side}>
        {label}
        {shortcut && <kbd className="ml-1.5 rounded bg-background/20 px-1 font-mono text-[10px]">{shortcut}</kbd>}
      </TooltipContent>
    </Tooltip>
  );
}
