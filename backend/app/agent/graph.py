"""The finance LangGraph (docs/FINANCE_PLAN.md section 3):

START → guard_in → classify ─┬─ spending   → analytics ─┐
                             ├─ documents  → retrieve ──┤
                             ├─ market     → market ────┤→ draft ⇄ tools → verify → finalize → END
                             ├─ explain ───────────────┘
                             ├─ advice     → draft (disclaimer prompt) …
                             └─ out_of_scope → refuse → END
"Sphura Ensemble": draft ⇄ tools runs on the lead model with its text held back, then ensemble (other models
answer in parallel, the lead merges) → verify.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.analytics import analytics
from app.agent.nodes.classify import classify
from app.agent.nodes.draft import MAX_ROUNDS, draft
from app.agent.nodes.ensemble import ensemble, is_active
from app.agent.nodes.finalize import finalize
from app.agent.nodes.guard import guard_in, refuse
from app.agent.nodes.market import market
from app.agent.nodes.retrieve import retrieve
from app.agent.nodes.tools import tools
from app.agent.nodes.verify import verify
from app.agent.run import lookup
from app.agent.state import FinState

log = logging.getLogger("sphura.agent.graph")

NODE_LABELS = {
    "__start__": "Start", "guard_in": "Guard in (redact PII)", "classify": "Classify intent",
    "analytics": "Analytics (pandas)", "retrieve": "Retrieve (hybrid RAG)", "market": "Market data",
    "draft": "Draft (LLM + tools)", "tools": "Tools", "verify": "Verify (NLI)", "finalize": "Finalize",
    "refuse": "Refuse (templated)", "ensemble": "Ensemble (ask all, merge)", "__end__": "End",
}
INTENT_TARGETS = {"spending": "analytics", "documents": "retrieve", "market": "market", "explain": "draft",
                  "advice": "draft", "out_of_scope": "refuse"}

_compiled: Any = None            # compiled without a checkpointer (always usable)
_checkpointed: Any = None        # compiled with the AsyncSqliteSaver opened at startup
_checkpoint_loop: asyncio.AbstractEventLoop | None = None


def route_intent(state: FinState) -> str:
    return INTENT_TARGETS.get(state.get("intent") or "explain", "draft")


def after_draft(state: FinState) -> str:
    """Tools while the model asks for them and the effort's round budget lasts; otherwise verify."""
    messages = state.get("messages") or []
    last = messages[-1] if messages else None
    within_budget = int(state.get("tool_rounds") or 0) <= MAX_ROUNDS.get(state.get("effort") or "balanced", 3)
    if last is not None and getattr(last, "tool_calls", None) and within_budget:
        return "tools"
    try:
        return "ensemble" if is_active(lookup(state["run_id"])) else "verify"
    except (KeyError, RuntimeError):
        return "verify"


def build_graph(checkpointer: Any = None) -> Any:
    g = StateGraph(FinState)
    g.add_node("guard_in", guard_in)
    g.add_node("classify", classify)
    g.add_node("analytics", analytics)
    g.add_node("retrieve", retrieve)
    g.add_node("market", market)
    g.add_node("draft", draft)
    g.add_node("tools", tools)
    g.add_node("verify", verify)
    g.add_node("finalize", finalize)
    g.add_node("ensemble", ensemble)
    g.add_node("refuse", refuse)
    g.add_edge(START, "guard_in")
    g.add_edge("guard_in", "classify")
    g.add_conditional_edges("classify", route_intent, {"analytics": "analytics", "retrieve": "retrieve",
                                                       "market": "market", "draft": "draft", "refuse": "refuse"})
    g.add_edge("analytics", "draft")
    g.add_edge("retrieve", "draft")
    g.add_edge("market", "draft")
    g.add_conditional_edges("draft", after_draft, {"tools": "tools", "verify": "verify", "ensemble": "ensemble"})
    g.add_edge("ensemble", "verify")
    g.add_edge("tools", "draft")
    g.add_edge("verify", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("refuse", END)
    return g.compile(checkpointer=checkpointer)


def set_checkpointer(saver: Any, loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Install (or remove, with None) the checkpointer-backed graph opened by app.agent.lifecycle."""
    global _checkpointed, _checkpoint_loop
    _checkpointed = build_graph(saver) if saver is not None else None
    _checkpoint_loop = loop if saver is not None else None


def get_graph() -> Any:
    """The compiled graph for the current event loop (checkpointed when the lifecycle opened one here)."""
    global _compiled
    if _checkpointed is not None:
        try:
            if asyncio.get_running_loop() is _checkpoint_loop:
                return _checkpointed
        except RuntimeError:
            pass
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def graph_export() -> dict[str, Any]:
    """{mermaid, nodes, edges} of the compiled graph for the Model Lab page."""
    drawable = get_graph().get_graph()
    nodes_out = [{"id": n.id, "label": NODE_LABELS.get(n.id, n.id)} for n in drawable.nodes.values()]
    edges_out = [{"source": e.source, "target": e.target,
                  "label": (str(e.data) if e.data is not None else ("conditional" if e.conditional else None))}
                 for e in drawable.edges]
    return {"mermaid": drawable.draw_mermaid(), "nodes": nodes_out, "edges": edges_out}
