"""Prompt building: the finance persona, per-intent notes, context block, history trimming and titles."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

CONTEXT_HEADER = "Context gathered by Sphura for this question (not written by the user):"

_PERSONA = """You are Sphura (Sanskrit sphur, "a flash of insight"), a brilliant, warm and precise AI assistant.
Today is {today}.

How you answer:
- Write in GitHub-flavoured Markdown. Lead with the direct answer, then the supporting detail.
- Use headings, bullet lists, tables and fenced code blocks (with a language tag) when they help; keep simple answers short.
- Write math in LaTeX: $inline$ and $$display$$.
- Be honest about uncertainty. Never fabricate facts, numbers, quotes, people, URLs or references.

Artifacts (rendered live in a side panel next to the chat):
- When the user asks for a chart, visualization, interactive demo, small web page or UI mock-up, reply with ONE complete,
  self-contained HTML document in a ```html code block (inline CSS/JS; you may load libraries such as Chart.js or D3 from
  https://cdn.jsdelivr.net). Keep it under ~250 lines and make it look polished in both light and dark backgrounds.
- For flowcharts, sequence, class or mind-map diagrams, reply with a ```mermaid code block instead.
- Briefly explain the artifact outside the code block."""

_CITATIONS = """
Sources:
- The latest user message is followed by numbered sources [1], [2], ... gathered from the web and/or the user's documents.
- Ground your answer in them and cite inline right after each supported claim, like [1] or [2][3].
- Use ONLY the indices listed there. Never invent a citation, source or URL.
- If the sources don't contain the answer, say so clearly, then answer from general knowledge and mark that part as not from the sources.
- Do not add a references list at the end: the interface already shows the sources."""

_TOOLS = """
Tools: you can call {names} to gather information before answering.
- Search when the question needs current, specific or verifiable facts you are not sure of; otherwise answer directly.
- Never repeat a search that is listed as already done. When you have enough information, write the final answer."""

_MODES = {
    "finance": """
Mode: careful financial analyst.
- Show calculations step by step and put figures in tables. State assumptions, units, currencies and the date of any data.
- Flag risks, limitations and caveats. Provide information and analysis, not personalised investment advice; say so when discussing specific securities.""",
    "research": """
Mode: deep research.
- Be thorough and well structured: open with a short summary, then organised sections, then key takeaways.
- Compare viewpoints, note disagreements and gaps in the evidence, and rely on the sources rather than memory.""",
}

# ── finance persona (the LangGraph draft node) ───────────────────────────────
_FIN_PERSONA = """You are Sphura, a finance-only AI assistant for people in India: personal finance, spending and budgeting, \
business accounting, investing and markets (educational), and finance concepts. Today is {today}.

How you answer:
- GitHub-flavoured Markdown. Lead with the direct answer, then the supporting detail; tables for figures; LaTeX for formulas.
- Every computed figure (EMI, SIP value, maturity, tax, ratios) MUST come from a tool result or a numbered source. \
Never do the arithmetic yourself and never invent prices, rates, tax slabs, dates or statistics.
- State assumptions, units (₹, %, years), the financial year and regime for any tax figure, and that market data is delayed.
- You are not a SEBI-registered investment adviser: explain, compare and educate; never give a personalised buy / sell / \
hold or asset-allocation recommendation. When asked "should I buy X?", give the educational framing (what to look at, \
risks, how to decide) and say it is not personalised advice.
- If a message is not about money or finance, say politely that you only help with finance and suggest what you can do.
- Be concise: most answers fit in 120–250 words unless the user asks for depth.
- Never use emoji or decorative symbols; plain words and Markdown formatting only.
- Charts of the user's statements and of price history are attached automatically below your answer; do not draw those yourself. Only when the user asks to see a chart of other figures that appear in the sources or tool results (an EMI split, a SIP projection, a tax comparison), add ONE fenced block with the language `chart` holding JSON: {{"type": "bar" | "line" | "pie", "title": "...", "unit": "₹", "labels": [...], "series": [{{"name": "...", "data": [numbers]}}]}}. Never invent the numbers."""

