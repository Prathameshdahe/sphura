"""Intent classification for the finance graph: trained router → keyword fallback → (optional) local LLM.

Order of precedence (docs/FINANCE_PLAN.md section 3):
  1. deterministic rules: `webSearch` forces `market`; attached tabular files → `spending`, other files → `documents`
  2. the trained finance router (backend/ml/artifacts/fin_router.joblib, trained by the training engineer)
     when its confidence is >= ROUTER_THRESHOLD
  3. the keyword classifier below (also the fallback when the artifact is absent or fails to load)
The node may additionally ask the local model for structured output when both are unsure (see nodes/classify.py).
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR, settings

log = logging.getLogger("sphura.classify")

ROUTER_PATH = BACKEND_DIR / "ml" / "artifacts" / "fin_router.joblib"
ROUTER_THRESHOLD = 0.6
NO_SIGNAL = 0.4  # keyword confidence when the text has neither finance nor off-topic markers
LABELS = ("spending", "documents", "market", "explain", "advice", "out_of_scope")

_lock = threading.Lock()
_bundle: dict[str, Any] | None = None
_bundle_mtime: float | None = None


@dataclass
class Classification:
    intent: str
    confidence: float
    method: str  # "rule" | "router" | "keywords" | "llm"


# ── keyword classifier ───────────────────────────────────────────────────────
_FINANCE = re.compile(
    r"\b(money|spend|spent|spending|expense|expenses|budget|budgeting|save|saving|savings|salary|income|earn|"
    r"tax|taxes|itr|gst|tds|80c|80d|regime|slab|deduction|rebate|cess|lpa|lakh|lakhs|crore|crores|rupee|rupees|"
    r"inr|usd|dollar|euro|emi|loan|loans|mortgage|interest|rate|rates|sip|sips|mutual fund|mutual funds|fund|"
    r"funds|nav|fd|rd|fixed deposit|recurring deposit|ppf|epf|nps|elss|pension|insurance|premium|policy|"
    r"stock|stocks|share|shares|equity|equities|nifty|sensex|nasdaq|dow|s&p|index|market|markets|ipo|dividend|"
    r"portfolio|invest|investing|investment|investments|investor|trade|trading|trader|etf|bond|bonds|gold|"
    r"crypto|bitcoin|ethereum|forex|fx|exchange rate|inflation|interest rate|repo rate|rbi|sebi|bank|banking|"
    r"account|credit|debit|card|upi|neft|imps|rtgs|cheque|balance|statement|transaction|transactions|"
    r"subscription|subscriptions|recurring|bill|bills|rent|invoice|invoices|payable|receivable|revenue|profit|"
    r"loss|margin|ebitda|ebit|cash flow|cashflow|liquidity|solvency|ratio|ratios|balance sheet|p&l|pnl|"
    r"accounting|accounts|audit|ledger|depreciation|asset|assets|liability|liabilities|debt|wealth|net worth|"
    r"retirement|retire|credit score|cibil|financial|finance|finances|price|prices|quote|valuation|pe ratio|"
    r"earnings|quarterly results|fiscal|compounding|compound|annuity|maturity|principal|tenure|lumpsum|"
    r"lump sum|cost|costs|fees|charges|refund|cashback|wallet|paytm|zerodha|groww|hdfc|icici|sbi|axis|kotak|"
    r"reliance|tcs|infosys|wipro|adani|tata|bajaj|apple|tesla|nvidia|microsoft|google|amazon)\b", re.I)
_OUT_OF_SCOPE = re.compile(
    r"\b(python|javascript|typescript|java|c\+\+|rust|golang|sql query|regex|html|css|react|code|coding|script|"
    r"function|bug|debug|compile|algorithm|recipe|recipes|cook|cooking|bake|biryani|pasta|ingredients|"
    r"cricket|football|soccer|tennis|ipl|world cup|match|tournament|goal scored|who won|movie|movies|film|"
    r"song|songs|lyrics|poem|poetry|story|novel|joke|jokes|weather|forecast|temperature|translate|"
    r"translation|homework|essay|physics|chemistry|biology|photosynthesis|quantum|history of|capital of|"
    r"planet|galaxy|workout|diet plan|medicine|doctor|symptoms|travel itinerary|visa|hotel booking|"
    r"girlfriend|boyfriend|dating)\b", re.I)
_ADVICE = re.compile(
    r"\b(should i (?:buy|sell|invest|hold|exit|book|put|switch|move|go)|is it (?:a )?good (?:time|idea) to "
    r"(?:buy|sell|invest)|worth (?:buying|investing)|buy or sell|which (?:stock|share|fund|mutual fund|"
    r"coin|crypto) (?:should|to) (?:i )?(?:buy|pick|choose)|recommend (?:a |me |some )?(?:stock|share|fund|"
    r"mutual fund|crypto)|best (?:stock|stocks|share|shares|fund|funds|mutual fund|mutual funds|crypto) "
    r"to (?:buy|invest)|will (?:\S+ )?(?:stock|share|price|nifty|sensex|bitcoin|gold) (?:go up|rise|fall|"
    r"crash)|allocate my|where (?:should|do) i invest|what should i invest)\b", re.I)
_MARKET = re.compile(
    r"\b(share price|stock price|price of|quote|quotes|trading at|how is .* (?:stock|share) doing|"
    r"nifty|sensex|nasdaq|dow jones|s&p 500|bank nifty|nse|bse|ipo|52[- ]week|market cap|"
    r"news|headlines|latest|today|yesterday|this week|current price|live price|chart|history|performance|"
    r"exchange rate|usd to inr|inr to usd|dollar rate|gold price|silver price|bitcoin price|crypto price|"
    r"forex|dividend yield|pe ratio|earnings|quarterly results|q[1-4] results)\b", re.I)
_SPENDING = re.compile(
    r"\b(my (?:money|spending|expenses|spends|budget|statement|statements|bank statement|transactions|"
    r"salary|income|savings|bills|subscriptions|rent|emis|categories|cash ?flow)|where (?:did|does|is) my money|"
    r"how much (?:did|do|have) i (?:spend|spent|save|saved|pay|paid)|spent on|spend on|spending on|"
    r"subscriptions? i|recurring (?:charges|payments)|cut (?:my )?(?:dining|food|shopping|spending)|"
    r"save (?:\d+ ?%|\d+ percent|more|money)|can i save|biggest expense|largest expense|top expenses|"
    r"categori[sz]e|monthly (?:spend|spending|expenses|burn)|last month|this month|bank statement|"
    r"statement|transactions?|my liquidity|my (?:balance sheet|current ratio|quick ratio|cash|debt|runway)|"
    r"is my (?:liquidity|business|company|cash position|balance sheet)|what should i watch)\b", re.I)
_DOCUMENT = re.compile(
    r"\b(this (?:document|file|pdf|report|invoice|policy|contract|statement|annual report|balance sheet)|"
    r"the (?:attached|uploaded) (?:document|file|pdf|report|invoice|policy|contract)|in (?:my|the) "
    r"(?:document|file|pdf|report|invoice|policy|contract|annual report)|according to the (?:document|report|"
    r"policy|contract)|clause|section \d|page \d|summari[sz]e (?:this|the (?:document|file|report|pdf))|"
    r"what does (?:this|the) (?:document|report|policy|invoice|contract) say)\b", re.I)
_EXPLAIN = re.compile(r"\b(what is|what are|what's|whats|explain|how does|how do|how to|define|meaning of|difference "
                      r"between|vs\.?|versus|compare|which (?:tax )?regime|better|calculate|compute|work out|"
                      r"estimate|formula|example)\b", re.I)


# A short message that only makes sense with the previous turn ("why?", "explain it more simply", "and for 10
# years?"): the router, which sees one message, tends to call these off-topic.
_CONTEXTUAL = re.compile(
    r"\b(it|its|that|this|those|these|them|they|same|above|previous|earlier|again|more|less|simpler|simply|"
    r"shorter|briefly|why|elaborate|explain|clarify|example|examples|table|chart|summari[sz]e|summary|detail|"
    r"details|continue|go on|instead|what about|how about|what if|and if|and for|and the|and what|and how|"
    r"then|so)\b", re.I)
FOLLOW_UP_MAX_WORDS = 12


def contextual_follow_up(text: str) -> bool:
    words = (text or "").split()
    return 0 < len(words) <= FOLLOW_UP_MAX_WORDS and bool(_CONTEXTUAL.search(text))


def _available_router() -> dict[str, Any] | None:
    """The training engineer's finance router bundle ({model, labels, embedding_model}), reloaded on change."""
    global _bundle, _bundle_mtime
    try:
        mtime = ROUTER_PATH.stat().st_mtime
    except OSError:
        return None
    if _bundle is not None and _bundle_mtime == mtime:
        return _bundle
    with _lock:
        if _bundle is None or _bundle_mtime != mtime:
            try:
                import joblib

                bundle = joblib.load(ROUTER_PATH)
            except Exception as exc:  # noqa: BLE001 — a broken artifact must never break chat
                log.warning("finance router artifact could not be loaded: %s", exc)
                return None
            if not isinstance(bundle, dict) or "model" not in bundle:
                log.warning("finance router artifact has an unexpected layout; using keywords")
                return None
            trained_on = bundle.get("embedding_model")
            if trained_on and trained_on != settings.embedding_model:
                log.warning("finance router was trained on %s but EMBEDDING_MODEL is %s; using keywords",
                            trained_on, settings.embedding_model)
                return None
            _bundle, _bundle_mtime = bundle, mtime
            log.info("finance router loaded from %s", ROUTER_PATH.name)
        return _bundle


