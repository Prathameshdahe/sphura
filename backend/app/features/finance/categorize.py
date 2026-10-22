"""Transaction categoriser: the trained model first, the rule set as the safety net.

`categorize(description, amount)` returns a dashboard category name. Order:
  1. credit-only rules for Refunds and Interest (keyword-trivial; the bank parser's sign inference needs them);
  2. the trained 14-class narration model (`categoriser_model`: DistilBERT ONNX → sklearn TF-IDF) when its
     confidence is at least MODEL_THRESHOLD;
  3. the ordered regex rules below (first match wins, so specific merchants beat generic rails).
`rules_category` is the pure rule categoriser (the training scripts use it as the baseline).
"""
from __future__ import annotations

import re

OTHER = "Other"
MODEL_THRESHOLD = 0.55

# (category, direction: "in" | "out" | "any", pattern)
_RULES: list[tuple[str, str, str]] = [
    ("Salary", "in", r"salary|\bsal\b|sal cr|payroll|stipend|wages|\bpay ?roll"),
    ("Refunds", "in", r"refund|reversal|\brev\b|cashback|cash back|chargeback"),
    ("Interest", "in", r"interest|\bint\.? ?(cr|pd|paid|credit)|int\.?pd|dividend"),
    ("Loans & EMI", "out", r"\bemi\b|loan|bajaj fin|home ?loan|car ?loan|credit card (bill|payment)|cc payment|"
                           r"\bcred\b|card ?bill"),
    ("Investments", "any", r"zerodha|groww|upstox|kuvera|coin by|mutual fund|\bmf\b|\bsip\b|\bnps\b|\bppf\b|"
                           r"fixed deposit|\bfd\b|recurring deposit|\brd\b|demat|\betf\b|stocks?|shares|"
                           r"\blic\b|insurance|policy ?bazaar|smallcase|indmoney|paytm money"),
    ("Rent", "out", r"\brent\b|rental|house ?rent|landlord|nobroker|nestaway|\bpg\b|society maint|maintenance chg"),
    ("Cash withdrawal", "out", r"\batm\b|\batw\b|\bnwd\b|cash ?withdrawal|cash wdl|\bcwdr\b|self withdrawal|"
                               r"\bcash\b"),
    ("Subscriptions", "out", r"netflix|spotify|prime ?video|amazon prime|hotstar|disney|youtube|apple\.com|"
                             r"itunes|icloud|google ?one|google storage|jiocinema|sonyliv|zee5|chatgpt|openai|"
                             r"adobe|microsoft|office 365|notion|github|subscription|linkedin|audible|"
                             r"kindle unlimited|cult\.?fit|gym"),
    ("Travel", "out", r"\buber\b|\bola\b|olacabs|rapido|irctc|indigo|air ?india|vistara|spicejet|akasa|"
                      r"makemytrip|\bmmt\b|goibibo|cleartrip|yatra|redbus|\bmetro\b|fastag|\btoll\b|airbnb|"
                      r"\boyo\b|booking\.com|hotel|flight|airline|railway|\btaxi\b|\bcab\b|travel"),
    ("Utilities", "out", r"electricity|bescom|msedcl|tata power|adani elec|bses|torrent power|tneb|kseb|"
                         r"water bill|\bgas\b|indane|bharat ?gas|hp ?gas|mahanagar gas|airtel|\bjio\b|vodafone|"
                         r"\bbsnl\b|act fibernet|fibernet|broadband|postpaid|prepaid|recharge|\bdth\b|tata play|"
                         r"tata sky|utility|bill ?pay|billdesk|mobile bill|electric"),
    ("Groceries", "out", r"bigbasket|big basket|blinkit|zepto|grofers|dmart|d-mart|d mart|reliance fresh|"
                         r"reliance smart|more retail|jiomart|grocer|supermarket|kirana|nature'?s basket|"
                         r"spencer|instamart|milkbasket|country delight|vegetable|fruits?\b|walmart|costco|"
                         r"tesco|whole foods|aldi"),
    ("Dining", "out", r"swiggy|zomato|restaurant|caf[eé]|coffee|starbucks|\bccd\b|domino|pizza|mcdonald|kfc|"
                      r"burger|eatsure|dining|food|bistro|bakery|chai|haldiram|barbeque|subway|dunkin|"
                      r"chaayos|third wave|blue tokai"),
    ("Fuel", "out", r"petrol|diesel|\bfuel|indian ?oil|\biocl?\b|bharat petroleum|\bbpcl\b|\bhpcl\b|"
                    r"hp petro|\bshell\b|nayara|filling station|\bcng\b|service station"),
    ("Shopping", "out", r"amazon|amzn|flipkart|myntra|ajio|nykaa|meesho|tata ?cliq|croma|reliance digital|"
                        r"decathlon|ikea|lifestyle|shoppers stop|westside|\bh&m\b|zara|pantaloons|\bmall\b|"
                        r"shopping|lenskart|pepperfry|apple store|uniqlo|\bpos\b|ecom|store"),
    ("Fees & charges", "out", r"charges?|\bchg\b|\bfee\b|fees|\bgst\b|penalty|annual fee|\bamc\b|service tax|"
                              r"late payment|interest debit|min bal|minimum balance|\btds\b"),
    ("Transfers", "any", r"\bupi\b|\bimps\b|\bneft\b|\brtgs\b|transfer|\btrf\b|\bto self\b|\bp2p\b|paytm|phonepe|"
                         r"gpay|google ?pay|\bbhim\b|\bach\b|\bnach\b|\bzelle\b|venmo|wire"),
]
_COMPILED = [(name, direction, re.compile(pattern, re.IGNORECASE)) for name, direction, pattern in _RULES]
_CREDIT_ONLY = [(name, rx) for name, direction, rx in _COMPILED if name in ("Refunds", "Interest")]

CATEGORIES = [name for name, _, _ in _RULES] + [OTHER]


def rules_category(description: str, amount: float) -> str:
    """Rule-only category for one transaction (amount < 0 is money out)."""
    text = description or ""
    direction = "in" if amount > 0 else "out"
    for name, rule_dir, rx in _COMPILED:
        if rule_dir != "any" and rule_dir != direction:
            continue
        if rx.search(text):
            return name
    return OTHER


def categorize(description: str, amount: float) -> str:
    """Category for one transaction: credit-only rules → trained model (confident) → rules."""
    text = description or ""
    if amount > 0:
        for name, rx in _CREDIT_ONLY:
            if rx.search(text):
                return name
    from app.features.finance import categoriser_model

    pred = categoriser_model.predict_one(text, "credit" if amount > 0 else "debit")
    if pred is not None and pred[1] >= MODEL_THRESHOLD:
        return pred[0]
    return rules_category(text, amount)