_FIN_TOOLS = """
Tools: {names}.
- emi: loan EMIs (principal, annual rate %, months). sip_future_value: SIP projections. fd_rd_maturity: FD/RD maturity.
- income_tax_estimate: Indian income tax for an income (regime "new", "old" or "both"); quote the FY/regime/source it returns.
- ratio_calculator: liquidity/leverage/profitability ratios from balance-sheet or P&L figures.
- get_quote / get_history / fx_rate / finance_news: delayed market data and sentiment-labelled headlines.
- search_documents: passages from the user's uploaded files (only when they could hold the answer).
Call a tool at most once per figure, then write the final answer. Do not call tools for things already in the sources."""

_INTENT_NOTES = {
    "spending": "This is a spending / budgeting question about the user's own statement. Use the computed analytics "
                "source verbatim for every amount, name months and categories, and give 2-3 concrete, kind suggestions.",
    "documents": "Answer from the user's documents. Quote the figures and clauses you rely on with [n] citations; say "
                 "clearly when the documents do not contain the answer.",
    "market": "This is a market question. Use only the quoted figures and headlines in the sources (cite them), mention "
              "that prices are delayed, and add one line of context. No buy/sell recommendation.",
    "explain": "Explain the concept simply with one worked example when it helps; use the calculators for any numbers.",
    "advice": "The user is asking for investment advice. Do NOT recommend buying, selling, holding or an allocation. "
              "Teach: what the instrument is, what drives its returns and risks, what a beginner should check (goal, "
              "horizon, costs, diversification) and point to a SEBI-registered adviser. End with the disclaimer line: "
              "\"*Sphura is not a SEBI-registered investment adviser; this is general education, not a personalised "
              "recommendation.*\"",
}

_TITLE_SYSTEM = ("Write a short, specific title (3 to 6 words) for a conversation that starts with the user's "
                 "message below. Reply with the title only: no quotes, no trailing punctuation.")
_QUERY_SYSTEM = ("Rewrite the user's latest message as one standalone web search query, resolving pronouns from "
                 "the conversation. Reply with the search query only.")
_CLASSIFY_SYSTEM = (
    "Classify the user's latest message for a finance-only assistant. Labels: spending (their own bank statement, "
    "expenses, subscriptions, savings from their data), documents (questions about an uploaded balance sheet, "
    "invoice, policy or report), market (stock / index / fund / FX prices, charts or finance news), explain "
    "(a finance concept, calculation, tax, loans, SIP/EMI/FD, ratios), advice (asks what THEY should buy, sell, "
    "hold or invest in), out_of_scope (not about money or finance at all: code, recipes, sport, general chit-chat).")
_CITE = re.compile(r"\s?\[\d+(?:\s*,\s*\d+)*\](?!\()")
_FENCED = re.compile(r"(^```.*?^```[ \t]*$)", re.M | re.S)  # code blocks, chart JSON included


def outside_code(text: str, fn: Any) -> str:
    """Apply `fn` to the prose only: "[120, 340]" in a ```chart block is data, not a citation."""
    parts = _FENCED.split(text)
    return "".join(part if i % 2 else fn(part) for i, part in enumerate(parts))


def system_prompt(mode: str, has_sources: bool, tool_names: list[str], today: datetime | None = None) -> str:
    day = (today or datetime.now()).strftime("%A, %d %B %Y")
    parts = [_PERSONA.format(today=day), _MODES.get(mode, "")]
    if tool_names:
        parts.append(_TOOLS.format(names=", ".join(tool_names)))
    if has_sources or tool_names:
        parts.append(_CITATIONS)
    return "\n".join(p for p in parts if p).strip()


