"""Finance analytics in chat: attached spreadsheets are analysed (any mode) and cited as computed sources."""
from __future__ import annotations

import sys
import types

import pytest

from tests.test_core_chat import first, send
from tests.test_w2_finance import BALANCE, BANK, add_doc


@pytest.fixture
def no_rag(monkeypatch):
    """Document search is not under test here (and would load embedding models)."""
    async def fake_search_documents(user_id, query, doc_ids, k=8):
        return []

    fake = types.ModuleType("app.rag.service")
    fake.search_documents = fake_search_documents
    monkeypatch.setitem(sys.modules, "app.rag.service", fake)


def test_finance_mode_adds_computed_source(client, user, no_rag):
    bank = add_doc(user["user"]["id"], BANK)
    sheet = add_doc(user["user"]["id"], BALANCE)
    pdf = add_doc(user["user"]["id"], text="%PDF-1.4", filename="notes.pdf")
    _, events = send(client, user, content="Where is my money going?", mode="finance", docIds=[bank, pdf, sheet])
    done = first(events, "done")["message"]
    assert done["meta"]["finance"] == {"docIds": [bank, sheet]}

    steps = [s for s in done["steps"] if s["name"] == "finance_analyze"]
    assert [s["label"] for s in steps] == ["Analysing bank_statement_demo.csv", "Analysing balance_sheet_2025.csv"]
    assert all(s["status"] == "done" for s in steps)
    assert steps[0]["detail"].startswith("Bank statement · 6 months") and "current ratio 3.02" in steps[1]["detail"]

    first_src = next(s for s in done["sources"] if s.get("docId") == bank)
    second_src = next(s for s in done["sources"] if s.get("docId") == sheet)
    assert first_src["type"] == "doc" and first_src["filename"] == "bank_statement_demo.csv"
    assert first_src["title"] == "bank_statement_demo.csv — Computed analysis"
    assert first_src["snippet"].startswith("Computed financial analysis of bank_statement_demo.csv")
    assert second_src["snippet"].startswith("Computed financial analysis of balance_sheet_2025.csv")
    assert "[1]" in done["content"]


def test_foreign_docs_are_untouched(client, user, other_user, no_rag):
    foreign = add_doc(other_user["user"]["id"], BANK)
    _, events = send(client, user, content="Analyse it", mode="finance", docIds=[foreign])
    done = first(events, "done")["message"]
    assert not [s for s in done["steps"] if s["name"] == "finance_analyze"] and "finance" not in done["meta"]


def test_finance_prompt_carries_exact_figures(client, user, no_rag, monkeypatch):
    from app.llm import registry
    from app.llm.types import LLMChunk

    seen: list[dict] = []

    async def scripted(model, messages, tools=None, temperature=0.4, reasoning_effort=None):
        seen.append({"system": messages[0]["content"], "user": messages[-1]["content"]})
        yield LLMChunk(kind="text", text="Rent is your largest cost [1].")

    monkeypatch.setattr(registry, "chat_stream", scripted)
    bank = add_doc(user["user"]["id"], BANK)
    _, events = send(client, user, content="Biggest expense?", mode="finance", docIds=[bank])
    content = first(events, "done")["message"]["content"]
    assert content.startswith("Rent is your largest cost [1].\n\n```chart\n")  # + the computed charts
    assert "Finance analytics: Sphura computed exact figures" in seen[0]["system"]
    assert "| Rent | ₹1,32,000 |" in seen[0]["user"]
