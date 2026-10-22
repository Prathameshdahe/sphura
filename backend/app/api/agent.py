"""GET /agent/graph: the compiled LangGraph as Mermaid plus nodes/edges (rendered by the Model Lab page)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agent.graph import graph_export
from app.api.deps import get_current_user
from app.db.models import User

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/graph")
def agent_graph(_user: User = Depends(get_current_user)) -> dict:
    return graph_export()
