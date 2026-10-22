"""Guardrails: input redaction (guard_in), the out-of-scope refusal and the advice disclaimer.

Nothing here calls a model. Redaction runs before the text is logged, stored in the graph state or sent to a
cloud provider: card numbers, bank account numbers, Aadhaar and PAN are replaced by typed placeholders.
"""
from __future__ import annotations

import re

# Payment cards: 13-19 digits with optional spaces/dashes in groups (Luhn is not required: we prefer to over-redact).
_CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
# Aadhaar: 12 digits, usually "1234 5678 9012"; PAN: ABCDE1234F.
_AADHAAR = re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")
_PAN = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")  # people type it in lower case too
# Account numbers: 9-18 digits next to an account/acct/a/c keyword, or any bare 11-18 digit run.
_ACCOUNT_CTX = re.compile(r"(?i)(?:\b(?:account|acct|a/c|ac)\b(?:\s*(?:no\.?|number|num|#))?|\bifsc\s*\S+\s*)"
                          r"\W{0,12}(\d[\d ]{7,20}\d)")
_LONG_DIGITS = re.compile(r"(?<![\d.,])\d{11,18}(?![\d.,])")
_CVV = re.compile(r"(?i)\b(cvv|cvc|pin|mpin|otp)\b(?:\s+(?:is|was|number|no\.?|code))?\W{0,6}(\d{3,6})\b")

REDACTED_CARD = "[card number redacted]"
REDACTED_ACCOUNT = "[account number redacted]"
REDACTED_AADHAAR = "[aadhaar redacted]"
REDACTED_PAN = "[pan redacted]"


def _digits(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


def redact(text: str) -> tuple[str, list[str]]:
    """Replace sensitive identifiers with placeholders; returns (clean text, kinds redacted)."""
    kinds: list[str] = []

    def account_ctx(m: re.Match[str]) -> str:
        kinds.append("account")
        return m.group(0).replace(m.group(1), REDACTED_ACCOUNT)

    def card(m: re.Match[str]) -> str:
        if 13 <= _digits(m.group(0)) <= 19:
            kinds.append("card")
            return REDACTED_CARD
        return m.group(0)

    text = _ACCOUNT_CTX.sub(account_ctx, text)  # "a/c no. 5010…" is an account even when it is card-length
    text = _CARD.sub(card, text)
    if _PAN.search(text):
        kinds.append("pan")
        text = _PAN.sub(REDACTED_PAN, text)
    if _AADHAAR.search(text):
        kinds.append("aadhaar")
        text = _AADHAAR.sub(REDACTED_AADHAAR, text)
    if _LONG_DIGITS.search(text):
        kinds.append("account")
        text = _LONG_DIGITS.sub(REDACTED_ACCOUNT, text)
    if _CVV.search(text):
        kinds.append("card")
        text = _CVV.sub(lambda m: f"{m.group(1)} [redacted]", text)
    return text, list(dict.fromkeys(kinds))


REFUSAL = (
    "I'm Sphura, a finance-only assistant, so I can't help with that request.\n\n"
    "I can help you with things like:\n"
    "- **Spending**: upload a bank statement and ask where your money goes or which subscriptions to cut.\n"
    "- **Documents**: ask grounded questions about balance sheets, invoices, policies or annual reports.\n"
    "- **Markets**: stock, index, mutual fund or FX quotes and finance news.\n"
    "- **Finance concepts**: SIP, EMI, FD/RD, tax regimes, ratios like EBITDA or the current ratio.\n\n"
    "Ask me a money question and I'll get to work."
)

GREETING = (
    "Hi! I'm Sphura, your finance assistant. I can analyse bank statements, answer questions about your "
    "financial documents, look up market quotes and news, and explain personal-finance concepts "
    "(SIP, EMI, tax regimes, ratios). What would you like to look at?"
)

ADVICE_DISCLAIMER = (
    "*Sphura is not a SEBI-registered investment adviser. This is general financial education, not a "
    "personalised recommendation to buy, sell or hold any security; consider your goals, risk appetite and a "
    "registered adviser before acting.*"
)
_DISCLAIMER_HINT = re.compile(r"not (?:a |an )?(?:sebi[- ])?registered|not (?:personalised|personalized|individual) "
                              r"(?:investment |financial )?advice|educational purposes", re.I)


THANKS = "You're welcome! Anything else about your money I can help with — a statement, a document, a stock or a concept?"
_GREETINGS = {"hi", "hello", "hey", "namaste", "hola", "yo", "good"}
_THANKS = {"thanks", "thank", "thx", "ok", "okay", "great", "cool", "nice", "awesome", "perfect", "got"}


def refusal_text(question: str) -> str:
    """Templated refusal (or a greeting / thanks for small talk); never calls a model."""
    words = re.findall(r"[a-z']+", question.lower())
    if words and len(words) <= 4 and words[0] in _THANKS:
        return THANKS
    if words and len(words) <= 6 and (words[0] in _GREETINGS or words[:3] == ["how", "are", "you"]):
        return GREETING
    return REFUSAL


def needs_disclaimer(answer: str) -> bool:
    return not _DISCLAIMER_HINT.search(answer or "")
