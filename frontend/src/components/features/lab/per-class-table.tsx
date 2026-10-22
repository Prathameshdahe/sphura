import { int, pct } from "@/components/metrics/fmt";
import type { PerClassRow } from "@/lib/feature-types";
import { labelMeta } from "@/lib/intents";
import { cn } from "@/lib/utils";

function Score({ value, best }: { value: number; best?: boolean }) {
  return <span className={cn("tabular-nums", best ? "font-semibold" : "text-foreground/85")}>{pct(value, 1)}</span>;
}

/** Precision / recall / F1 per class with an inline F1 bar. */
export function PerClassTable({ rows }: { rows: PerClassRow[] }) {
  if (rows.length === 0) return <p className="py-8 text-center text-sm text-muted-foreground">No per-class scores in this report.</p>;
  const bestF1 = Math.max(...rows.map((r) => r.f1));
  return (
    <div className="scrollbar-thin relative overflow-x-auto">
      <table className="w-full min-w-[22rem] text-sm">
        <caption className="sr-only">Per-class precision, recall, F1 and support on the test set</caption>
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th scope="col" className="sticky left-0 z-[1] bg-card py-2 pr-2 text-left font-medium">Class</th>
            <th scope="col" className="px-2 py-2 text-right font-medium">Precision</th>
            <th scope="col" className="px-2 py-2 text-right font-medium">Recall</th>
            <th scope="col" className="px-2 py-2 text-left font-medium">F1</th>
            <th scope="col" className="py-2 pl-2 text-right font-medium">Support</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const { icon: Icon, title } = labelMeta(r.label);
            return (
              <tr key={r.label} className="border-b border-border/60 last:border-0">
                <th scope="row" className="sticky left-0 z-[1] bg-card py-2.5 pr-2 text-left font-medium whitespace-nowrap">
                  <span className="flex items-center gap-2">
                    <Icon className="size-3.5 text-muted-foreground" aria-hidden />
                    {title}
                  </span>
                </th>
                <td className="px-2 py-2.5 text-right">
                  <Score value={r.precision} />
                </td>
                <td className="px-2 py-2.5 text-right">
                  <Score value={r.recall} />
                </td>
                <td className="px-2 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-14 overflow-hidden rounded-full bg-muted sm:w-20" aria-hidden>
                      <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(2, r.f1 * 100)}%` }} />
                    </div>
                    <Score value={r.f1} best={r.f1 === bestF1} />
                  </div>
                </td>
                <td className="py-2.5 pl-2 text-right text-muted-foreground tabular-nums">{int(r.support)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
