import { useMemo } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Building2,
  CalendarRange,
  Coins,
  Landmark,
  Lightbulb,
  MessageSquareText,
  RefreshCw,
  Percent,
  PiggyBank,
  Scale,
  TrendingUp,
  TriangleAlert,
  Wallet,
} from "lucide-react";
import { KpiCard } from "@/components/metrics/kpi-card";
import { Panel, PanelHeader } from "@/components/metrics/section";
import { Stagger, StaggerItem } from "@/components/motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDay, moneyFormatter } from "@/lib/feature-api/finance";
import type { FinanceReport } from "@/lib/feature-types";
import { CategoryDonut } from "./category-donut";
import { MonthlyChart } from "./monthly-chart";
import { RatioCards } from "./ratio-cards";
import { TransactionsTable } from "./transactions-table";

const KIND_LABEL: Record<FinanceReport["kind"], string> = {
  bank_statement: "Bank statement",
  balance_sheet: "Balance sheet",
  table: "Table",
};

function periodDays(p: { start: string; end: string }): number | null {
  const a = Date.parse(p.start);
  const b = Date.parse(p.end);
  return Number.isFinite(a) && Number.isFinite(b) ? Math.round((b - a) / 86_400_000) + 1 : null;
}

interface FinanceDashboardProps {
  report: FinanceReport;
  refreshing: boolean;
  onRefresh: () => void;
  onDiscuss: (() => void) | null;
}

