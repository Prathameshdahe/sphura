"""Deterministic finance calculators (EMI, SIP, FD/RD, ratios). Pure functions wrapped as LangChain tools.

The model must take every figure from these tools rather than doing arithmetic itself.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool


def _r(x: float, places: int = 2) -> float:
    return round(float(x), places)


def emi_schedule(principal: float, annual_rate_pct: float, months: int) -> dict[str, Any]:
    """Standard reducing-balance EMI: P·r·(1+r)^n / ((1+r)^n − 1)."""
    if principal <= 0 or months <= 0:
        raise ValueError("principal and months must be positive")
    r = annual_rate_pct / 12 / 100
    if r == 0:
        emi_value = principal / months
    else:
        growth = (1 + r) ** months
        emi_value = principal * r * growth / (growth - 1)
    total = emi_value * months
    return {
        "principal": _r(principal), "annualRatePct": annual_rate_pct, "months": months,
        "emi": _r(emi_value), "totalPayment": _r(total), "totalInterest": _r(total - principal),
        "formula": "EMI = P × r × (1+r)^n / ((1+r)^n − 1), r = annual rate / 12 / 100",
    }


def sip_value(monthly: float, annual_return_pct: float, years: float) -> dict[str, Any]:
    """Future value of a monthly SIP invested at the start of each month (the usual SIP-calculator formula)."""
    if monthly <= 0 or years <= 0:
        raise ValueError("monthly amount and years must be positive")
    n = int(round(years * 12))
    i = annual_return_pct / 12 / 100
    if i == 0:
        fv = monthly * n
    else:
        fv = monthly * (((1 + i) ** n - 1) / i) * (1 + i)
    invested = monthly * n
    return {
        "monthly": _r(monthly), "annualReturnPct": annual_return_pct, "years": years, "months": n,
        "invested": _r(invested), "futureValue": _r(fv), "estimatedGains": _r(fv - invested),
        "formula": "FV = M × ((1+i)^n − 1) / i × (1+i), i = annual return / 12 / 100",
    }


def fd_maturity(principal: float, annual_rate_pct: float, years: float, compounding_per_year: int = 4) -> dict[str, Any]:
    if principal <= 0 or years <= 0:
        raise ValueError("principal and years must be positive")
    k = max(1, int(compounding_per_year))
    amount = principal * (1 + annual_rate_pct / 100 / k) ** (k * years)
    return {"kind": "fd", "principal": _r(principal), "annualRatePct": annual_rate_pct, "years": years,
            "compoundingPerYear": k, "maturity": _r(amount), "interestEarned": _r(amount - principal),
            "formula": "A = P × (1 + r/k)^(k×t)"}


def rd_maturity(monthly: float, annual_rate_pct: float, years: float) -> dict[str, Any]:
    """Recurring deposit with quarterly compounding (the formula Indian banks publish)."""
    if monthly <= 0 or years <= 0:
        raise ValueError("monthly amount and years must be positive")
    n = int(round(years * 12))
    q = annual_rate_pct / 100 / 4
    amount = sum(monthly * (1 + q) ** ((n - k + 1) / 3) for k in range(1, n + 1))
    invested = monthly * n
    return {"kind": "rd", "monthly": _r(monthly), "annualRatePct": annual_rate_pct, "years": years, "months": n,
            "invested": _r(invested), "maturity": _r(amount), "interestEarned": _r(amount - invested),
            "formula": "M = Σ P × (1 + r/4)^((n−k+1)/3) over instalments k = 1..n"}


def ratios(current_assets: float | None = None, current_liabilities: float | None = None,
           inventory: float | None = None, total_debt: float | None = None, equity: float | None = None,
           total_assets: float | None = None, total_liabilities: float | None = None, revenue: float | None = None,
           net_income: float | None = None, ebit: float | None = None, interest_expense: float | None = None,
           cash: float | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def div(a: float | None, b: float | None) -> float | None:
        return _r(a / b, 3) if a is not None and b not in (None, 0) else None

    if current_assets is not None and current_liabilities is not None:
        out["currentRatio"] = div(current_assets, current_liabilities)
        out["workingCapital"] = _r(current_assets - current_liabilities)
        out["quickRatio"] = div(current_assets - (inventory or 0), current_liabilities)
        if cash is not None:
            out["cashRatio"] = div(cash, current_liabilities)
    out["debtToEquity"] = div(total_debt, equity) if total_debt is not None else div(total_liabilities, equity)
    out["debtRatio"] = div(total_liabilities, total_assets)
    out["netMarginPct"] = _r(net_income / revenue * 100, 2) if net_income is not None and revenue else None
    out["returnOnEquityPct"] = _r(net_income / equity * 100, 2) if net_income is not None and equity else None
    out["returnOnAssetsPct"] = _r(net_income / total_assets * 100, 2) if net_income is not None and total_assets else None
    out["interestCoverage"] = div(ebit, interest_expense)
    out = {k: v for k, v in out.items() if v is not None}
    if not out:
        raise ValueError("give at least one pair of figures, e.g. current_assets and current_liabilities")
    out["benchmarks"] = {"currentRatio": "1.5–2 is comfortable; < 1 means current liabilities exceed current assets",
                         "quickRatio": ">= 1 is healthy", "debtToEquity": "< 1 conservative; > 2 highly leveraged",
                         "interestCoverage": "> 3 comfortable"}
    return out


# ── LangChain tool wrappers (JSON strings are provider-neutral tool outputs) ──
@tool
def emi(principal: float, annual_rate_pct: float, months: int) -> str:
    """Loan EMI (equated monthly instalment), total payment and total interest. Use it for home, car or
    personal loans: principal in the user's currency, annual interest rate in percent, tenure in months."""
    return json.dumps(emi_schedule(principal, annual_rate_pct, int(months)))


@tool
def sip_future_value(monthly: float, annual_return_pct: float, years: float) -> str:
    """Future value of a monthly SIP (systematic investment plan) at an assumed annual return (percent)."""
    return json.dumps(sip_value(monthly, annual_return_pct, years))


@tool
def fd_rd_maturity(kind: str, amount: float, annual_rate_pct: float, years: float, compounding_per_year: int = 4) -> str:
    """Maturity of a fixed deposit (kind="fd": `amount` is the lump sum) or a recurring deposit
    (kind="rd": `amount` is the monthly instalment) at an annual rate in percent over `years`."""
    if kind.lower().strip() == "rd":
        return json.dumps(rd_maturity(amount, annual_rate_pct, years))
    return json.dumps(fd_maturity(amount, annual_rate_pct, years, compounding_per_year))


@tool
def ratio_calculator(current_assets: float | None = None, current_liabilities: float | None = None,
                     inventory: float | None = None, total_debt: float | None = None, equity: float | None = None,
                     total_assets: float | None = None, total_liabilities: float | None = None,
                     revenue: float | None = None, net_income: float | None = None, ebit: float | None = None,
                     interest_expense: float | None = None, cash: float | None = None) -> str:
    """Financial ratios from balance-sheet / P&L figures: current & quick ratio, working capital, debt-to-equity,
    debt ratio, net margin, ROE, ROA, interest coverage. Pass only the figures you have."""
    return json.dumps(ratios(current_assets, current_liabilities, inventory, total_debt, equity, total_assets,
                             total_liabilities, revenue, net_income, ebit, interest_expense, cash))
