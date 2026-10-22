"""Build the SFT mix for sphura-fin-1.7b (docs/FINANCE_PLAN.md §5 row 4) and the held-out evaluation sets.

    training/.venv/Scripts/python training/sft/build_data.py

Sources (all read from training/data/raw and backend/ml/data; nothing is downloaded here):
  * sujet-ai/Sujet-Finance-Instruct-177k (CSV, Apache-2.0) — a stratified ~2,500-row subset: `qa` (finance-alpaca
    StackExchange answers, filtered), `qa_with_context` (FinTalk-19k, ConvFinQA, finqabench; the generic alpaca
    rows are dropped by a finance-keyword filter), `qa_conversation` (lmsys-finance only — the 'contrived' set is
    synthetic) and `sentiment_analysis` capped at 10 % of the subset.
  * ChanceFocus/flare-finqa (parquet; FinQA, MIT) — ~800 train rows whose prompt + answer fit 1,024 Qwen3 tokens.
    TheFinAI/Fino1_Reasoning_Path_FinQA is a gated dataset (no token on this machine), so the FinQA questions come
    from flare-finqa and the answer is the gold number (no GPT-4o reasoning path). 100 rows of its TEST split are
    the FinQA numeric-EM evaluation set and are never trained on.
  * backend/ml/data/indian_finance_qa.jsonl — the author-written Indian finance QA (≥ 300 rows, source notes).
  * backend/ml/data/refusals.jsonl — hand-written off-topic prompts with scoped refusals (≥ 150 rows).
  * backend/ml/data/fin_router.jsonl — hand-written rows supply the off-topic / finance prompts for the refusal evals.

10 % of EVERY slice is held out before training (stratified by slice, fixed seed) → holdout.jsonl.
Outputs (training/data/sft/): train.jsonl, holdout.jsonl, finqa_eval.jsonl, offtopic_eval.jsonl, finance_eval.jsonl,
judge_eval.jsonl, stats.json. Row format: {"messages": [system, user, assistant], "source": str, "meta": {...}}.
"""
from __future__ import annotations

import csv
import glob
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAINING_DIR = HERE.parent
REPO = TRAINING_DIR.parent
BACKEND = REPO / "backend"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BACKEND))

from prompts import SYSTEM_PROMPT  # noqa: E402

RAW = TRAINING_DIR / "data" / "raw"
OUT = TRAINING_DIR / "data" / "sft"
ML_DATA = BACKEND / "ml" / "data"
SUJET_CSV = RAW / "sujet-ai__Sujet-Finance-Instruct-177k" / "sujet-ai" / "Sujet-Finance-Instruct-177k.csv"
FINQA_DIR = RAW / "ChanceFocus__flare-finqa" / "data"
SEED = 2026
MAX_TOKENS = 1024
HOLDOUT = 0.10
TARGETS = {"sujet_qa": 1100, "sujet_qa_with_context": 700, "sujet_conversation": 450, "sujet_sentiment": 250,
           "finqa": 800}
FINQA_EVAL = 100
JUDGE_EVAL = 100
_FIN = re.compile(r"\b(tax|invest|stock|share|fund|bank|loan|mortgage|credit|debt|interest|dividend|bond|equity|"
                  r"revenue|profit|loss|income|salary|budget|saving|savings|insurance|pension|retire|portfolio|"
                  r"market|price|inflation|rate|finance|financial|money|cash|payment|account|asset|liabilit|capital|"
                  r"earning|expense|cost|valuation|ipo|etf|broker|trading|trade|option|futures|currency|dollar|rupee|"
                  r"euro|gdp|economy|economic|fiscal|audit|accounting|balance sheet|cash flow|emi|sip|gst|roi|yield|"
                  r"deposit|withdraw|wallet|fee|lease|rent|mutual)\w*", re.I)
_URL = re.compile(r"https?://\S+")


def _tok():
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained("Qwen/Qwen3-1.7B")


def _row(user: str, assistant: str, source: str, meta: dict | None = None) -> dict:
    return {"messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user.strip()},
                         {"role": "assistant", "content": assistant.strip()}], "source": source, "meta": meta or {}}


def _clean(text: str) -> str:
    return " ".join(_URL.sub("", str(text)).replace("\r", "\n").split(" ")).strip()


