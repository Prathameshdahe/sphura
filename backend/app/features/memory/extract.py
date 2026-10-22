"""Pull at most two durable facts about the user out of their message.

Cloud models: one bounded JSON LLM call. Offline/local models (the mock can't do JSON; a single local GPU shouldn't
queue extra work) and failed/unparseable LLM calls fall back to conservative first-person patterns ("I'm a …",
"I prefer …", "My name is …"), so memory works without any API key. Messages with no first-person statement are
skipped. Secrets, credentials, account/ID numbers, contact details and personal health information are never
kept — the prompt forbids them and `is_sensitive` filters whatever slips through (an ML project *about* credit
card fraud or diabetes is fine; a card number or a diagnosis is not).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.llm import registry
from app.llm.types import LLMError, ResolvedModel

log = logging.getLogger("sphura.memory")

MAX_FACTS = 2
EXTRACT_TIMEOUT_S = 4.0
MAX_INPUT_CHARS = 2000
OFFLINE_PROVIDERS = frozenset({"mock", "ollama", "lmstudio"})

_FIRST_PERSON = re.compile(r"\b(?:i|i'm|im|i've|i'd|i'll|me|my|mine|myself|we|we're|our|ours)\b", re.I)

_CREDENTIALS = re.compile(  # always sensitive
    r"\b(?:pass(?:word|wd|code|phrase)s?|one[- ]time (?:code|password)|api[ _-]?keys?"
    r"|(?:access|auth|bearer|refresh|secret|session)[ _-]?tokens?|secret[ _-]?keys?|private[ _-]?keys?"
    r"|credentials?|seed phrase|recovery (?:phrase|codes?)|mnemonic (?:phrase|seed|words?)|cvv|cvc)\b",
    re.I,
)
_ID_WORDS = re.compile(  # sensitive next to a value ("PIN is 4321", "card number …"), not as a topic
    r"\b(?:pin|otp|ssn|social security|aadhaa?r|pan (?:card|number|no)|passport|driv(?:er'?s|ing) licen[cs]e"
    r"|(?:credit|debit) card|card|iban|swift(?: code)?|routing number|sort code|ifsc|upi|(?:bank )?account"
    r"|acct)\b",
    re.I,
)
_VALUE_HINT = re.compile(r"\b(?:number|no|num|id|details|ending|ends)\b|[:=#]|\d{3,}", re.I)
_LONG_NUMBER = re.compile(r"(?<![\d.])\d(?:[ -]?\d){8,}(?![\d.])")  # 9+ digits: card/account/phone/ID numbers
_KEY_LIKE = re.compile(
    r"\b(?:(?:sk|pk|rk|ghp|gho|ghs|glpat|xox[abpr]|hf)[-_][-_A-Za-z0-9]{12,}|(?:AKIA|AIza)[-_A-Za-z0-9]{12,})"
    r"|\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{32,}\b"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_HEALTH_PERSONAL = re.compile(  # always sensitive
    r"\b(?:diagnosed with|suffer(?:s|ed|ing)? from|(?:takes?|taking|took|on) (?:\w+ )?medications?|prescribed"
    r"|(?:is|am|was) pregnant|(?:my|his|her|their) (?:doctor|therapist|psychiatrist)|hiv[- ]positive"
    r"|patient id|health id|insurance (?:id|number|policy))\b",
    re.I,
)
_HEALTH_TOPIC = re.compile(  # sensitive unless the fact is about a project/work ("a diabetes prediction model")
    r"\b(?:diagnos(?:is|es|tic)|medications?|prescriptions?|pregnan(?:t|cy)|disabilit(?:y|ies)|disabled"
    r"|mental (?:health|illness)|health (?:insurance|records?)|medical (?:records?|history|conditions?)"
    r"|blood (?:type|group)|hiv|therapy|illness|disease|disorder|diabetes|diabetic|asthma|cancer|depression"
    r"|anxiety|adhd|autism|autistic)\b",
    re.I,
)
_WORK_TOPIC = re.compile(
    r"\b(?:models?|projects?|datasets?|apps?|applications?|systems?|classifiers?|predictors?|predictions?"
    r"|detection|detectors?|chatbots?|bots?|research(?:ing|er)?|thesis|dissertation|papers?|startups?|pipelines?"
    r"|tools?|platforms?|analysis|analytics|courses?|internships?|hackathons?|company|domain|industry)\b",
    re.I,
)

SYSTEM_PROMPT = f"""You maintain the long-term memory of an AI assistant. Read the user's message and extract at most \
{MAX_FACTS} durable facts about the USER that would help in future conversations: lasting preferences (answer style, \
format, language, tools), background (role, field of study, skills, city-level location), goals, or ongoing projects.

