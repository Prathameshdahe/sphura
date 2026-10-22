"""POST /finance/analyze — deterministic analytics over an uploaded CSV/XLSX (docs/CONTRACT.md → Finance)."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.db.models import User
from app.features.finance import service
from app.features.finance.insights import llm_insights
from app.features.finance.report import analyze_file, is_tabular
from app.features.finance.schemas import AnalyzeIn, FinanceReport

router = APIRouter(prefix="/finance", tags=["finance"])

ANALYZE_TIMEOUT_S = 90.0


@router.post("/analyze", response_model=FinanceReport)
async def analyze(body: AnalyzeIn, user: User = Depends(get_current_user)) -> dict[str, Any]:
    doc = await asyncio.to_thread(service.load_owned, user.id, body.doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if not is_tabular(doc.filename):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "Finance analysis needs a CSV or Excel file (.csv, .xlsx, .xls).")
    if not doc.path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The file for this document is no longer available")
    try:
        report = await asyncio.wait_for(asyncio.to_thread(analyze_file, doc.path, doc.filename, doc.id),
                                        ANALYZE_TIMEOUT_S)
    except asyncio.TimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "The analysis took too long; try a smaller file.") from None
    if report["totals"] or report["balanceSheet"] or report["byCategory"]:
        better = await llm_insights(report)
        if better:
            report["insights"] = better
    return report
