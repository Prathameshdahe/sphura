"""`search_documents` tool: hybrid RAG over the user's uploaded files, scoped to the live run."""
from __future__ import annotations

import asyncio
import logging

from langchain_core.tools import tool

from app.agent.run import current_run

log = logging.getLogger("sphura.agent.tools")

SEARCH_TIMEOUT_S = 60.0
MAX_CHARS = 700


@tool
async def search_documents(query: str) -> str:
    """Search the user's uploaded documents (bank statements, balance sheets, invoices, policies, annual reports)
    for passages about `query`. Results become numbered sources you must cite as [n]."""
    run = current_run.get()
    if run is None:
        return "Document search is only available inside a chat turn."
    try:
        from app.rag.service import search_documents as rag_search
    except Exception as exc:  # noqa: BLE001
        log.warning("document search unavailable: %s", exc)
        return "Document search isn't available right now."
    try:
        chunks = await asyncio.wait_for(rag_search(run.turn.user_id, query, run.turn.doc_ids or None, k=6),
                                        SEARCH_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001
        log.warning("document search failed: %s", exc)
        return "Document search failed; answer from what you already have."
    if not chunks:
        return "No relevant passages found in the user's documents."
    lines = []
    for chunk in chunks:
        index = run.registry.add_doc(chunk)
        where = f" (page {chunk.page})" if getattr(chunk, "page", None) else ""
        lines.append(f"[{index}] {chunk.filename}{where}: {' '.join(chunk.text.split())[:MAX_CHARS]}")
    run.emit_sources()
    return "\n\n".join(lines)
