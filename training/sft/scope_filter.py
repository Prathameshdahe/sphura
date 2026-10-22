"""Drop off-topic general-instruction rows from the Sujet slices of the SFT mix (optional, for a re-run).

    backend/.venv/Scripts/python training/sft/scope_filter.py        (run from the repo root; CPU, ~1 min)

Why: Sujet-Finance-Instruct-177k aggregates several instruction sets, and the trained finance router labels many
of its "qa" / "conversation" prompts out_of_scope ("Write a short story about a robot…"). Training on those answers
contradicts the 139 refusal rows. This script applies the same deterministic rule to train, held-out and the judge
set (so the hold-out stays a fair hold-out): a Sujet row is dropped when the router's top label is out_of_scope.
indian_qa, refusal and finqa rows are never touched.

Reads training/data/sft/ and writes training/data/sft_scoped/ (the original files are left as they are, because
the first SFT run was trained on them). Train on it with `train.py --data training/data/sft_scoped`.
Runs in backend/.venv because the router uses the app's fastembed bge-small embedder.
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "training" / "data" / "sft"
DST = REPO / "training" / "data" / "sft_scoped"
sys.path.insert(0, str(REPO / "backend"))

from app.features.router import model as router  # noqa: E402

JUDGE_EVAL = 100
UNTOUCHED = {"indian_qa", "refusal", "finqa"}


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def off_topic(prompt: str) -> tuple[bool, float]:
    pred = router.predict(" ".join(prompt.split())[:2000])
    return pred.label == "out_of_scope", float(pred.confidence)


def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for row in rows:
        if row["source"] in UNTOUCHED:
            kept.append(row)
            continue
        flag, conf = off_topic(row["messages"][1]["content"])
        if flag:
            dropped.append({**row, "meta": {**(row.get("meta") or {}), "routerOutOfScope": round(conf, 4)}})
        else:
            kept.append(row)
    return kept, dropped


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    train, train_drop = split(load(SRC / "train.jsonl"))
    hold, hold_drop = split(load(SRC / "holdout.jsonl"))
    dropped_prompts = {r["messages"][1]["content"] for r in hold_drop}
    judge = [r for r in load(SRC / "judge_eval.jsonl") if r["prompt"] not in dropped_prompts]
    have = {r["prompt"] for r in judge}
    pool = [r for r in hold if r["source"] in ("indian_qa", "sujet_qa", "sujet_qa_with_context", "sujet_conversation")
            and r["messages"][1]["content"] not in have]
    for r in pool:  # deterministic top-up in hold-out order
        if len(judge) >= JUDGE_EVAL:
            break
        judge.append({"prompt": r["messages"][1]["content"], "reference": r["messages"][2]["content"],
                      "source": r["source"]})
    write(DST / "train.jsonl", train)
    write(DST / "holdout.jsonl", hold)
    write(DST / "judge_eval.jsonl", judge)
    write(DST / "dropped.jsonl", train_drop + hold_drop)
    for name in ("finqa_eval.jsonl", "offtopic_eval.jsonl", "finance_eval.jsonl"):
        shutil.copy(SRC / name, DST / name)
    stats = {
        "train": len(train), "holdout": len(hold), "judgeEval": len(judge),
        "droppedTrain": dict(Counter(r["source"] for r in train_drop)),
        "droppedHoldout": dict(Counter(r["source"] for r in hold_drop)),
        "bySourceTrain": dict(Counter(r["source"] for r in train)),
        "rule": "drop Sujet rows whose user prompt the finance router (fin_router.joblib) labels out_of_scope",
        "source": "training/data/sft",
    }
    (DST / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
