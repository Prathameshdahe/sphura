import type { ComponentProps, ReactNode, Ref } from "react";
import { cn } from "@/lib/utils";

interface PageProps extends Omit<ComponentProps<"div">, "title"> {
  /** `narrow` = the chat column (max-w-3xl); `wide` = dashboards (max-w-6xl). */
  width?: "narrow" | "wide";
  /** Usually a <PageHeader>. */
  header?: ReactNode;
  /** The scroll container (for sticky sub-navs and intersection observers). */
  scrollRef?: Ref<HTMLDivElement>;
  contentClassName?: string;
}

/** Studio page frame: one scroll container under the app bar, centred column with the 8-px rhythm. */
export function Page({ width = "wide", header, scrollRef, contentClassName, className, children, ...rest }: PageProps) {
  return (
    <div className={cn("relative flex h-full min-h-0 flex-col", className)} {...rest}>
      <div ref={scrollRef} className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
        <div className={cn("mx-auto w-full px-4 pt-4 pb-14 sm:px-6 sm:pt-6", width === "narrow" ? "max-w-3xl" : "max-w-6xl", contentClassName)}>
          {header}
          {children}
        </div>
      </div>
    </div>
  );
}
