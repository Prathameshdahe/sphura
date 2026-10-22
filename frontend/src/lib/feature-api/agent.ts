// LangGraph export (FINANCE_PLAN §8: GET /api/agent/graph).
import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";
import type { AgentGraph } from "@/lib/feature-types";

export const agentKeys = { graph: ["agent", "graph"] as const };

export const agentApi = {
  graph: () => request<AgentGraph>("/agent/graph"),
};

export function useAgentGraph() {
  return useQuery({ queryKey: agentKeys.graph, queryFn: agentApi.graph, staleTime: 10 * 60_000 });
}
