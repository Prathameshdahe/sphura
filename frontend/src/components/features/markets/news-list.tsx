import { ArrowUpRight, Minus, Newspaper, TrendingDown, TrendingUp, type LucideIcon } from "lucide-react";
import { Panel, PanelHeader } from "@/components/metrics/section";
import { Stagger, StaggerItem } from "@/components/motion";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useMarketNews } from "@/lib/feature-api/market";
import type { NewsItem, SentimentLabel } from "@/lib/feature-types";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

const SENTIMENT: Record<SentimentLabel, { label: string; icon: LucideIcon; cls: string }> = {
  positive: { label: "Positive", icon: TrendingUp, cls: "bg-success/12 text-success" },
  neutral: { label: "Neutral", icon: Minus, cls: "bg-muted text-muted-foreground" },
  negative: { label: "Negative", icon: TrendingDown, cls: "bg-danger/12 text-danger" },
};

/** Headline sentiment from the fine-tuned DistilBERT (FINANCE_PLAN §2): icon + word, never colour alone. */
export function SentimentChip({ sentiment }: { sentiment: NewsItem["sentiment"] }) {
  const s = SENTIMENT[sentiment.label] ?? SENTIMENT.neutral;
  const Icon = s.icon;
  return (
    <span
      className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-1.5 text-[10.5px] font-semibold", s.cls)}
      title={`${s.label} · ${Math.round(sentiment.score * 100)}% confidence`}
    >
      <Icon className="size-3" aria-hidden />
      {s.label}
      <span className="font-medium opacity-75 tabular-nums">{Math.round(sentiment.score * 100)}%</span>
    </span>
  );
}

/** Finance news for the selected name, each headline labelled by the sentiment model. */
export function NewsList({ query }: { query: string | null }) {
  const news = useMarketNews(query);
  const items = news.data ?? [];
  const counts = items.reduce(
    (acc, n) => {
      acc[n.sentiment.label] = (acc[n.sentiment.label] ?? 0) + 1;
      return acc;
    },
    {} as Partial<Record<SentimentLabel, number>>,
  );
  const mood = items.length
    ? (["positive", "neutral", "negative"] as SentimentLabel[]).map((k) => `${counts[k] ?? 0} ${SENTIMENT[k].label.toLowerCase()}`).join(" · ")
    : null;

  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            <Newspaper className="size-4 text-muted-foreground" strokeWidth={1.75} aria-hidden /> News{query ? ` · ${query}` : ""}
          </span>
        }
        description={mood ?? "Finance-only web search; each headline is labelled by Sphura's sentiment model."}
      />
      <div className="px-4 pt-3 pb-4 sm:px-5">
        {!query ? (
          <p className="py-6 text-center text-sm text-muted-foreground">Pick a symbol to see its news.</p>
        ) : news.isPending ? (
          <ul className="space-y-3" aria-busy="true" aria-label="Loading news">
            {[0, 1, 2, 3].map((i) => (
              <li key={i} className="space-y-2">
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-3 w-1/3" />
              </li>
            ))}
          </ul>
        ) : news.isError ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{errorMessage(news.error, "News is unavailable right now.")}</p>
        ) : items.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No recent finance news found for {query}.</p>
        ) : (
          <Stagger className="divide-y" aria-label="News">
            {items.map((n, i) => (
              <StaggerItem key={`${n.url}-${i}`} className="py-3 first:pt-0 last:pb-0">
                <article>
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <a
                        href={n.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group inline text-sm leading-snug font-medium text-foreground hover:underline"
                      >
                        {n.title}
                        <ArrowUpRight className="ml-1 inline size-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" aria-hidden />
                      </a>
                      {n.snippet && <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{n.snippet}</p>}
                      <p className="mt-1.5 text-[11px] text-muted-foreground">
                        {n.domain}
                        {n.publishedAt ? ` · ${formatRelative(n.publishedAt)}` : ""}
                      </p>
                    </div>
                    <SentimentChip sentiment={n.sentiment} />
                  </div>
                </article>
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </div>
    </Panel>
  );
}
