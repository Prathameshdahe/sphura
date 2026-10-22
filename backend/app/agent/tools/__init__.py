"""LangChain tools offered to the draft node (calculators, tax, markets, documents)."""
from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agent.tools.calculators import emi, fd_rd_maturity, ratio_calculator, sip_future_value
from app.agent.tools.documents import search_documents
from app.agent.tools.market import finance_news, fx_rate, get_history, get_quote
from app.agent.tools.tax import income_tax_estimate

CALCULATOR_TOOLS: list[BaseTool] = [emi, sip_future_value, fd_rd_maturity, income_tax_estimate, ratio_calculator]
MARKET_TOOLS: list[BaseTool] = [get_quote, get_history, finance_news, fx_rate]
DOCUMENT_TOOLS: list[BaseTool] = [search_documents]
ALL_TOOLS: list[BaseTool] = [*CALCULATOR_TOOLS, *MARKET_TOOLS, *DOCUMENT_TOOLS]
CALCULATOR_NAMES = frozenset(t.name for t in CALCULATOR_TOOLS)
MARKET_NAMES = frozenset(t.name for t in MARKET_TOOLS)

STEP_LABELS = {
    "emi": "Calculating the EMI", "sip_future_value": "Projecting the SIP value",
    "fd_rd_maturity": "Computing the deposit maturity", "income_tax_estimate": "Estimating income tax",
    "ratio_calculator": "Computing financial ratios", "get_quote": "Fetching the quote",
    "get_history": "Fetching the price history", "finance_news": "Searching finance news",
    "fx_rate": "Fetching the exchange rate", "search_documents": "Searching your documents",
}


def tools_for(intent: str, with_documents: bool) -> list[BaseTool]:
    """The tool set bound to the model for one intent (out_of_scope never reaches the model). Questions about the
    user's own statements / documents get no market tools: fewer schemas = a shorter prompt for local models."""
    tools = [*CALCULATOR_TOOLS] if intent in ("spending", "documents") else [*CALCULATOR_TOOLS, *MARKET_TOOLS]
    if with_documents:
        tools.append(search_documents)
    return tools


def tool_by_name(name: str) -> BaseTool | None:
    return next((t for t in ALL_TOOLS if t.name == name), None)


__all__ = ["CALCULATOR_TOOLS", "MARKET_TOOLS", "DOCUMENT_TOOLS", "ALL_TOOLS", "CALCULATOR_NAMES", "MARKET_NAMES",
           "STEP_LABELS", "tools_for", "tool_by_name"]