/** Deterministic analytics for one statement + the (optional) LLM insights. */
const pct = (r: number | null | undefined) =>
  r == null || !Number.isFinite(r) ? "—" : `${(r * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;

/** Small P&L summary (revenue, net profit, net margin, revenue growth, ROE) when the file holds a P&L statement. */
function ProfitLossCard({
  pnl,
  compact,
  full,
  unit,
}: {
  pnl: NonNullable<FinanceReport["profitLoss"]>;
  compact: (n: number) => string;
  full: (n: number | null | undefined) => string | undefined;
  unit: string | null;
}) {
  const scaled = (n: number) => `${compact(n)}${unit ? ` ${unit}` : ""}`;
  const growth = pnl.revenueGrowth;
  return (
    <Panel>
      <PanelHeader
        title="Profit and loss"
        description={[pnl.period, pnl.previousPeriod ? `vs ${pnl.previousPeriod}` : null, unit ? `amounts in ${unit}` : null]
          .filter(Boolean)
          .join(" · ") || undefined}
      />
      <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
        <KpiCard label="Revenue" icon={TrendingUp} value={pnl.revenue ?? "—"} format={scaled} hint={full(pnl.revenue)} />
        <KpiCard label="Net profit" icon={PiggyBank} accent value={pnl.netProfit ?? "—"} format={scaled} hint={full(pnl.netProfit)} />
        <KpiCard label="Net margin" icon={Percent} value={pct(pnl.netMargin)} />
        <KpiCard
          label="Revenue growth"
          icon={TrendingUp}
          value={pct(growth)}
          hint={pnl.previousPeriod ? `vs ${pnl.previousPeriod}` : "vs the previous year"}
        />
        <KpiCard label="Return on equity" icon={Scale} value={pct(pnl.returnOnEquity)} />
      </div>
    </Panel>
  );
}

export function FinanceDashboard({ report, refreshing, onRefresh, onDiscuss }: FinanceDashboardProps) {
  const money = useMemo(() => moneyFormatter(report.currency), [report.currency]);
  const t = report.totals;
  const bs = report.balanceSheet;
  const days = report.period ? periodDays(report.period) : null;
  const isSheet = report.kind === "balance_sheet";

  const period = report.period ? (
    <span className="block text-base leading-snug whitespace-normal">
      {formatDay(report.period.start)} <span className="text-muted-foreground">–</span> {formatDay(report.period.end)}
    </span>
  ) : (
    "—"
  );
  const compact = (n: number) => money.compact(n);
  const hintFull = (n: number | null | undefined) => (n != null ? money.full(n) : undefined);
  const currencyHint = money.currency ? `${money.currency} (from the file)` : "currency not detected";

  return (
    <Stagger key={report.docId} className="space-y-4">
      <StaggerItem className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate font-brand text-2xl font-normal tracking-[-0.01em]" title={report.filename}>
              {report.filename}
            </h2>
            <Badge variant="outline" className="text-muted-foreground">
              {KIND_LABEL[report.kind]}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">Computed with pandas — every number below is deterministic and reproducible.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
            <RefreshCw className={refreshing ? "animate-spin" : undefined} /> Re-analyse
          </Button>
          <Button size="sm" onClick={onDiscuss ?? undefined} disabled={!onDiscuss}>
            <MessageSquareText /> Discuss in chat
          </Button>
        </div>
      </StaggerItem>

      {isSheet && bs ? (
        <StaggerItem className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard label="Total assets" icon={Building2} value={bs.totalAssets ?? "—"} format={compact} hint={hintFull(bs.totalAssets) ?? currencyHint} />
          <KpiCard label="Total liabilities" icon={Landmark} value={bs.totalLiabilities ?? "—"} format={compact} hint={hintFull(bs.totalLiabilities)} />
          <KpiCard label="Equity" icon={Scale} accent value={bs.equity ?? "—"} format={compact} hint={hintFull(bs.equity)} />
          {report.period ? (
            <KpiCard label="Period" icon={CalendarRange} value={period} hint={days ? `${days.toLocaleString()} days` : undefined} />
          ) : (
            <KpiCard label="Currency" icon={Coins} value={money.currency ?? "—"} hint={currencyHint} />
          )}
        </StaggerItem>
      ) : t || report.period ? (
        <StaggerItem className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard
            label="Inflow"
            icon={ArrowDownLeft}
            value={t ? Math.abs(t.inflow) : "—"}
            format={compact}
            hint={t ? `${money.full(Math.abs(t.inflow))} · ${currencyHint}` : currencyHint}
          />
          <KpiCard label="Outflow" icon={ArrowUpRight} value={t ? Math.abs(t.outflow) : "—"} format={compact} hint={t ? money.full(Math.abs(t.outflow)) : undefined} />
          <KpiCard
            label="Net"
            icon={Wallet}
            accent
            value={t ? t.net : "—"}
            format={compact}
            hint={t ? money.full(t.net) : undefined}
            delta={
              t && t.inflow !== 0
                ? {
                    text: `${t.net >= 0 ? "saved" : "overspent"} ${Math.abs((t.net / Math.abs(t.inflow)) * 100).toFixed(0)}% of inflow`,
                    direction: t.net > 0 ? "up" : t.net < 0 ? "down" : "flat",
                  }
                : null
            }
          />
          <KpiCard label="Period" icon={CalendarRange} value={period} hint={days ? `${days.toLocaleString()} days` : undefined} />
        </StaggerItem>
      ) : null}

      {isSheet && bs && (
        <StaggerItem>
          <RatioCards sheet={bs} />
        </StaggerItem>
      )}

      {report.profitLoss && (
        <StaggerItem>
          <ProfitLossCard pnl={report.profitLoss} compact={compact} full={hintFull} unit={report.amountUnit ?? null} />
        </StaggerItem>
      )}

      {(report.byMonth.length > 0 || report.byCategory.length > 0) && (
        <StaggerItem className="grid gap-4 lg:grid-cols-5">
          {report.byMonth.length > 0 && (
            <Panel className={report.byCategory.length > 0 ? "lg:col-span-3" : "lg:col-span-5"}>
              <PanelHeader title="Cash flow by month" description="Inflow and outflow per month, with the net line." />
              <div className="px-2 pt-4 pb-3 sm:px-4">
                <MonthlyChart data={report.byMonth} money={money} />
              </div>
            </Panel>
          )}
          {report.byCategory.length > 0 && (
            <Panel className={report.byMonth.length > 0 ? "lg:col-span-2" : "lg:col-span-5"}>
              <PanelHeader
                title={isSheet ? "Composition" : report.kind === "table" ? "By category" : "Where the money goes"}
                description={
                  isSheet ? "Assets vs the liabilities and equity that fund them; each side is 100%." : report.kind === "table" ? "Column totals per category (absolute values)." : "Spending by category."
                }
              />
              <div className="p-4 sm:p-5">
                <CategoryDonut
                  data={report.byCategory}
                  money={money}
                  centerLabel={report.kind === "bank_statement" ? "spent" : "total"}
                  balance={isSheet}
                />
              </div>
            </Panel>
          )}
        </StaggerItem>
      )}

      {(report.insights.length > 0 || report.warnings.length > 0) && (
        <StaggerItem className="grid gap-4 lg:grid-cols-2">
          <Panel className={report.warnings.length === 0 ? "lg:col-span-2" : undefined}>
            <PanelHeader title="Insights" description="What stands out in this file." />
            <div className="p-4 pt-3 sm:p-5 sm:pt-3">
              {report.insights.length > 0 ? (
                <ul className="space-y-2.5">
                  {report.insights.map((s, i) => (
                    <li key={i} className="flex gap-2.5 text-sm">
                      <Lightbulb className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden />
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No narrative insights for this file — the numbers above are complete.</p>
              )}
            </div>
          </Panel>
          {report.warnings.length > 0 && (
            <Panel className="border-warning/35 bg-warning/5">
              <PanelHeader
                title={
                  <span className="flex items-center gap-2">
                    <TriangleAlert className="size-4 text-warning" aria-hidden /> Things to watch
                  </span>
                }
              />
              <ul className="space-y-2 p-4 pt-3 sm:p-5 sm:pt-3">
                {report.warnings.map((w, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className="mt-2 size-1.5 shrink-0 rounded-full bg-warning" aria-hidden />
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </StaggerItem>
      )}

      {report.topTransactions.length > 0 && (
        <StaggerItem>
          <Panel>
            <PanelHeader title="Largest transactions" description={`Top ${report.topTransactions.length} by amount.`} />
            <div className="px-4 pt-2 pb-3 sm:px-5">
              <TransactionsTable rows={report.topTransactions} money={money} />
            </div>
          </Panel>
        </StaggerItem>
      )}
    </Stagger>
  );
}
