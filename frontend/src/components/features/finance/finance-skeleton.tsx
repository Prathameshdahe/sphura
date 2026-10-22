import { Panel } from "@/components/metrics/section";
import { Skeleton } from "@/components/ui/skeleton";

/** Placeholder with the dashboard's shape while the analysis runs. */
export function FinanceSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Analyzing the statement">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Panel key={i} className="space-y-3 p-4">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-3 w-20" />
          </Panel>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <Panel className="p-5 lg:col-span-3">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-4 h-64 w-full" />
        </Panel>
        <Panel className="flex items-center gap-6 p-5 lg:col-span-2">
          <Skeleton className="size-40 shrink-0 rounded-full" />
          <div className="flex-1 space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-3 w-full" />
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