def finance_system_prompt(intent: str, has_sources: bool, tool_names: list[str], extra: list[str] | None = None,
                          today: datetime | None = None) -> str:
    """The draft node's system prompt: persona, intent note, tool guide, citation rules and plugin context."""
    day = (today or datetime.now()).strftime("%A, %d %B %Y")
    parts = [_FIN_PERSONA.format(today=day)]
    note = _INTENT_NOTES.get(intent)
    if note:
        parts.append("This turn: " + note)
    if tool_names:
        parts.append(_FIN_TOOLS.format(names=", ".join(tool_names)))
    if has_sources or tool_names:
        parts.append(_CITATIONS)
    parts.extend(extra or [])
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def classify_messages(question: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    recent = "\n".join(f"{m['role']}: {strip_citations(m['content'])[:300]}" for m in history[-4:])
    user = f"Conversation so far:\n{recent}\n\nLatest message:\n{question[:800]}" if recent else question[:800]
    return [{"role": "system", "content": _CLASSIFY_SYSTEM}, {"role": "user", "content": user}]


def user_turn(question: str, context: str, searches: list[str], notes: list[str]) -> str:
    """The user's question plus the numbered context block the model must cite from."""
    extra: list[str] = []
    if context:
        extra.append(f"Sources:\n{context}")
    if searches:
        extra.append("Searches already done: " + "; ".join(f'"{s}"' for s in searches))
    if notes:
        extra.append("Notes:\n" + "\n".join(f"- {n}" for n in notes))
    if not extra:
        return question
    return f"{question}\n\n---\n{CONTEXT_HEADER}\n\n" + "\n\n".join(extra)


def strip_citations(text: str) -> str:
    return outside_code(text, lambda prose: _CITE.sub("", prose))


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 4


def trim_history(history: list[dict[str, str]], budget_tokens: int) -> list[dict[str, str]]:
    """Newest-first within the budget; old answers lose their (now stale) [n] markers.

    The newest answer is cut to half the budget first: kept whole, a long answer would push out the question that
    led to it, and the leading-user rule below would then drop the answer too (no context for "and for 10 years?").
    """
    kept: list[dict[str, str]] = []
    used = 0
    half = budget_tokens // 2
    for i, msg in enumerate(reversed(history)):
        content = msg["content"].strip()
        if msg["role"] == "assistant":
            content = strip_citations(content)
            if i == 0 and half > 50 and estimate_tokens(content) > half:
                content = content[: (half - 6) * 4].rstrip() + " …"
        if not content:
            continue
        cost = estimate_tokens(content)
        if used + cost > budget_tokens:
            if not kept and budget_tokens > 200:  # keep the tail of a huge last message
                kept.append({"role": msg["role"], "content": "…" + content[-(budget_tokens - 50) * 4:]})
            break
        kept.append({"role": msg["role"], "content": content})
        used += cost
    kept.reverse()
    while kept and kept[0]["role"] != "user":
        kept.pop(0)
    return kept


def normalise_turns(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge consecutive same-role messages so every provider sees strictly alternating turns."""
    out: list[dict[str, Any]] = []
    for m in messages:
        if out and out[-1]["role"] == m["role"] and m["role"] != "system":
            out[-1] = {"role": m["role"], "content": f"{out[-1]['content']}\n\n{m['content']}"}
        else:
            out.append(dict(m))
    return out


def fallback_title(text: str, words: int = 6) -> str:
    clean = re.sub(r"\s+", " ", re.sub(r"[`*_#>\[\]]", "", text)).strip()
    parts = clean.split(" ")[:words]
    title = " ".join(parts)
    if len(title) > 60:
        title = title[:57].rstrip() + "…"
    elif len(clean.split(" ")) > words:
        title += "…"
    return title[:1].upper() + title[1:] if title else "New chat"


def clean_title(raw: str) -> str:
    line = next((ln for ln in raw.strip().splitlines() if ln.strip()), "")
    line = re.sub(r"^(title|conversation title)\s*:\s*", "", line.strip(), flags=re.I)
    line = line.strip().strip("\"'`*#“”‘’ ").rstrip(".!?:;,")
    if not line or len(line.split()) > 12:
        return ""
    return line[:80]


def title_messages(question: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": _TITLE_SYSTEM}, {"role": "user", "content": question[:1500]}]


def query_messages(question: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    recent = history[-4:]
    convo = "\n".join(f"{m['role']}: {strip_citations(m['content'])[:500]}" for m in recent)
    return [
        {"role": "system", "content": _QUERY_SYSTEM},
        {"role": "user", "content": f"Conversation:\n{convo}\n\nLatest message:\n{question[:800]}"},
    ]


def clean_query(raw: str, fallback: str) -> str:
    line = next((ln for ln in raw.strip().splitlines() if ln.strip()), "")
    line = re.sub(r"^(search query|query)\s*:\s*", "", line.strip(), flags=re.I).strip().strip("\"'`")
    return line[:300] if 2 <= len(line) <= 300 else fallback[:300]
