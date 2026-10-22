"""Agent plugin: in finance mode, attached CSV/XLSX files are analysed with pandas before the model answers.

The computed report becomes a `doc` source (a compact Markdown summary of exact figures) so the answer can
cite real numbers instead of eyeballing raw rows; a `finance_analyze` step shows the work.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.features.finance import service
from app.features.finance.money import money, period_label
from app.features.finance.report import analyze_file, summary_markdown

if TYPE_CHECKING:
    from app.agent.orchestrator import AgentRun

log = logging.getLogger("sphura.finance.plugin")

MAX_FILES = 5
ANALYZE_TIMEOUT_S = 60.0
SUMMARY_CHUNK_INDEX = -1  # distinct from RAG chunk indexes (0..n) in the source registry's key


@dataclass
class _Summary:
    """Duck-typed like app.rag.service.RetrievedChunk for SourceRegistry.add_doc."""

    doc_id: str
    filename: str
    page: int | None
    chunk_index: int
    text: str
    score: float | None = 1.0
    section: str | None = "Computed analysis"


def _detail(report: dict) -> str:
    cur = report.get("currency")
    if report["kind"] == "bank_statement" and report.get("totals"):
        months = len(report.get("byMonth") or [])
        period = report.get("period")
        span = f" · {period_label(period['start'], period['end'])}" if period else ""
        return f"Bank statement · {months} month{'s' if months != 1 else ''}{span} · net " \
               f"{money(report['totals']['net'], cur)}"
    if report["kind"] == "balance_sheet" and report.get("balanceSheet"):
        ratio = report["balanceSheet"].get("currentRatio")
        return "Balance sheet" + (f" · current ratio {ratio:.2f}" if ratio is not None else "")
    if report.get("warnings") and not report.get("insights"):
        return report["warnings"][0][:120]
    return "Table summary"


class FinancePlugin:
    async def before_answer(self, run: AgentRun) -> None:
        if run.turn.mode != "finance" or not run.turn.doc_ids:
            return
        docs = await asyncio.to_thread(service.load_tabular, run.turn.user_id, run.turn.doc_ids)
        if not docs:
            return
        run.phase("analyzing", "Crunching the numbers")
        cited: list[int] = []
        analysed: list[str] = []
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
            run.step_end(step, "done", _detail(report))
            cited.append(index)
            analysed.append(doc.id)
        if not analysed:
            return
        run.meta_extra["finance"] = {"docIds": analysed}
        refs = ", ".join(f"[{i}]" for i in cited)
        run.extra_system.append(
            f"Finance analytics: Sphura computed exact figures for the attached spreadsheet(s) with pandas — see "
            f"source {refs}. Use those numbers verbatim (do not re-add raw rows yourself) and cite them like {refs}. "
            "Lead with the headline numbers in a table, explain what drives them (months, categories, ratios), "
            "flag anomalies or data warnings, and close with 2-3 practical observations. This is information, "
            "not personalised investment advice.")


plugin = FinancePlugin()