def router_available() -> bool:
    return ROUTER_PATH.exists()


def router_predict(text: str) -> Classification | None:
    """Trained router prediction (blocking: call from a worker thread), or None when unavailable."""
    bundle = _available_router()
    text = " ".join((text or "").split())[:2000]
    if bundle is None or not text:
        return None
    try:
        import numpy as np

        model = bundle["model"]
        if bundle.get("embedding_model"):
            from app.features.router.model import embed_texts

            features = embed_texts([text])
        else:  # a self-contained sklearn pipeline (e.g. TF-IDF + LR) takes raw text
            features = [text]
        probs = model.predict_proba(features)[0]
        classes = [str(c) for c in model.classes_]
        best = int(np.argmax(probs))
        label = classes[best]
        if label not in LABELS:
            return None
        return Classification(label, round(float(probs[best]), 4), "router")
    except Exception as exc:  # noqa: BLE001
        log.info("finance router prediction failed: %s", exc)
        return None


def keyword_classify(text: str) -> Classification:
    """Deterministic fallback. Refuses only on clear off-topic markers without any finance signal."""
    t = " ".join((text or "").split())
    finance = len(_FINANCE.findall(t))
    off_topic = len(_OUT_OF_SCOPE.findall(t))
    if off_topic and not finance:
        return Classification("out_of_scope", min(0.95, 0.7 + 0.1 * off_topic), "keywords")
    if _ADVICE.search(t):
        return Classification("advice", 0.9, "keywords")
    spending = len(_SPENDING.findall(t))
    market = len(_MARKET.findall(t))
    document = len(_DOCUMENT.findall(t))
    if document and document >= max(spending, market):
        return Classification("documents", 0.8, "keywords")
    if spending and spending >= market:
        return Classification("spending", min(0.95, 0.7 + 0.1 * spending), "keywords")
    if market or (finance and _mentions_symbol(t)):
        return Classification("market", min(0.95, 0.7 + 0.1 * market), "keywords")
    if finance:
        return Classification("explain", 0.75 if _EXPLAIN.search(t) else 0.65, "keywords")
    if off_topic:
        return Classification("out_of_scope", 0.7, "keywords")
    # No signal either way (e.g. "I prefer concise answers"): let the finance-tuned model answer.
    return Classification("explain", NO_SIGNAL, "keywords")


