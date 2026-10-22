"""Thin adapters from the graph nodes to the kept feature code (finance analytics, memory, verify, documents).

The memory and verify plugin objects are called unchanged with an `AgentRun` (they only use the small
`phase` / `step_*` / `emit` / `registry` surface); finance analytics reuses the report + summary code and the
plugin's source shape.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.agent import prompts
from app.agent.charts import report_charts
from app.agent.run import AgentRun
from app.db.base import session_scope
from app.db.models import Document
from app.features.finance import service as finance_service
from app.features.finance.plugin import MAX_FILES, SUMMARY_CHUNK_INDEX, _detail, _Summary
from app.features.finance.report import analyze_file, is_tabular, summary_markdown
from app.llm.types import LLMError

log = logging.getLogger("sphura.agent.adapters")

DOC_WAIT_S = 90.0
DOC_POLL_S = 1.0
ANALYZE_TIMEOUT_S = 60.0
TITLE_TIMEOUT_S = 10.0
LOCAL_TITLE_S = 5.0
ANALYTICS_INSTRUCTION = (
    "Finance analytics: Sphura computed exact figures for the attached spreadsheet(s) with pandas — see "
    "source {refs}. Use those numbers verbatim (do not re-add raw rows yourself) and cite them like {refs}. "
    "Lead with the headline numbers in a table, explain what drives them (months, categories, ratios), "
    "flag anomalies or data warnings, and close with 2-3 practical observations. This is information, "
    "not personalised investment advice.")


@dataclass
class DocState:
    id: str
    filename: str
    status: str
    error: str | None


def load_documents(user_id: str, doc_ids: list[str]) -> list[DocState]:
    """The caller's documents among `doc_ids`, in request order (unknown / foreign ids are dropped)."""
    if not doc_ids:
        return []
    with session_scope() as db:
        rows = db.scalars(select(Document).where(Document.user_id == user_id, Document.id.in_(doc_ids))).all()
        by_id = {d.id: DocState(d.id, d.filename, d.status, d.error) for d in rows}
    return [by_id[i] for i in dict.fromkeys(doc_ids) if i in by_id]


def has_ready_documents(user_id: str, doc_ids: list[str]) -> bool:
    with session_scope() as db:
        stmt = select(Document.id).where(Document.user_id == user_id, Document.status == "ready")
        if doc_ids:
            stmt = stmt.where(Document.id.in_(doc_ids))
        return db.scalars(stmt.limit(1)).first() is not None


def tabular_documents(user_id: str, doc_ids: list[str]) -> list[finance_service.DocFile]:
    """Attached CSV/XLSX documents, or — when none is attached — every ready tabular document of the user."""
    attached = finance_service.load_tabular(user_id, doc_ids) if doc_ids else []
    if attached:
        return attached
    with session_scope() as db:
        rows = db.scalars(select(Document).where(Document.user_id == user_id, Document.status == "ready")
                          .order_by(Document.created_at.desc())).all()
        return [finance_service.DocFile(d.id, d.filename, Path(d.storage_path or ""), d.status)
                for d in rows if is_tabular(d.filename)][:MAX_FILES]


async def wait_for_documents(run: AgentRun, step: dict[str, Any], doc_ids: list[str]) -> list[DocState]:
    """Poll until the attached documents stop being queued/processing (or DOC_WAIT_S passes)."""
    docs = await asyncio.to_thread(load_documents, run.turn.user_id, doc_ids)
    deadline = time.monotonic() + DOC_WAIT_S
    while True:
        pending = [d for d in docs if d.status in ("queued", "processing")]
        if not pending or time.monotonic() >= deadline:
            break
        more = f" (+{len(pending) - 1} more)" if len(pending) > 1 else ""
        label = f"Waiting for {pending[0].filename} to finish indexing{more}"
        if step["label"] != label:
            run.step_update(step, label=label)
        await asyncio.sleep(DOC_POLL_S)
        docs = await asyncio.to_thread(load_documents, run.turn.user_id, doc_ids)
    for d in docs:
        if d.status == "error":
            run.notes.append(f"The document {d.filename} could not be processed ({d.error or 'unknown error'}).")
        elif d.status != "ready":
            run.notes.append(f"The document {d.filename} is still being indexed, so its content isn't available.")
    return docs


