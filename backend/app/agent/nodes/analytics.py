"""analytics: deterministic pandas report over the user's tabular documents (spending intent)."""
from __future__ import annotations

from typing import Any

from app.agent import adapters
from app.agent.run import attach
from app.agent.state import FinState


async def analytics(state: FinState) -> dict[str, Any]:
    run = attach(state)
    run.phase("analyzing", "Crunching your statements")
    result = await adapters.analytics(run)
    return {"analytics": result, "sources": run.registry.sources(), "steps": run.steps}
