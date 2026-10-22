import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { formatDay, type MoneyFormatter } from "@/lib/feature-api/finance";
import type { FinanceReport } from "@/lib/feature-types";

/** Largest transactions; sign + arrow carry direction, so colour is never the only cue. */
export function TransactionsTable({ rows, money }: { rows: FinanceReport["topTransactions"]; money: MoneyFormatter }) {
  return (
    <div className="scrollbar-thin relative overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Largest transactions</caption>
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th scope="col" className="hidden py-2 pr-3 text-left font-medium whitespace-nowrap sm:table-cell">Date</th>
            <th scope="col" className="py-2 pr-3 text-left font-medium">Description</th>
            <th scope="col" className="hidden py-2 pr-3 text-left font-medium sm:table-cell">Category</th>
            <th scope="col" className="py-2 text-right font-medium">Amount</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t, i) => {
            const credit = t.amount >= 0;
            return (
              <tr key={`${t.date}-${i}`} className="border-b border-border/60 last:border-0">
                <td className="hidden py-2.5 pr-3 align-top text-xs whitespace-nowrap text-muted-foreground tabular-nums sm:table-cell">{formatDay(t.date)}</td>
                <td className="w-full max-w-0 py-2.5 pr-3 align-top sm:max-w-[16rem]">
                  <span className="line-clamp-2 break-words" title={t.description}>
                    {t.description || "—"}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted-foreground sm:hidden">
                    {formatDay(t.date)} · {t.category || "Uncategorised"}
                  </span>
                </td>
                <td className="hidden py-2.5 pr-3 align-top sm:table-cell">
                  <span className="inline-block max-w-[10rem] truncate rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {t.category || "Uncategorised"}
                  </span>
                </td>
                <td className="py-2.5 text-right align-top whitespace-nowrap">
                  <span className="inline-flex items-center gap-1 font-mono font-medium tabular-nums">
                    {credit ? (
                      <ArrowDownLeft className="size-3.5 text-success" aria-label="money in" />
                    ) : (
                      <ArrowUpRight className="size-3.5 text-danger" aria-label="money out" />
                    )}
                    {credit ? "+" : "−"}
                    {money.full(Math.abs(t.amount))}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