Rules:
- Only facts the user states about themselves. Ignore questions, one-off tasks, facts about the topic or other people.
- Never include secrets or sensitive data: passwords, API keys, tokens, credentials, card/bank/account/ID numbers, \
email addresses, phone numbers, street addresses, or health information.
- Write each fact as one short third-person phrase without "The user", e.g. "Prefers concise answers with code \
examples", "Is a final-year computer science student", "Is building a chatbot called Sphura".
- When nothing qualifies, return an empty list.

Respond with JSON only: {{"facts": ["..."]}}"""

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)
_DIGIT = re.compile(r"\d")


def worth_extracting(message: str) -> bool:
    """Cheap pre-filter: only first-person messages can state facts about the user."""
    return len(message.strip()) >= 12 and bool(_FIRST_PERSON.search(message))


def uses_llm(model: ResolvedModel | None) -> bool:
    """Cloud models extract with a JSON call; offline/local ones use the rule-based fallback."""
    return model is not None and model.provider not in OFFLINE_PROVIDERS


def should_extract(model: ResolvedModel | None, message: str) -> bool:
    """Any model can extract (LLM or rules); only first-person messages are worth it."""
    return worth_extracting(message)


def is_secret(text: str) -> bool:
    """Credentials, keys, financial/ID numbers, phone numbers or e-mail addresses."""
    return bool(_CREDENTIALS.search(text) or _LONG_NUMBER.search(text) or _KEY_LIKE.search(text)
                or _EMAIL.search(text) or (_ID_WORDS.search(text) and _VALUE_HINT.search(text)))


def is_sensitive(text: str) -> bool:
    """`is_secret`, or personal health information."""
    return is_secret(text) or bool(_HEALTH_PERSONAL.search(text)
                                   or (_HEALTH_TOPIC.search(text) and not _WORK_TOPIC.search(text)))


def parse_json(text: str) -> Any | None:
    if not text:
        return None
    for candidate in (text.strip(), *(m.group(1).strip() for m in _FENCE.finditer(text))):
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            return None
    return None


def clean_facts(raw: Any) -> list[str]:
    """Validated facts from the model's JSON: short statements, no questions, nothing sensitive, ≤ MAX_FACTS."""
    items = raw.get("facts") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    facts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            item = item.get("fact") or item.get("content") or ""
        if not isinstance(item, str):
            continue
        fact = " ".join(item.split()).strip("-•*\"' ")
        if not 8 <= len(fact) <= 200 or fact.endswith("?") or is_sensitive(fact):
            continue
        fact = fact[0].upper() + fact[1:]
        if fact.lower() not in {f.lower() for f in facts}:
            facts.append(fact)
        if len(facts) == MAX_FACTS:
            break
    return facts


# ── rule-based fallback (no LLM) ─────────────────────────────────────────────
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\s*\n\s*")  # "B.Tech" / "3.5" stay intact
_CLAUSE_SPLIT = re.compile(r",\s*|\s+(?:and|but|so|also|plus)\s+(?=(?:i|i'm|im|i've|my)\b)", re.I)
_HYPOTHETICAL = re.compile(r"\b(?:if|when|whether|suppose|imagine|pretend|like|as|what|how|why|do|does|should"
                           r"|could|would|can|will|did|assume|translate|rephrase|paraphrase|correct|fix|check"
                           r"|say|says|said|write|repeat|means?|sentence|quote)\b"
                           r"|[\"“”«`]|(?:^|\s)['‘]", re.I)  # …or quoted text before the match
