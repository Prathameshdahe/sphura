import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, Clock, MessageSquareText, Minus, Star } from "lucide-react";
import { Sparkline } from "@/components/features/markets/sparkline";
import { Panel } from "@/components/metrics/section";
import { CountUp } from "@/components/motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { formatChange, formatPrice, useHistory, useQuote, useWatchlist } from "@/lib/feature-api/market";
import type { HistoryPeriod } from "@/lib/feature-types";
import { formatRelative } from "@/lib/format";
import { chipSpring } from "@/lib/motion";
import { cn } from "@/lib/utils";

interface QuoteCardProps {
  symbol: string;
  /** Name from the search match / watchlist, shown until the quote arrives. */
  nameHint?: string | null;
  onAsk: (symbol: string, name: string) => void;
}

/** Quote header (price count-up, coloured change with arrow + sign), sparkline with period toggle, watch + ask actions. */
export function QuoteCard({ symbol, nameHint, onAsk }: QuoteCardProps) {
  const quote = useQuote(symbol);
  const [period, setPeriod] = useState<HistoryPeriod>("3mo");
  const history = useHistory(symbol, period);
  const watching = useWatchlist((s) => s.items.some((w) => w.symbol === symbol));
  const toggle = useWatchlist((s) => s.toggle);
  const q = quote.data;
  const name = q?.name || nameHint || symbol;
  const dir = q ? (q.change > 0 ? "up" : q.change < 0 ? "down" : "flat") : "flat";
  const Arrow = dir === "up" ? ArrowUpRight : dir === "down" ? ArrowDownRight : Minus;

  return (
    <Panel className="p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate font-brand text-2xl leading-tight font-normal tracking-[-0.01em] sm:text-[1.7rem]">{name}</h2>
            <Badge variant="outline" className="font-mono text-muted-foreground">
              {symbol}
            </Badge>
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <Clock className="size-3" aria-hidden />
            {q ? (
              <>
                as of {formatRelative(q.asOf)} · delayed · {q.source}
              </>
            ) : quote.isError ? (
              <span className="text-destructive">{errorMessage(quote.error)}</span>
            ) : (
              "Fetching the quote…"
            )}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant={watching ? "secondary" : "outline"}
            size="sm"
            aria-pressed={watching}
            onClick={() => toggle({ symbol, name })}
          >
            <Star className={cn(watching && "fill-current text-warning")} /> {watching ? "Watching" : "Watch"}
          </Button>
          <Button size="sm" onClick={() => onAsk(symbol, name)}>
            <MessageSquareText /> Ask Sphura
          </Button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-x-4 gap-y-2">
        {q ? (
          <>
            <div className="font-brand text-4xl leading-none font-normal tracking-[-0.015em] tabular-nums sm:text-5xl">
              <CountUp value={q.price} format={(n) => formatPrice(n, q.currency)} />
            </div>
            <motion.span
              key={`${q.change}-${q.changePercent}`}
              {...chipSpring}
              className={cn(
                "inline-flex h-7 items-center gap-1 rounded-full px-2.5 text-sm font-semibold tabular-nums",
                dir === "up" ? "bg-success/12 text-success" : dir === "down" ? "bg-danger/12 text-danger" : "bg-muted text-muted-foreground",
              )}
            >
              <Arrow className="size-3.5" aria-hidden />
              {formatChange(q.change, q.changePercent)}
            </motion.span>
            {(q.dayLow != null || q.dayHigh != null) && (
              <span className="text-xs text-muted-foreground">
                Day {q.dayLow != null ? formatPrice(q.dayLow, q.currency) : "–"} – {q.dayHigh != null ? formatPrice(q.dayHigh, q.currency) : "–"}
              </span>
            )}
          </>
        ) : quote.isPending ? (
          <>
            <Skeleton className="h-10 w-40" />
            <Skeleton className="h-7 w-32 rounded-full" />
          </>
        ) : (
          <p className="text-sm text-muted-foreground">No quote for this symbol. Try the NSE form (e.g. TCS.NS) or a global ticker.</p>
        )}
      </div>

      <Sparkline
        className="mt-5"
        history={history.data}
        loading={history.isFetching}
        period={period}
        onPeriodChange={setPeriod}
        currency={q?.currency}
      />
    </Panel>
  );
}
