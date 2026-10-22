"""FinanceReport (docs/CONTRACT.md → Finance; TS mirror in frontend/src/lib/feature-types.ts)."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas import CamelModel


class Period(CamelModel):
    start: str
    end: str


class Totals(CamelModel):
    inflow: float
    outflow: float
    net: float


class MonthRow(CamelModel):
    month: str
    inflow: float
    outflow: float
    net: float


class CategoryRow(CamelModel):
    category: str
    amount: float
    count: int


class TransactionRow(CamelModel):
    date: str
    description: str
    amount: float
    category: str


class BalanceSheet(CamelModel):
    total_assets: float | None = None
    total_liabilities: float | None = None
    equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    debt_to_equity: float | None = None


class ProfitLoss(CamelModel):
    period: str | None = None
    previous_period: str | None = None
    revenue: float | None = None
    other_income: float | None = None
    total_income: float | None = None
    total_expenses: float | None = None
    ebitda: float | None = None
    finance_costs: float | None = None
    depreciation: float | None = None
    profit_before_tax: float | None = None
    tax: float | None = None
    net_profit: float | None = None
    net_margin: float | None = None
    ebitda_margin: float | None = None
    revenue_growth: float | None = None
    profit_growth: float | None = None
    previous_revenue: float | None = None
    previous_total_expenses: float | None = None
    previous_ebitda: float | None = None
    previous_net_profit: float | None = None
    interest_coverage: float | None = None
    return_on_equity: float | None = None
    return_on_assets: float | None = None


class FinanceReport(CamelModel):
    doc_id: str
    filename: str
    kind: Literal["bank_statement", "balance_sheet", "table"]
    currency: str | None = None
    amount_unit: str | None = None  # the scale a statement states above its table ("crore", "lakh")
    period: Period | None = None
    totals: Totals | None = None
    by_month: list[MonthRow] = Field(default_factory=list)
    by_category: list[CategoryRow] = Field(default_factory=list)
    top_transactions: list[TransactionRow] = Field(default_factory=list)
    balance_sheet: BalanceSheet | None = None
    profit_loss: ProfitLoss | None = None  # from a P&L table, or a P&L sheet in the same workbook
    insights: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalyzeIn(CamelModel):
    doc_id: str = Field(min_length=1, max_length=64)
