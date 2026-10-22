import { useEffect } from "react";
import { motion } from "framer-motion";
import { useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, Dumbbell, FileSearch, FlaskConical, RefreshCw, ShieldCheck, Workflow, type LucideIcon } from "lucide-react";
import { AgentGraphSection } from "@/components/features/lab/agent-graph-section";
import { ClassifiersSection } from "@/components/features/lab/classifiers-section";
import { FinetuneSection } from "@/components/features/lab/finetune-section";
import { HallucinationSection } from "@/components/features/lab/groundedness-section";
import { RagSection } from "@/components/features/lab/rag-section";
import { Page } from "@/components/layout/page";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { agentKeys } from "@/lib/feature-api/agent";
import { mlKeys, useModelLabReport } from "@/lib/feature-api/ml";
import { formatRelative } from "@/lib/format";
import { press } from "@/lib/motion";
import { useMe } from "@/lib/queries";

const SECTIONS: { id: string; label: string; icon: LucideIcon }[] = [
  { id: "classifiers", label: "Classifiers", icon: BrainCircuit },
  { id: "finetune", label: "Fine-tune", icon: Dumbbell },
  { id: "retrieval", label: "Retrieval", icon: FileSearch },
  { id: "verification", label: "Verification", icon: ShieldCheck },
  { id: "agent", label: "Agent graph", icon: Workflow },
];

function jump(id: string) {
  document.getElementById(id)?.scrollIntoView({
    block: "start",
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
  });
}

/** Model Lab: the evidence behind the AI/ML work — classifier metrics, the fine-tune, retrieval benchmark, groundedness and the agent graph. */
export default function Lab() {
  const me = useMe();
  const qc = useQueryClient();
  const report = useModelLabReport();
  const isAdmin = !!me.data?.isAdmin;

  useEffect(() => {
    document.title = "Model Lab · Sphura";
    return () => {
      document.title = "Sphura";
    };
  }, []);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: mlKeys.all });
    void qc.invalidateQueries({ queryKey: agentKeys.graph });
  };

  return (
    <Page
      header={
        <PageHeader
          icon={FlaskConical}
          title="Model Lab"
          subtitle={
            report.data?.generatedAt
              ? `Every number comes from a saved evaluation artifact · report generated ${formatRelative(report.data.generatedAt)}.`
              : "Every number on this page comes from a saved evaluation artifact, never from the UI."
          }
          action={
            <Button variant="outline" onClick={refresh} disabled={report.isFetching}>
              <RefreshCw className={report.isFetching ? "animate-spin" : undefined} /> Refresh
            </Button>
          }
        />
      }
    >
      <nav aria-label="Sections" className="scrollbar-thin -mx-1 mb-8 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {SECTIONS.map(({ id, label, icon: Icon }) => (
          <motion.button
            key={id}
            type="button"
            onClick={() => jump(id)}
            {...press}
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border bg-card px-3 text-xs font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground focus-visible:outline-2"
          >
            <Icon className="size-3.5" strokeWidth={1.75} aria-hidden /> {label}
          </motion.button>
        ))}
      </nav>

      <div className="space-y-14">
        <ClassifiersSection
          models={report.data?.models}
          loading={report.isPending}
          error={report.isError ? report.error : null}
          onRetry={() => void report.refetch()}
          isAdmin={isAdmin}
        />
        <FinetuneSection finetune={report.data?.finetune} loading={report.isPending} error={report.isError ? report.error : null} onRetry={() => void report.refetch()} />
        <RagSection report={report.data?.ragEval} loading={report.isPending} error={report.isError ? report.error : null} onRetry={() => void report.refetch()} />
        <HallucinationSection />
        <AgentGraphSection />
      </div>
    </Page>
  );
}