async def analytics(run: AgentRun) -> dict[str, Any]:
    """pandas analytics over the user's tabular documents → `doc` sources + a system instruction."""
    docs = await asyncio.to_thread(tabular_documents, run.turn.user_id, run.turn.doc_ids)
    if not docs:
        run.notes.append("No bank statement or spreadsheet is available: ask the user to upload a CSV/XLSX "
                         "statement for exact figures, and answer generally in the meantime.")
        return {"docIds": [], "reports": []}
    cited: list[int] = []
    analysed: list[str] = []
    reports: list[dict[str, Any]] = []
    for doc in docs[:MAX_FILES]:
        step = run.step_start("finance_analyze", f"Analysing {doc.filename}")
        if not doc.path.is_file():
            run.step_end(step, "error", "The file is no longer available")
            continue
        try:
            report = await asyncio.wait_for(asyncio.to_thread(analyze_file, doc.path, doc.filename, doc.id),
                                            ANALYZE_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001
            log.warning("finance analysis failed for %s: %s", doc.filename, exc)
            run.step_end(step, "error", "Analysis failed")
            continue
        index = run.registry.add_doc(_Summary(doc_id=doc.id, filename=doc.filename, page=None,
                                              chunk_index=SUMMARY_CHUNK_INDEX, text=summary_markdown(report)))
        run.emit_sources()
        run.charts.extend(report_charts(report))
        run.step_end(step, "done", _detail(report))
        cited.append(index)
        analysed.append(doc.id)
        reports.append({"docId": doc.id, "kind": report.get("kind"), "currency": report.get("currency"),
                        "totals": report.get("totals"), "balanceSheet": report.get("balanceSheet"),
                        "profitLoss": report.get("profitLoss")})
    if analysed:
        refs = ", ".join(f"[{i}]" for i in cited)
        run.extra_system.append(ANALYTICS_INSTRUCTION.format(refs=refs))
        run.meta_extra["analytics"] = {"docIds": analysed}
        run.meta_extra["finance"] = {"docIds": analysed}
    return {"docIds": analysed, "reports": reports}


# ── memory & verification (plugin objects called as-is) ──────────────────────
async def memory_before(run: AgentRun) -> None:
    try:
        from app.features.memory.plugin import plugin

        await plugin.before_answer(run)
    except Exception:  # noqa: BLE001 — memory is never worth failing an answer
        log.exception("memory recall failed")


async def memory_after(run: AgentRun) -> None:
    try:
        from app.features.memory.plugin import plugin

        await plugin.after_answer(run)
    except Exception:  # noqa: BLE001
        log.exception("memory write failed")


async def remember_without_model(run: AgentRun) -> None:
    """Rule-based memory write for a templated turn (the refusal): never an LLM call, whatever the model."""
    try:
        from app.features.memory import extract, ranking, store

        question = run.turn.question
        if not extract.worth_extracting(question):
            return
        enabled, _ = await asyncio.to_thread(store.recall_state, run.turn.user_id)
        facts = extract.rule_facts(question) if enabled else []
        if not facts:
            return
        existing = await asyncio.to_thread(store.existing_contents, run.turn.user_id)
        fresh = await asyncio.to_thread(ranking.novel, facts, existing)
        added = await asyncio.to_thread(store.save_facts, run.turn.user_id, run.turn.conversation_id, fresh)
        if added:
            run.meta_extra["memoriesAdded"] = added
    except Exception:  # noqa: BLE001
        log.exception("memory write failed")


async def verify_after(run: AgentRun) -> dict[str, Any] | None:
    try:
        from app.features.verify.plugin import plugin

        await plugin.after_answer(run)
    except Exception:  # noqa: BLE001
        log.exception("verification failed")
    return run.meta_extra.get("verification")


# ── titles ───────────────────────────────────────────────────────────────────
async def generate_title(run: AgentRun) -> str:
    """LLM title for a new conversation (short timeout; local models get less), else the first words."""
    from app.agent.models import chat_model, strip_thinking
    from langchain_core.messages import HumanMessage, SystemMessage

    fallback = prompts.fallback_title(run.turn.question)
    timeout = LOCAL_TITLE_S if run.model.provider in ("ollama", "lmstudio") else TITLE_TIMEOUT_S
    try:
        model = chat_model(run.model, reasoning=False, temperature=0.3, streaming=False)
        system, user = prompts.title_messages(run.turn.question)
        result = await asyncio.wait_for(
            model.ainvoke([SystemMessage(content=system["content"]), HumanMessage(content=user["content"])]),
            timeout)
        text = result.content if isinstance(result.content, str) else str(result.content)
        return prompts.clean_title(strip_thinking(text)) or fallback
    except (Exception, LLMError) as exc:  # noqa: BLE001
        log.info("title generation skipped: %s", exc)
        return fallback
