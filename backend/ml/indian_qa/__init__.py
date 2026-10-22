"""Author-written Indian finance QA set and scoped refusals for the sphura-fin-1.7b SFT (docs/FINANCE_PLAN.md §5 row 4).

  python -m ml.indian_qa     → ml/data/indian_finance_qa.jsonl  ({"question","answer","topic","source"})
                              ml/data/refusals.jsonl           ({"prompt","answer","template"})
The Q/A pairs live in qa_tax.py, qa_banking.py and qa_invest.py (each row carries a one-line source note); the
refusal prompts and templates in refusals.py. `check()` is what the tests and the data cards call.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from ml.indian_qa import qa_banking, qa_invest, qa_tax, refusals

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
QA_PATH = DATA_DIR / "indian_finance_qa.jsonl"
REFUSALS_PATH = DATA_DIR / "refusals.jsonl"
MIN_QA = 300
MIN_REFUSALS = 150


def qa_rows() -> list[dict]:
    rows = []
    for module in (qa_tax, qa_banking, qa_invest):
        for topic, question, answer, source in module.ROWS:
            rows.append({"question": " ".join(question.split()), "answer": " ".join(answer.split()), "topic": topic,
                         "source": source})
    return rows


def refusal_rows() -> list[dict]:
    return refusals.rows()


def check() -> dict[str, int]:
    """Validate sizes, uniqueness and that every row carries a source note; returns the counts."""
    qa = qa_rows()
    questions = [r["question"].lower() for r in qa]
    dupes = [q for q, n in Counter(questions).items() if n > 1]
    assert not dupes, f"duplicate questions: {dupes[:5]}"
    assert all(r["source"].strip() for r in qa), "every QA row needs a source note"
    assert all(len(r["answer"]) >= 25 for r in qa), "answers must be substantive"
    assert len(qa) >= MIN_QA, f"only {len(qa)} QA rows (need {MIN_QA})"
    ref = refusal_rows()
    prompts = [r["prompt"].lower() for r in ref]
    assert len(prompts) == len(set(prompts)), "duplicate refusal prompts"
    assert len(ref) >= MIN_REFUSALS, f"only {len(ref)} refusal rows (need {MIN_REFUSALS})"
    return {"qa": len(qa), "refusals": len(ref), "topics": len({r["topic"] for r in qa})}


def save() -> dict[str, int]:
    from ml.reports import write_jsonl

    counts = check()
    write_jsonl(QA_PATH, qa_rows())
    write_jsonl(REFUSALS_PATH, refusal_rows())
    return counts


def main() -> None:
    counts = save()
    print(f"indian_finance_qa.jsonl: {counts['qa']} rows over {counts['topics']} topics; refusals.jsonl: "
          f"{counts['refusals']} rows")
    for topic, n in sorted(Counter(r["topic"] for r in qa_rows()).items()):
        print(f"  {topic:14s} {n}")


if __name__ == "__main__":
    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    main()