def load_sujet(rng: random.Random) -> list[dict]:
    import pandas as pd

    df = pd.read_csv(SUJET_CSV, usecols=["answer", "system_prompt", "user_prompt", "task_type", "dataset"])
    df = df.dropna(subset=["answer", "user_prompt"])
    df["user_prompt"] = df["user_prompt"].astype(str)
    df["answer"] = df["answer"].astype(str)
    out: list[dict] = []

    def take(sub, n: int, source: str, build) -> None:
        sub = sub.sample(frac=1.0, random_state=rng.randint(0, 10**6))
        kept = 0
        for _, r in sub.iterrows():
            row = build(r)
            if row is None:
                continue
            out.append(_row(row[0], row[1], source, {"dataset": r["dataset"], "task_type": r["task_type"]}))
            kept += 1
            if kept >= n:
                break

    def qa(r):
        q = _clean(r["user_prompt"]).removeprefix("Question:").strip()
        a = _clean(r["answer"])
        if not (15 <= len(q) <= 600 and 150 <= len(a) <= 1800) or not _FIN.search(q + " " + a):
            return None
        if a.count("?") > 3 or " I'm not" in a[:40]:  # forum noise: answers that are mostly more questions
            return None
        return q, a

    def qa_ctx(r):
        if r["dataset"] not in ("ceadar-ie/FinTalk-19k", "AdaptLLM/finance-tasks_ConvFinQA", "lighthouzai/finqabench",
                                "gbharti/finance-alpaca"):
            return None
        u, a = _clean(r["user_prompt"]), _clean(r["answer"])
        if r["dataset"] == "gbharti/finance-alpaca" and len(_FIN.findall(u + " " + a)) < 3:
            return None  # generic alpaca rows ("identify the odd one out") are not finance
        if not (40 <= len(u) <= 2500 and 20 <= len(a) <= 1500):
            return None
        return u, a

    def conv(r):
        if r["dataset"] != "amphora/lmsys-finance":
            return None
        u, a = _clean(r["user_prompt"]), _clean(r["answer"])
        if not (30 <= len(u) <= 2500 and 60 <= len(a) <= 1500) or not _FIN.search(u):
            return None
        return u, a

    def sent(r):
        text = _clean(r["user_prompt"])
        a = str(r["answer"]).strip().lower()
        if a not in ("positive", "neutral", "negative") or not (20 <= len(text) <= 400):
            return None
        return ("What is the sentiment of this financial text — positive, neutral or negative?\n\n" + text,
                f"{a.capitalize()}.")

    take(df[df.task_type == "qa"], TARGETS["sujet_qa"], "sujet_qa", qa)
    take(df[df.task_type == "qa_with_context"], TARGETS["sujet_qa_with_context"], "sujet_qa_with_context", qa_ctx)
    take(df[df.task_type == "qa_conversation"], TARGETS["sujet_conversation"], "sujet_conversation", conv)
    take(df[(df.task_type == "sentiment_analysis") & (df.dataset.isin(["financial_phrasebank",
         "zeroshot/twitter-financial-news-sentiment"]))], TARGETS["sujet_sentiment"], "sujet_sentiment", sent)
    return out


def _finqa_frame(split: str):
    import pandas as pd

    return pd.read_parquet(glob.glob(str(FINQA_DIR / f"{split}-*.parquet"))[0])


def _finqa_prompt(r) -> str:
    query = str(r["query"]).strip()
    question = str(r["text"]).strip()
    if question and question not in query:
        query = query + "\nQuestion: " + question
    return query


def load_finqa(rng: random.Random, tok) -> tuple[list[dict], list[dict]]:
    """(train rows ≤ MAX_TOKENS from the train split, 100 eval rows from the test split)."""
    train = _finqa_frame("train").sample(frac=1.0, random_state=SEED)
    rows: list[dict] = []
    for _, r in train.iterrows():
        prompt, answer = _finqa_prompt(r), str(r["answer"]).strip()
        if not answer or answer.lower() in ("yes", "no"):
            continue
        reply = f"The answer is {answer}."
        if len(tok(prompt + reply)["input_ids"]) + 60 > MAX_TOKENS:
            continue
        rows.append(_row(prompt, reply, "finqa", {"id": r["id"], "gold": answer}))
        if len(rows) >= TARGETS["finqa"]:
            break
    test = _finqa_frame("test").sample(frac=1.0, random_state=SEED)
    evals: list[dict] = []
    for _, r in test.iterrows():
        prompt, answer = _finqa_prompt(r), str(r["answer"]).strip()
        try:
            float(answer.replace("%", "").replace(",", ""))
        except ValueError:
            continue  # the EM metric is numeric
        if len(tok(prompt)["input_ids"]) + 80 > MAX_TOKENS:
            continue
        evals.append({"id": r["id"], "prompt": prompt, "gold": answer})
        if len(evals) >= FINQA_EVAL:
            break
    return rows, evals


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def split_holdout(rows: list[dict], rng: random.Random) -> tuple[list[dict], list[dict]]:
    by_source: dict[str, list[dict]] = {}
    for row in rows:
        by_source.setdefault(row["source"], []).append(row)
    train, hold = [], []
    for source, items in by_source.items():
        rng.shuffle(items)
        k = max(1, int(round(HOLDOUT * len(items))))
        hold.extend(items[:k])
        train.extend(items[k:])
    rng.shuffle(train)
    rng.shuffle(hold)
    return train, hold


