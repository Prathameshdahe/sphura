import { motion } from "framer-motion";
import { Minus, Plus, Star, TrendingDown, TrendingUp, X } from "lucide-react";
import { Panel, PanelHeader } from "@/components/metrics/section";
import { Stagger, StaggerItem } from "@/components/motion";
import { Skeleton } from "@/components/ui/skeleton";
import { SUGGESTED_SYMBOLS, formatPrice, useQuotes, useWatchlist, type WatchItem } from "@/lib/feature-api/market";
import { press } from "@/lib/motion";
import { cn } from "@/lib/utils";

interface WatchlistProps {
  selected: string | null;
  onSelect: (item: WatchItem) => void;
}

/** Symbols kept in this browser (localStorage) with live mini quotes; suggestions when empty. */
export function Watchlist({ selected, onSelect }: WatchlistProps) {
  const items = useWatchlist((s) => s.items);
  const add = useWatchlist((s) => s.add);
  const remove = useWatchlist((s) => s.remove);
  const quotes = useQuotes(items.map((w) => w.symbol));
  const suggestions = SUGGESTED_SYMBOLS.filter((s) => !items.some((w) => w.symbol === s.symbol));

  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            <Star className="size-4 text-muted-foreground" strokeWidth={1.75} aria-hidden /> Watchlist
          </span>
        }
        description={items.length ? `${items.length} symbol${items.length === 1 ? "" : "s"} · saved in this browser` : "Saved in this browser — nothing leaves your device."}
      />
      <div className="px-2 pt-2 pb-3">
        {items.length > 0 ? (
          <Stagger className="space-y-0.5" aria-label="Watched symbols">
            {items.map((w, i) => {
              const q = quotes[i];
              const data = q?.data;
              const dir = data ? (data.change > 0 ? "up" : data.change < 0 ? "down" : "flat") : "flat";
              const active = w.symbol === selected;
              return (
                <StaggerItem key={w.symbol} className="group/row relative">
                  <button
                    type="button"
                    onClick={() => onSelect(w)}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg py-2 pr-9 pl-2.5 text-left transition-[background-color,transform] duration-150 focus-visible:outline-2 active:scale-[0.99] motion-reduce:active:scale-100",
                      active ? "bg-accent text-accent-foreground" : "hover:bg-muted",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{w.name || w.symbol}</span>
                      <span className="block truncate font-mono text-[11px] text-muted-foreground">{w.symbol}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      {data ? (
                        <>
                          <span className="block text-sm font-medium tabular-nums">{formatPrice(data.price, data.currency)}</span>
                          <span
                            className={cn(
                              "flex items-center justify-end gap-0.5 text-[11px] font-medium tabular-nums",
                              dir === "up" ? "text-success" : dir === "down" ? "text-danger" : "text-muted-foreground",
                            )}
                          >
                            {dir === "up" ? (
                              <TrendingUp className="size-3" aria-hidden />
                            ) : dir === "down" ? (
                              <TrendingDown className="size-3" aria-hidden />
                            ) : (
                              <Minus className="size-3" aria-hidden />
                            )}
                            <span className="sr-only">{dir === "up" ? "Up" : dir === "down" ? "Down" : "Unchanged"}</span>
                            {Math.abs(data.changePercent).toFixed(2)}%
                          </span>
                        </>
                      ) : q?.isError ? (
                        <span className="text-[11px] text-muted-foreground">no quote</span>
                      ) : (
                        <Skeleton className="h-8 w-16" />
                      )}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove ${w.symbol} from watchlist`}
                    onClick={() => remove(w.symbol)}
                    className="absolute top-1/2 right-1.5 grid size-6 -translate-y-1/2 place-items-center rounded-md text-muted-foreground opacity-100 transition-opacity hover:bg-background/70 hover:text-foreground focus-visible:opacity-100 md:opacity-0 md:group-hover/row:opacity-100"
                  >
                    <X className="size-3.5" />
                  </button>
                </StaggerItem>
              );
            })}
          </Stagger>
        ) : (
          <p className="px-2.5 py-3 text-sm text-muted-foreground">Star a quote to keep it here.</p>
        )}
        {suggestions.length > 0 && (
          <div className={cn("px-2.5", items.length > 0 && "mt-3 border-t pt-3")}>
            <p className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Popular</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {suggestions.slice(0, 6).map((s) => (
                <motion.button
                  key={s.symbol}
                  type="button"
                  onClick={() => {
                    add(s);
                    onSelect(s);
                  }}
                  {...press}
                  className="inline-flex h-7 items-center gap-1 rounded-full border bg-card px-2.5 text-xs text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-2"
                >
                  <Plus className="size-3" aria-hidden /> {s.name}
                </motion.button>
              ))}
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