def _mentions_symbol(text: str) -> bool:
    """A known ticker / company / index name in the text (bare acronyms like EMI or SIP never count)."""
    try:
        from app.features.market.symbols import mentions

        return bool(mentions(text, limit=1))
    except Exception:  # noqa: BLE001
        return False


def has_tabular(filenames: list[str]) -> bool:
    return any(Path(f).suffix.lower() in (".csv", ".xlsx", ".xls") for f in filenames)


STRONG = 0.9  # router confidence that overrides the attachment rule for market / advice questions


def classify(text: str, *, web_search: bool = False, attached: list[str] | None = None,
             follow_up: bool = False) -> Classification:
    """Rules first, then the trained router (confidence >= 0.6), then keywords (blocking; use a thread).

    Guardrails on the rules: a clearly off-topic message (router and keywords agree) is refused even with the web
    toggle or attachments on; a strong market / advice prediction beats the attachment rule; and in a follow-up
    the router alone cannot refuse a message the keyword classifier sees finance in ("what should I watch?" after
    a balance-sheet question) or that only makes sense with the previous turn ("why?", "and for 10 years?").
    Any other off-topic follow-up ("tell me about Shah Rukh Khan") is still refused without a model call."""
    attached = attached or []
    routed = router_predict(text)
    keywords = keyword_classify(text)
    router_off = routed is not None and routed.intent == "out_of_scope" and routed.confidence >= ROUTER_THRESHOLD
    if keywords.intent == "out_of_scope" and (routed is None or router_off):
        method = "router" if routed is not None else "keywords"
        return Classification("out_of_scope", max(keywords.confidence, routed.confidence if routed else 0.0), method)
    if web_search:
        return Classification("market", 1.0, "rule")
    if attached:
        if routed is not None and routed.intent in ("market", "advice") and routed.confidence >= STRONG:
            return routed
        return Classification("spending" if has_tabular(attached) else "documents", 1.0, "rule")
    if router_off and follow_up and (keywords.confidence > NO_SIGNAL or contextual_follow_up(text)):
        return keywords
    if routed is not None and routed.confidence >= ROUTER_THRESHOLD:
        return routed
    if routed is not None and routed.intent == keywords.intent:
        return Classification(routed.intent, max(routed.confidence, keywords.confidence), "router")
    return keywords


def label_for(intent: str) -> str:
    return {
        "spending": "Spending question", "documents": "Document question", "market": "Market question",
        "explain": "Finance concept", "advice": "Advice request", "out_of_scope": "Off-topic",
    }.get(intent, intent)
