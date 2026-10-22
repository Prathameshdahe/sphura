import { useMemo, useState } from "react";
import { ArrowRight, ListTree, Workflow } from "lucide-react";
import { ArtifactFrame } from "@/components/artifacts/artifact-frame";
import { MERMAID_URL } from "@/components/artifacts/artifact-utils";
import { ErrorState, Panel, Section, SectionSkeleton } from "@/components/metrics/section";
import { Stagger, StaggerItem } from "@/components/motion";
import { useAgentGraph } from "@/lib/feature-api/agent";
import type { AgentGraph } from "@/lib/feature-types";
import { cn } from "@/lib/utils";

type View = "diagram" | "list";

const MERMAID_VERSION = /mermaid@([\d.]+)/.exec(MERMAID_URL)?.[1] ?? "pinned";

/** Plain list of nodes and edges — works offline and for screen readers. */
function GraphList({ graph }: { graph: AgentGraph }) {
  const label = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n.label || n.id])), [graph.nodes]);
  return (
    <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div>
        <h4 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Nodes · {graph.nodes.length}</h4>
        <Stagger className="mt-2 flex flex-wrap gap-1.5" aria-label="Graph nodes">
          {graph.nodes.map((n) => (
            <StaggerItem key={n.id}>
              <span className="inline-flex h-7 items-center gap-1.5 rounded-full border bg-card px-2.5 text-xs font-medium" title={n.id}>
                <span className="size-1.5 rounded-full bg-brand" aria-hidden />
                {n.label || n.id}
              </span>
            </StaggerItem>
          ))}
        </Stagger>
      </div>
      <div>
        <h4 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Edges · {graph.edges.length}</h4>
        <ol className="mt-2 divide-y text-sm">
          {graph.edges.map((e, i) => (
            <li key={`${e.source}-${e.target}-${i}`} className="flex items-center gap-2 py-1.5">
              <span className="min-w-0 truncate font-medium">{label.get(e.source) ?? e.source}</span>
              <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 truncate font-medium">{label.get(e.target) ?? e.target}</span>
              {e.label && <span className="ml-auto shrink-0 rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">{e.label}</span>}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

/** 05 · The LangGraph state machine, straight from `graph.get_graph().draw_mermaid()` (GET /api/agent/graph). */
export function AgentGraphSection() {
  const graph = useAgentGraph();
  const [view, setView] = useState<View>("diagram");
  const g = graph.data;
  const hasMermaid = !!g?.mermaid?.trim();
  const showDiagram = view === "diagram" && hasMermaid;

  return (
    <Section
      id="agent"
      icon={Workflow}
      eyebrow="05 · Agent"
      title="LangGraph state machine"
      description="The exact graph the backend runs: guard → classify → one branch (analytics, retrieve, market, explain, advice, refuse) → draft ⇄ tools → verify → finalize. Exported by the server, not drawn by hand."
      actions={
        g ? (
          <div role="radiogroup" aria-label="Graph view" className="inline-flex rounded-full border bg-card p-0.5">
            {(
              [
                ["diagram", "Diagram", Workflow],
                ["list", "Nodes & edges", ListTree],
              ] as const
            ).map(([id, text, Icon]) => (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={view === id}
                disabled={id === "diagram" && !hasMermaid}
                onClick={() => setView(id)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-2 disabled:opacity-50",
                  view === id ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="size-3.5" aria-hidden /> {text}
              </button>
            ))}
          </div>
        ) : null
      }
    >
      {graph.isPending ? (
        <SectionSkeleton tiles={0} />
      ) : graph.isError ? (
        <ErrorState error={graph.error} onRetry={() => void graph.refetch()} />
      ) : !g || (g.nodes.length === 0 && !hasMermaid) ? (
        <Panel className="px-6 py-10 text-center text-sm text-muted-foreground">The agent graph is empty — is the LangGraph agent compiled?</Panel>
      ) : (
        <Panel>
          {showDiagram ? (
            <div className="h-[26rem] sm:h-[30rem]">
              <ArtifactFrame artifact={{ kind: "mermaid", code: g.mermaid, title: "LangGraph agent" }} />
            </div>
          ) : (
            <GraphList graph={g} />
          )}
          <p className="border-t px-4 py-2 text-[11px] text-muted-foreground sm:px-5">
            {showDiagram
              ? `Rendered with Mermaid ${MERMAID_VERSION} (cdn.jsdelivr.net, pinned) inside a sandboxed iframe — switch to “Nodes & edges” when offline.`
              : `${g.nodes.length} nodes · ${g.edges.length} edges · from graph.get_graph().draw_mermaid()`}
          </p>
        </Panel>
      )}
    </Section>
  );
}
