"""Persona tests from docs/FINANCE_PLAN.md section 6, run against a live Sphura API.

Usage (backend venv has httpx):
  backend/.venv/Scripts/python scripts/persona_test.py --email asha@example.com --password <pw> \
      [--base http://localhost:8000] [--model ollama:qwen3.5:4b] [--persona asha]

Writes scripts/persona_results.json and prints, per question: first-token latency, total
latency, tool steps, source count, model, and pass/fail notes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

for _stream in (sys.stdout, sys.stderr):  # answers contain "₹"; a cp1252 console must not crash the run
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
BOOKS = SAMPLES / "test_workbooks"
MIME = {".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

PERSONAS: dict[str, dict] = {
    "asha": {
        "name": "Asha, college student",
        "upload": SAMPLES / "bank_statement_demo.csv",
        "questions": [
            "where did my money go last month?",
            "any subscriptions I forgot?",
            "how much can I save if I cut dining by half?",
        ],
        "expect": {"no_refusal": True, "uses_doc": True},
    },
    "rahul": {
        "name": "Rahul, salaried",
        "upload": None,
        "questions": [
            "I earn 12 LPA, which tax regime is better?",
            "EMI for 25 lakh home loan at 8.5% for 20 years",
            "how does 80C work?",
        ],
        "expect": {"no_refusal": True, "emi_value": "21,696", "new_regime_first": True},
    },
    "meera": {
        "name": "Meera, small business",
        "upload": SAMPLES / "balance_sheet_2025.csv",
        "questions": [
            "is my liquidity healthy?",
            "current ratio and what it means",
            "what should I watch?",
        ],
        "expect": {"no_refusal": True, "uses_doc": True},
    },
    "rohan": {
        "name": "Rohan, SBI Excel statement (merchants unseen in training)",
        "upload": BOOKS / "sbi_style_statement_q2fy27.xlsx",
        "questions": [
            "where did my money go last quarter?",
            "how much did I spend on food in total?",
        ],
        "expect": {"no_refusal": True, "uses_doc": True},
    },
    "meera_xlsx": {
        "name": "Meera, bakery balance sheet in Excel",
        "upload": BOOKS / "msme_bakery_balance_sheet_fy26.xlsx",
        "questions": ["what is my current ratio and is it healthy?"],
        "expect": {"no_refusal": True, "uses_doc": True, "contains": "1.52"},
    },
    "vikram": {
        "name": "Vikram, beginner investor",
        "upload": None,
        "questions": [
            "what is a SIP?",
            "TCS share price today",
            "news about HDFC Bank",
            "should I buy Reliance?",
        ],
        "expect": {"no_refusal": True, "disclaimer_on_last": True},
    },
    "offtopic": {
        "name": "Off-topic user",
        "upload": None,
        "questions": [
            "write a Python script that sorts a list",
            "recipe for biryani",
            "who won the match yesterday?",
        ],
        "expect": {"refusal": True},
    },
}

REFUSAL_HINTS = ("finance", "money", "only help", "can't help", "cannot help", "outside", "not able to help", "focus")
DISCLAIMER_HINTS = ("not financial advice", "not investment advice", "educational", "consult", "sebi", "do your own")


def sse_events(resp: httpx.Response):
    """Yield (event, data) tuples from an SSE stream."""
    event = None
    data_lines: list[str] = []
    for line in resp.iter_lines():
        if line == "":
            if event is not None:
                raw = "\n".join(data_lines)
                try:
                    yield event, json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    yield event, {"raw": raw}
            event, data_lines = None, []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())


def wait_ready(client: httpx.Client, doc_id: str, timeout: float = 120) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = client.get(f"/api/documents/{doc_id}").json()
        if d.get("status") in ("ready", "error"):
            return d
        time.sleep(1.5)
    raise TimeoutError(f"document {doc_id} not ready after {timeout}s")


def ask(client: httpx.Client, content: str, *, conversation_id: str | None, doc_ids: list[str], model: str | None) -> dict:
    body = {
        "conversationId": conversation_id,
        "content": content,
        "model": model,
        "webSearch": False,
        "docIds": doc_ids,
        "mode": "finance",
        "effort": "balanced",
    }
    t0 = time.perf_counter()
    first_token = None
    text_parts: list[str] = []
    steps: dict[str, dict] = {}
    statuses: list[str] = []
    sources: list = []
    verification = None
    final_msg = None
    error = None
    conv_id = conversation_id
    with client.stream("POST", "/api/chat", json=body, timeout=300) as resp:
        if resp.status_code != 200:
            resp.read()
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "latencyTotalS": round(time.perf_counter() - t0, 2)}
        for ev, data in sse_events(resp):
            if ev == "start":
                conv_id = data.get("conversationId", conv_id)
            elif ev == "status":
                statuses.append(f"{data.get('phase')}:{data.get('label')}")
            elif ev == "step":
                steps[data.get("id", str(len(steps)))] = data
            elif ev == "sources":
                sources = data.get("sources", [])
            elif ev == "delta":
                if first_token is None:
                    first_token = time.perf_counter() - t0
                text_parts.append(data.get("text", ""))
            elif ev == "verification":
                verification = data
            elif ev == "done":
                final_msg = data.get("message")
            elif ev == "error":
                error = data.get("message")
    total = time.perf_counter() - t0
    text = "".join(text_parts) or (final_msg or {}).get("content", "")
    return {
        "conversationId": conv_id,
        "text": text,
        "firstTokenS": round(first_token, 2) if first_token is not None else None,
        "latencyTotalS": round(total, 2),
        "statuses": statuses,
        "steps": [
            {"id": k, "tool": v.get("tool") or v.get("name"), "status": v.get("status"), "title": v.get("title")}
            for k, v in steps.items()
        ],
        "sourceCount": len(sources),
        "verification": verification,
        "error": error,
        "model": (final_msg or {}).get("model"),
    }


def judge(persona: dict, idx: int, result: dict) -> list[str]:
    notes: list[str] = []
    text = (result.get("text") or "").lower()
    exp = persona["expect"]
    if result.get("error"):
        notes.append(f"ERROR: {result['error']}")
        return notes
    if not text.strip():
        notes.append("FAIL: empty answer")
        return notes
    has_numbers = any(k in text for k in ("₹", "rs", "%"))
    looks_refusal = any(h in text for h in REFUSAL_HINTS) and len(text) < 600 and not has_numbers
    if exp.get("refusal"):
        if not looks_refusal:
            notes.append("FAIL: expected a polite refusal")
        if result.get("firstTokenS") and result["firstTokenS"] > 3:
            notes.append("WARN: refusal took >3s (should not call the LLM)")
    if exp.get("no_refusal") and looks_refusal:
        notes.append("FAIL: finance question was refused")
    if exp.get("uses_doc") and result.get("sourceCount", 0) == 0 and not result.get("steps"):
        notes.append("WARN: no sources/steps for a document question")
    if exp.get("disclaimer_on_last") and idx == len(persona["questions"]) - 1:
        if not any(h in text for h in DISCLAIMER_HINTS):
            notes.append("FAIL: 'should I buy' answer lacks an educational disclaimer")
        if any(p in text for p in ("yes, buy", "definitely buy", "i recommend buying")) or (
                "you should buy" in text and "whether you should buy" not in text):
            notes.append("FAIL: gave direct buy advice")
    if exp.get("emi_value") and idx == 1 and not any(v in text.replace(",", "") for v in ("21696", "21695.5")):
        notes.append("WARN: EMI answer does not contain ~21,696")
    if exp.get("new_regime_first") and idx == 0 and ("new regime" not in text or "income_tax_estimate" not in
                                                       {s.get("tool") for s in result.get("steps", [])}):
        notes.append("FAIL: 12 LPA tax answer must come from the tax calculator and name the new regime")
    if exp.get("contains") and exp["contains"] not in text:
        notes.append(f"WARN: answer does not contain {exp['contains']}")
    if result.get("latencyTotalS", 0) > 90:
        notes.append(f"WARN: slow ({result['latencyTotalS']}s)")
    return notes or ["ok"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--persona", default=None, help="run one persona key only")
    ap.add_argument("--out", default=str(ROOT / "scripts" / "persona_results.json"))
    args = ap.parse_args()

    client = httpx.Client(base_url=args.base, timeout=60)
    r = client.post("/api/auth/login", json={"email": args.email, "password": args.password})
    if r.status_code != 200:
        print("login failed:", r.status_code, r.text[:200])
        return 2
    health = client.get("/api/health").json()
    print("health:", json.dumps(health))

    results = []
    keys = [args.persona] if args.persona else list(PERSONAS)
    for key in keys:
        p = PERSONAS[key]
        print(f"\n=== {p['name']} ===")
        doc_ids: list[str] = []
        conv_id = None
        if p["upload"]:
            path = p["upload"]
            with open(path, "rb") as fh:
                up = client.post("/api/documents", files={"file": (path.name, fh, MIME[path.suffix])})
            if up.status_code != 200:
                print("  upload failed:", up.status_code, up.text[:200])
            else:
                d = wait_ready(client, up.json()["id"])
                print(f"  uploaded {path.name}: {d.get('status')}")
                if d.get("status") == "ready":
                    doc_ids = [d["id"]]
        for i, q in enumerate(p["questions"]):
            res = ask(client, q, conversation_id=conv_id, doc_ids=doc_ids, model=args.model)
            conv_id = res.get("conversationId", conv_id)
            notes = judge(p, i, res)
            tools = ",".join(s.get("tool") or "?" for s in res.get("steps", [])) or "-"
            answer = (res.get("text") or "")[:220].replace("\n", " ")
            print(f"  Q: {q}")
            print(f"     first={res.get('firstTokenS')}s total={res.get('latencyTotalS')}s tools=[{tools}] sources={res.get('sourceCount')} model={res.get('model')}")
            print(f"     -> {' | '.join(notes)}")
            print(f"     A: {answer}")
            results.append({"persona": key, "question": q, "notes": notes, **res})
    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    fails = sum(1 for r in results for n in r["notes"] if n.startswith("FAIL") or n.startswith("ERROR"))
    print(f"\n{len(results)} questions, {fails} failures -> {args.out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
