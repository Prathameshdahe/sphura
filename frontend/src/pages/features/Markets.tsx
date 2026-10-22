import { useCallback, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChartCandlestick, MessageSquareText } from "lucide-react";
import { NewsList } from "@/components/features/markets/news-list";
import { QuoteCard } from "@/components/features/markets/quote-card";
import { SymbolSearch } from "@/components/features/markets/symbol-search";
import { Watchlist } from "@/components/features/markets/watchlist";
import { Page } from "@/components/layout/page";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/metrics/section";
import { Button } from "@/components/ui/button";
import { useQuote, useWatchlist, type WatchItem } from "@/lib/feature-api/market";
import type { NewChatState } from "@/lib/feature-types";
import { glyph } from "@/components/icons/glyphs";

const askPrompt = (symbol: string, name: string) =>
  `What's the latest on ${name !== symbol ? `${name} (${symbol})` : symbol}? Give me the current quote, the recent trend and the news, and explain what it means for a beginner.`;

/** Markets: quote search → price card with sparkline and period toggle, news with sentiment, browser-side watchlist. */
export default function Markets() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const watchlist = useWatchlist((s) => s.items);
  const symbol = params.get("symbol")?.trim().toUpperCase() || watchlist[0]?.symbol || null;
  const nameHint = params.get("name") || watchlist.find((w) => w.symbol === symbol)?.name || null;
  const quote = useQuote(symbol);
  const newsQuery = symbol ? quote.data?.name || nameHint || symbol : null;

  useEffect(() => {
    document.title = symbol ? `${symbol} · Markets · Sphura` : "Markets · Sphura";
    return () => {
      document.title = "Sphura";
    };
  }, [symbol]);

  const select = useCallback(
    (item: WatchItem) => {
      setParams(item.name && item.name !== item.symbol ? { symbol: item.symbol, name: item.name } : { symbol: item.symbol });
    },
    [setParams],
  );

  const ask = (s: string, name: string) =>
    navigate("/", { state: { fresh: true, prompt: askPrompt(s, name) } satisfies NewChatState });

  return (
    <Page
      header={
        <PageHeader
          icon={ChartCandlestick}
          title="Markets"
          subtitle="Delayed quotes, the trend and finance news labelled by Sphura's sentiment model — educational, never advice."
          action={
            symbol ? (
              <Button variant="outline" onClick={() => ask(symbol, quote.data?.name || nameHint || symbol)}>
                <MessageSquareText /> Ask about {symbol}
              </Button>
            ) : null
          }
        />
      }
    >
      <SymbolSearch autoFocus={!symbol} onPick={(m) => select({ symbol: m.symbol, name: m.name })} />

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
        <div className="min-w-0 space-y-4">
          {symbol ? (
            <>
              <QuoteCard key={symbol} symbol={symbol} nameHint={nameHint} onAsk={ask} />
              <NewsList query={newsQuery} />
            </>
          ) : (
            <EmptyState icon={glyph("candles")} title="Look up a stock, fund or index">
              Search by name or ticker. Indian names resolve to NSE (<span className="font-mono">.NS</span>); global tickers work too.
              Quotes come from yfinance and are delayed.
            </EmptyState>
          )}
        </div>
        <div className="min-w-0 lg:sticky lg:top-2">
          <Watchlist selected={symbol} onSelect={select} />
        </div>
      </div>
    </Page>
  );
}
