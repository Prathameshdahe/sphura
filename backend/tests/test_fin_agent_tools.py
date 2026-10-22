"""Deterministic calculator / tax / ratio tools on known values, and the rules file they read."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.agent.tools import ALL_TOOLS, STEP_LABELS, tool_by_name, tools_for
from app.agent.tools.calculators import emi, emi_schedule, fd_maturity, fd_rd_maturity, ratio_calculator, ratios
from app.agent.tools.calculators import rd_maturity, sip_future_value, sip_value
from app.agent.tools.tax import RULES_PATH, estimate, income_tax_estimate, rules


def test_emi_known_values():
    home = emi_schedule(2_500_000, 8.5, 240)
    assert home["emi"] == pytest.approx(21_695.6, abs=0.5)  # ≈ ₹21,696
    assert home["totalInterest"] == pytest.approx(home["totalPayment"] - 2_500_000, abs=0.01)
    assert emi_schedule(1_000_000, 9, 60)["emi"] == pytest.approx(20_758.36, abs=0.05)
    assert emi_schedule(120_000, 0, 12)["emi"] == 10_000.0
    with pytest.raises(ValueError):
        emi_schedule(-1, 8, 12)
    out = json.loads(emi.invoke({"principal": 2500000, "annual_rate_pct": 8.5, "months": 240}))
    assert out["emi"] == pytest.approx(21_695.6, abs=0.5) and "formula" in out


def test_sip_fd_rd_known_values():
    sip = sip_value(5_000, 12, 10)
    assert sip["invested"] == 600_000 and sip["futureValue"] == pytest.approx(1_161_695, rel=0.001)
    assert json.loads(sip_future_value.invoke({"monthly": 5000, "annual_return_pct": 12, "years": 10}))["months"] == 120
    fd = fd_maturity(100_000, 7, 1, 4)
    assert fd["maturity"] == pytest.approx(107_185.9, abs=0.1)
    rd = rd_maturity(5_000, 7, 1)
    assert rd["invested"] == 60_000 and 62_000 < rd["maturity"] < 62_500
    assert json.loads(fd_rd_maturity.invoke({"kind": "rd", "amount": 5000, "annual_rate_pct": 7, "years": 1}))["kind"] == "rd"
    assert json.loads(fd_rd_maturity.invoke({"kind": "fd", "amount": 100000, "annual_rate_pct": 7, "years": 1}))["kind"] == "fd"


def test_ratios():
    out = ratios(current_assets=2_000_000, current_liabilities=1_000_000, inventory=200_000, equity=3_000_000,
                 total_liabilities=1_500_000, total_assets=4_500_000, revenue=5_000_000, net_income=500_000)
    assert out["currentRatio"] == 2.0 and out["quickRatio"] == 1.8 and out["workingCapital"] == 1_000_000
    assert out["debtToEquity"] == 0.5 and out["netMarginPct"] == 10.0 and out["returnOnEquityPct"] == pytest.approx(16.67)
    assert "benchmarks" in out
    with pytest.raises(ValueError):
        ratios()
    assert json.loads(ratio_calculator.invoke({"current_assets": 3, "current_liabilities": 2}))["currentRatio"] == 1.5


def test_income_tax_fy_2026_27_new_regime_and_comparison():
    both = estimate(1_200_000)
    assert both["financialYear"] == "FY 2026-27" and both["source"].startswith("http") and both["asOf"]
    new, old = both["new"], both["old"]
    assert new["standardDeduction"] == 75_000 and new["taxableIncome"] == 1_125_000
    assert new["taxBeforeRebate"] == 52_500 and new["rebate87A"] == 52_500 and new["totalTax"] == 0  # 12 LPA pays nothing
    assert old["taxableIncome"] == 1_150_000 and old["totalTax"] == 163_800
    assert both["better"] == "new" and both["saving"] == 163_800
    with_80c = estimate(1_200_000, regime="old", deductions=150_000)["old"]
    assert with_80c["taxableIncome"] == 1_000_000 and with_80c["totalTax"] == 117_000
    rich = estimate(3_000_000, regime="new")["new"]
    assert rich["taxableIncome"] == 2_925_000 and rich["rebate87A"] == 0 and rich["cess"] > 0
    marginal = estimate(1_290_000, regime="new")["new"]  # just above the rebate limit: marginal relief caps the tax
    assert 0 < marginal["totalTax"] <= 15_600
    out = json.loads(income_tax_estimate.invoke({"gross_income": 1200000}))
    assert out["new"]["totalTax"] == 0 and out["regime" if "regime" in out else "financialYear"]


def test_rules_file_carries_source_and_date():
    data = yaml.safe_load(Path(RULES_PATH).read_text(encoding="utf-8"))["income_tax"]
    assert data["financial_year"] == "FY 2026-27" and data["as_of"] and "http" in data["source"]
    slabs = data["new_regime"]["slabs"]
    assert [s["rate_pct"] for s in slabs] == [0, 5, 10, 15, 20, 25, 30] and slabs[-1]["upto"] is None
    assert rules()["income_tax"]["new_regime"]["rebate_87a"]["taxable_income_upto"] == 1_200_000


def test_tool_registry():
    names = {t.name for t in ALL_TOOLS}
    assert names == {"emi", "sip_future_value", "fd_rd_maturity", "income_tax_estimate", "ratio_calculator",
                     "get_quote", "get_history", "finance_news", "fx_rate", "search_documents"}
    assert set(STEP_LABELS) == names
    assert [t.name for t in tools_for("explain", with_documents=False)][-1] == "fx_rate"
    assert tools_for("documents", with_documents=True)[-1].name == "search_documents"
    assert tool_by_name("emi") is emi and tool_by_name("nope") is None
    for t in ALL_TOOLS:
        assert t.description and t.args_schema is not None


def test_tax_questions_with_an_income_pre_run_the_tax_calculator():
    from app.agent.nodes.tools import income_in

    assert income_in("I earn 12 LPA, which tax regime is better?") == 1_200_000
    assert income_in("tax on my salary of ₹15,00,000") == 1_500_000
    assert income_in("which tax regime if my CTC is 1.2 crore") == 12_000_000
    assert income_in("EMI for 25 lakh home loan at 8.5% for 20 years") is None  # not a tax question
    assert income_in("how does 80C work?") is None  # no income to compute with


def test_citation_markers_past_the_sources_are_dropped():
    from app.agent.nodes.verify import drop_phantom_citations

    assert drop_phantom_citations("EMI is ₹21,696 [1]. P/E matters [2].", 1) == "EMI is ₹21,696 [1]. P/E matters."
    assert drop_phantom_citations("See [1, 3] and [docs](https://x.y)", 1) == "See and [docs](https://x.y)"
