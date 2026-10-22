"""retrieve: hybrid RAG over the attached (or all) documents → `doc` sources with page citations."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agent import adapters
from app.agent.run import attach
from app.agent.state import FinState

log = logging.getLogger("sphura.agent.retrieve")

SEARCH_TIMEOUT_S = 60.0
K = 8


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


async def retrieve(state: FinState) -> dict[str, Any]:
    run = attach(state)
    run.phase("reading", "Reading your documents")
    query = state.get("question") or run.turn.question
    step = run.step_start("search_documents", "Searching your documents")
    scope: list[str] | None = None
    if run.turn.doc_ids:
        docs = await adapters.wait_for_documents(run, step, run.turn.doc_ids)
        ready = [d for d in docs if d.status == "ready"]
        if not ready:
            detail = "No documents found" if not docs else (docs[0].error or "Documents aren't ready yet")
            run.step_end(step, "error", detail)
            return {"retrieved": [], "steps": run.steps}
        names = ready[0].filename if len(ready) == 1 else _plural(len(ready), "document")
        run.step_update(step, label=f"Searching {names}")
        scope = [d.id for d in ready]
    try:
        from app.rag.service import search_documents
    except Exception as exc:  # noqa: BLE001
        log.warning("document search unavailable: %s", exc)
        run.step_end(step, "error", "Document search isn't available")
        run.notes.append("Document search is unavailable, so the files could not be read.")
        return {"retrieved": [], "steps": run.steps}
    try:
        chunks = await asyncio.wait_for(search_documents(run.turn.user_id, query, scope, k=K), SEARCH_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001
        log.warning("document search failed: %s", exc)
        run.step_end(step, "error", "Document search failed")
        return {"retrieved": [], "steps": run.steps}
    retrieved = []
    for chunk in chunks:
        index = run.registry.add_doc(chunk)
        retrieved.append({"index": index, "docId": chunk.doc_id, "filename": chunk.filename, "page": chunk.page,
                          "score": float(chunk.score) if chunk.score is not None else None})
    run.emit_sources()
    n_docs = len({c.doc_id for c in chunks})
    detail = (f"{_plural(len(chunks), 'passage')} from {_plural(n_docs, 'document')}" if chunks
              else "No relevant passages found")
    run.step_end(step, "done", detail)
    if not chunks:
        run.notes.append("No matching passages were found in the documents; say so if the answer needs them.")
    return {"retrieved": retrieved, "sources": run.registry.sources(), "steps": run.steps}