def main() -> None:
    rng = random.Random(SEED)
    tok = _tok()
    print("loading Sujet subset …")
    sujet = load_sujet(rng)
    print("loading FinQA …")
    finqa, finqa_eval = load_finqa(rng, tok)
    indian = [_row(r["question"], r["answer"], "indian_qa", {"topic": r["topic"], "source_note": r["source"]})
              for r in load_jsonl(ML_DATA / "indian_finance_qa.jsonl")]
    refusals = [_row(r["prompt"], r["answer"], "refusal", {"template": r["template"]})
                for r in load_jsonl(ML_DATA / "refusals.jsonl")]
    rows = sujet + finqa + indian + refusals

    # token-length filter on the rendered chat (everything must fit the 1,024-token training window)
    kept, dropped = [], Counter()
    for row in rows:
        text = tok.apply_chat_template(row["messages"], tokenize=False, enable_thinking=False)
        n = len(tok(text)["input_ids"])
        if n <= MAX_TOKENS:
            row["meta"]["tokens"] = n
            kept.append(row)
        else:
            dropped[row["source"]] += 1
    train, hold = split_holdout(kept, rng)

    # evaluation prompt sets from the router's hand-written rows (never seen by the SFT)
    router = load_jsonl(ML_DATA / "fin_router.jsonl")
    hand = [r for r in router if r.get("source") == "hand"]
    offtopic = [r["text"] for r in hand if r["label"] == "out_of_scope"]
    finance = [r["text"] for r in hand if r["label"] in ("explain", "spending", "market", "advice", "documents")]
    rng.shuffle(offtopic)
    rng.shuffle(finance)
    # top up the off-topic set with held-out refusal prompts, then templated router rows, so it reaches 100
    offtopic_eval = offtopic[:100]
    for row in hold:
        if len(offtopic_eval) >= 100:
            break
        if row["source"] == "refusal":
            offtopic_eval.append(row["messages"][1]["content"])
    templated = [r["text"] for r in router if r.get("source") != "hand" and r["label"] == "out_of_scope"]
    rng.shuffle(templated)
    seen = {p.lower() for p in offtopic_eval}
    for text in templated:
        if len(offtopic_eval) >= 100:
            break
        if text.lower() not in seen:
            offtopic_eval.append(text)
            seen.add(text.lower())
    finance_eval = finance[:100]
    for row in hold:
        if len(finance_eval) >= 100:
            break
        if row["source"] == "indian_qa":
            finance_eval.append(row["messages"][1]["content"])
    judge_pool = [r for r in hold if r["source"] in ("indian_qa", "sujet_qa", "sujet_qa_with_context", "sujet_conversation")]
    rng.shuffle(judge_pool)
    judge_eval = [{"prompt": r["messages"][1]["content"], "reference": r["messages"][2]["content"], "source": r["source"]}
                  for r in judge_pool[:JUDGE_EVAL]]

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "train.jsonl", train)
    write_jsonl(OUT / "holdout.jsonl", hold)
    write_jsonl(OUT / "finqa_eval.jsonl", finqa_eval)
    write_jsonl(OUT / "offtopic_eval.jsonl", [{"prompt": p} for p in offtopic_eval])
    write_jsonl(OUT / "finance_eval.jsonl", [{"prompt": p} for p in finance_eval])
    write_jsonl(OUT / "judge_eval.jsonl", judge_eval)
    stats = {
        "train": len(train), "holdout": len(hold), "bySourceTrain": dict(Counter(r["source"] for r in train)),
        "bySourceHoldout": dict(Counter(r["source"] for r in hold)), "droppedOverLength": dict(dropped),
        "tokensMean": round(sum(r["meta"]["tokens"] for r in train) / max(1, len(train)), 1),
        "tokensMax": max(r["meta"]["tokens"] for r in train), "finqaEval": len(finqa_eval),
        "offtopicEval": len(offtopic_eval), "financeEval": len(finance_eval), "judgeEval": len(judge_eval),
        "maxTokens": MAX_TOKENS, "holdoutFraction": HOLDOUT, "seed": SEED,
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
