import { pct } from "@/components/metrics/fmt";
import { labelMeta } from "@/lib/intents";

interface ConfusionMatrixProps {
  labels: string[];
  /** rows = true label, cols = predicted, same order as `labels`. */
  matrix: number[][];
}

/**
 * Accessible heatmap: a real <table> whose cell tint encodes the share of the true-label row.
 * Diagonal (correct) cells use the success green, misclassifications the danger red, so errors stand out at a glance.
 */
export function ConfusionMatrix({ labels, matrix }: ConfusionMatrixProps) {
  const rowSums = matrix.map((r) => r.reduce((a, b) => a + b, 0));
  if (labels.length === 0 || matrix.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No confusion matrix in this report.</p>;
  }
  return (
    <div className="scrollbar-thin relative overflow-x-auto">
      <table className="w-full min-w-[19rem] border-separate border-spacing-1 text-xs">
        <caption className="sr-only">
          Confusion matrix on the held-out test set. Rows are the true label, columns the predicted label; each cell shows the
          number of test examples and its share of the row.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="sticky left-0 z-[1] bg-card px-1 pb-1 text-left align-bottom text-[10px] font-medium text-muted-foreground">
              <span className="block leading-tight">true ↓</span>
              <span className="block leading-tight">pred →</span>
            </th>
            {labels.map((l) => {
              const { icon: Icon, title } = labelMeta(l);
              return (
                <th key={l} scope="col" className="px-0.5 pb-1 text-center align-bottom font-medium text-muted-foreground">
                  <span className="flex flex-col items-center gap-0.5" title={title}>
                    <Icon className="size-3.5" aria-hidden />
                    <span className="hidden max-w-[5.5rem] truncate text-[10px] sm:block">{title}</span>
                    <span className="sr-only sm:hidden">{title}</span>
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => {
            const label = labels[i] ?? `#${i}`;
            const { icon: Icon, title } = labelMeta(label);
            return (
              <tr key={label}>
                <th scope="row" className="sticky left-0 z-[1] bg-card pr-1.5 text-left font-medium whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <Icon className="size-3.5 text-muted-foreground" aria-hidden />
                    {title}
                  </span>
                </th>
                {row.map((v, j) => {
                  const share = rowSums[i] ? v / rowSums[i] : 0;
                  const hit = i === j;
                  const tint = Math.round(12 + share * 78);
                  // White text only on deep tints; lighter cells keep the normal ink so contrast stays readable in light mode.
                  const strong = tint >= 80;
                  return (
                    <td
                      key={j}
                      title={`${title} → ${labelMeta(labels[j] ?? "").title}: ${v} (${pct(share, 0)} of row)`}
                      className="h-11 min-w-11 rounded-md text-center tabular-nums"
                      style={{
                        background:
                          v === 0
                            ? "color-mix(in oklch, var(--muted) 70%, transparent)"
                            : `color-mix(in oklch, var(${hit ? "--success" : "--danger"}) ${tint}%, transparent)`,
                      }}
                    >
                      <span className={strong ? "font-semibold text-white" : v === 0 ? "text-muted-foreground/70" : "font-medium"}>{v}</span>
                      {v > 0 && (
                        <span className={`block text-[9.5px] leading-none ${strong ? "text-white/85" : "text-muted-foreground"}`}>
                          {pct(share, 0)}
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px] bg-success" aria-hidden /> correct (diagonal)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px] bg-danger" aria-hidden /> misclassified
        </span>
        <span>darker = larger share of the true class</span>
      </div>
    </div>
  );
}