RULES_MAX_CHARS = 600  # longer messages usually paste text written by someone else
_I_AM = r"\b(?:i am|i'm|i’m|im)\s+"
_NOT_OBJECT = r"(?!(?:this|that|it|these|those|you|your|yours|the|how|what|when|to know|a bit|a lot|so much)\b)"
# (pattern searched in one clause, fact template, max words of the remainder `x`) — the first match wins
_RULES: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"\bmy name is\s+(?!not\b)", re.I), "Name is {x}", 3),
    (re.compile(r"\b(?:please\s+)?call me\s+", re.I), "Prefers to be called {x}", 3),
    (re.compile(_I_AM + r"(?:currently\s+|now\s+|also\s+)?(?P<verb>building|developing|creating|working on"
                r"|learning|studying|researching|writing|preparing for|pursuing)\s+" + _NOT_OBJECT, re.I),
     "Is {verb} {x}", 14),
    (re.compile(_I_AM + r"(?:originally\s+)?from\s+", re.I), "Is from {x}", 4),
    (re.compile(_I_AM + r"(?P<art>a|an)\s+(?!(?:bit|little|lot|tad)\b)", re.I), "Is {art} {x}", 10),
    (re.compile(r"\bi\s+(?:currently\s+|also\s+)?work\s+(?P<prep>as|at|in|for|on)\s+", re.I), "Works {prep} {x}", 10),
    (re.compile(r"\bi\s+(?:currently\s+|also\s+)?study\s+(?:(?P<prep>at|in)\s+)?", re.I), "Studies {prep}{x}", 10),
    (re.compile(r"\bi\s+(?:currently\s+)?live\s+in\s+", re.I), "Lives in {x}", 4),
    (re.compile(r"\bi(?:'d| would)?\s+(?:really\s+|usually\s+|always\s+|generally\s+)?prefer\s+" + _NOT_OBJECT,
                re.I), "Prefers {x}", 12),
    (re.compile(r"\bi\s+(?:mostly\s+|usually\s+|mainly\s+|always\s+)?(?:code|program)\s+in\s+", re.I),
     "Codes in {x}", 6),
    (re.compile(r"\bi\s+(?:mostly\s+|usually\s+|mainly\s+|always\s+)?use\s+" + _NOT_OBJECT, re.I), "Uses {x}", 8),
    (re.compile(r"\bi\s+(?:really\s+)?(?P<verb>like|love|enjoy)\s+" + _NOT_OBJECT, re.I), "{Verb}s {x}", 8),
    (re.compile(r"\bmy goal is to\s+", re.I), "Goal is to {x}", 12),
    (re.compile(r"\bi\s+(?:want|plan|hope|aim)\s+to\s+become\s+", re.I), "Wants to become {x}", 8),
    (re.compile(r"\bmy\s+favou?rite\s+(?P<what>\w+(?:\s\w+)?)\s+is\s+", re.I), "Favorite {what} is {x}", 6),
]
_PRONOUNS = {"my": "their", "mine": "theirs", "me": "them", "myself": "themselves"}
_PRONOUN = re.compile(r"\b(?:my|mine|me|myself)\b", re.I)
_ABOUT_ASSISTANT = re.compile(r"\b(?:you|your|yours)\b", re.I)  # facts are about the user, not about Sphura
_TRAILING = re.compile(r"\s+(?:because|since|so that|which|who|lol|haha)\b.*$", re.I)
_STRIP = " \t\"'“”‘’()*_.,!:;-"


def _rule_fact(clause: str) -> str | None:
    """The fact stated by one clause, or None."""
    for pattern, template, max_words in _RULES:
        match = pattern.search(clause)
        if not match:
            continue
        if _HYPOTHETICAL.search(clause[: match.start()]):
            return None
        words = _TRAILING.sub("", clause[match.end():]).strip(_STRIP).split()
        if not words or len(words) > max_words or _ABOUT_ASSISTANT.search(" ".join(words)):
            return None
        if template.startswith(("Lives", "Is from")) and _DIGIT.search(" ".join(words)):
            return None  # city-level only, never a street address
        if template.startswith(("Name is", "Prefers to be called")):
            words = [w if w[:1].isupper() else w.capitalize() for w in words]
        x = _PRONOUN.sub(lambda m: _PRONOUNS[m.group(0).lower()], " ".join(words))
        groups = {k: (v or "").lower() for k, v in match.groupdict().items()}
        if groups.get("prep"):
            groups["prep"] += " "
        return " ".join(template.format(x=x, Verb=groups.get("verb", "").capitalize(), **groups).split())
    return None


def rule_facts(message: str) -> list[str]:
    """Up to MAX_FACTS facts from plain first-person statements (questions and hypotheticals are skipped)."""
    if len(message) > RULES_MAX_CHARS or "```" in message:
        return []
    facts: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(message):
        if sentence.lstrip().startswith(">"):  # a quote, not the user speaking
            continue
        for clause in _CLAUSE_SPLIT.split(sentence):
            clause = (clause or "").strip()
            fact = _rule_fact(clause) if clause and not clause.endswith("?") else None
            if fact:
                facts.append(fact)
    return clean_facts(facts)


async def _complete(model: ResolvedModel, messages: list[dict[str, str]]) -> str:
    try:
        return await registry.complete(model, messages, temperature=0.0, json_mode=True, timeout=EXTRACT_TIMEOUT_S)
    except LLMError as exc:
        if exc.kind not in ("bad_request", "unknown"):  # e.g. an endpoint that rejects json_object
            raise
        return await registry.complete(model, messages, temperature=0.0, timeout=EXTRACT_TIMEOUT_S)


async def extract_facts(model: ResolvedModel | None, message: str) -> list[str]:
    """Up to MAX_FACTS facts, or [] — never raises. Cloud models use the LLM; local/offline models, and any LLM
    call that fails, times out or doesn't return JSON, use the rule-based fallback."""
    if not should_extract(model, message):
        return []
    if not uses_llm(model):
        return rule_facts(message)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.strip()[:MAX_INPUT_CHARS]}]
    try:
        raw = await asyncio.wait_for(_complete(model, messages), EXTRACT_TIMEOUT_S + 0.5)
    except asyncio.TimeoutError:
        log.info("memory extraction timed out (%s); using rules", model.id)
        return rule_facts(message)
    except Exception as exc:  # noqa: BLE001
        log.info("memory extraction failed (%s): %s; using rules", model.id, exc)
        return rule_facts(message)
    parsed = parse_json(raw)
    return rule_facts(message) if parsed is None else clean_facts(parsed)
