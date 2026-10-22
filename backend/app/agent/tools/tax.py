"""Indian income-tax estimate from the slabs in app/finance_rules.yaml (new and old regime)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import tool

RULES_PATH = Path(__file__).resolve().parents[2] / "finance_rules.yaml"


@lru_cache
def rules() -> dict[str, Any]:
    with RULES_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _slab_tax(taxable: float, slabs: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    tax, rows, lower = 0.0, [], 0.0
    for slab in slabs:
        upper = slab.get("upto")
        rate = float(slab["rate_pct"]) / 100
        top = taxable if upper is None else min(taxable, float(upper))
        if top > lower:
            amount = (top - lower) * rate
            tax += amount
            rows.append({"from": lower, "to": top, "ratePct": slab["rate_pct"], "tax": round(amount)})
        lower = float(upper) if upper is not None else lower
        if upper is not None and taxable <= float(upper):
            break
    return tax, rows


def _surcharge(tax: float, taxable: float, bands: list[dict[str, Any]]) -> float:
    rate = 0.0
    for band in bands:
        if taxable > float(band["above"]):
            rate = float(band["rate_pct"]) / 100
    return tax * rate


def regime_tax(regime: dict[str, Any], gross_income: float, deductions: float, salaried: bool) -> dict[str, Any]:
    std = float(regime.get("standard_deduction", 0)) if salaried else 0.0
    allowed = min(max(deductions, 0.0), float(regime.get("max_other_deductions", 0))) if regime.get("deductions_allowed") else 0.0
    taxable = max(0.0, gross_income - std - allowed)
    tax, rows = _slab_tax(taxable, regime["slabs"])
    rebate = regime.get("rebate_87a") or {}
    rebate_applied, marginal_relief = 0.0, 0.0
    if rebate and taxable <= float(rebate["taxable_income_upto"]):
        rebate_applied = min(tax, float(rebate["max_rebate"]))
        tax -= rebate_applied
    elif rebate and rebate.get("marginal_relief") and tax > taxable - float(rebate["taxable_income_upto"]):
        marginal_relief = tax - (taxable - float(rebate["taxable_income_upto"]))
        tax -= marginal_relief
    surcharge = _surcharge(tax, taxable, regime.get("surcharge", []))
    cess = (tax + surcharge) * float(regime.get("cess_pct", 0)) / 100
    total = tax + surcharge + cess
    return {
        "regime": regime["name"], "grossIncome": round(gross_income), "standardDeduction": round(std),
        "otherDeductionsUsed": round(allowed), "taxableIncome": round(taxable), "slabBreakdown": rows,
        "taxBeforeRebate": round(tax + rebate_applied + marginal_relief), "rebate87A": round(rebate_applied),
        "marginalRelief": round(marginal_relief), "surcharge": round(surcharge), "cess": round(cess),
        "totalTax": round(total), "effectiveRatePct": round(total / gross_income * 100, 2) if gross_income else 0.0,
    }


def estimate(gross_income: float, regime: str = "both", deductions: float = 0.0, salaried: bool = True) -> dict[str, Any]:
    data = rules()["income_tax"]
    if gross_income < 0:
        raise ValueError("income must be >= 0")
    wanted = regime.lower().strip()
    out: dict[str, Any] = {
        "financialYear": data["financial_year"], "assessmentYear": data["assessment_year"],
        "source": data["source"], "asOf": data["as_of"], "note": data.get("note", ""),
    }
    if wanted in ("new", "both"):
        out["new"] = regime_tax(data["new_regime"], gross_income, deductions, salaried)
    if wanted in ("old", "both"):
        out["old"] = regime_tax(data["old_regime"], gross_income, deductions, salaried)
    if "new" in out and "old" in out:
        better = "new" if out["new"]["totalTax"] <= out["old"]["totalTax"] else "old"
        out["better"] = better
        out["saving"] = abs(out["new"]["totalTax"] - out["old"]["totalTax"])
    return out


@tool
def income_tax_estimate(gross_income: float, regime: str = "both", deductions: float = 0.0, salaried: bool = True) -> str:
    """Estimate Indian income tax for an individual under 60. `gross_income` is annual income in rupees
    (12 LPA = 1200000); `regime` is "new", "old" or "both"; `deductions` are the Chapter VI-A amounts (80C, 80D,
    HRA, home-loan interest...) the user could claim under the OLD regime; `salaried` applies the standard
    deduction. Always state the financial year, regime and source returned in the result."""
    return json.dumps(estimate(gross_income, regime, deductions, salaried))
