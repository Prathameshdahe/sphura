"""Financial sentiment dataset: Financial PhraseBank (50 % agreement) + Twitter Financial News Sentiment.

Sources (cached under training/data/raw/ by the training engineer; never re-downloaded here):
  * takala/financial_phrasebank — FinancialPhraseBank-v1.0.zip, `Sentences_50Agree.txt` (4,846 sentences;
    CC BY-NC-SA 3.0, academic use). Labels: positive / neutral / negative.
  * zeroshot/twitter-financial-news-sentiment — sent_train.csv (9,543) + sent_valid.csv (2,388); MIT.
    Labels 0 Bearish → negative, 1 Bullish → positive, 2 Neutral → neutral. `https://t.co/…` links are removed.

Splits (fixed seed, stratified by label within each source):
  * PhraseBank: 80 / 10 / 10 → train / val / test.
  * TFNS: the official validation file is our TEST set; 10 % of the official train file becomes val.
Rows: {"text", "label", "source": "fpb"|"tfns", "split"}; exact-duplicate texts are kept once and never
appear in two splits. Run from backend/:  .venv/Scripts/python -m ml.sentiment_data
"""
from __future__ import annotations

import csv
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

LABELS = ["negative", "neutral", "positive"]
SEED = 7
ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"
RAW_DIR = ML_DIR.parents[1] / "training" / "data" / "raw"
FPB_ZIP = RAW_DIR / "takala__financial_phrasebank" / "data" / "FinancialPhraseBank-v1.0.zip"
FPB_MEMBER = "FinancialPhraseBank-v1.0/Sentences_50Agree.txt"
TFNS_DIR = RAW_DIR / "zeroshot__twitter-financial-news-sentiment"
TFNS_LABELS = {"0": "negative", "1": "positive", "2": "neutral"}
PATHS = {split: DATA_DIR / f"sentiment_{split}.jsonl" for split in ("train", "val", "test")}
_URL = re.compile(r"https?://\S+")
_KEY = re.compile(r"[^a-z0-9]+")


def _key(text: str) -> str:
    return _KEY.sub(" ", text.lower()).strip()


def load_fpb() -> list[dict]:
    raw = zipfile.ZipFile(FPB_ZIP).read(FPB_MEMBER).decode("latin-1")
    rows = []
    for line in raw.splitlines():
        if "@" not in line:
            continue
        text, label = line.rsplit("@", 1)
        label = label.strip().lower()
        if label in LABELS and text.strip():
            rows.append({"text": " ".join(text.split()), "label": label, "source": "fpb"})
    return rows


def load_tfns(name: str) -> list[dict]:
    rows = []
    with (TFNS_DIR / name).open(encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            label = TFNS_LABELS.get(str(rec.get("label", "")).strip())
            text = " ".join(_URL.sub("", rec.get("text") or "").split())
            if label and text:
                rows.append({"text": text, "label": label, "source": "tfns"})
    return rows


def _dedupe(rows: list[dict], seen: set[str]) -> list[dict]:
    out = []
    for row in rows:
        key = _key(row["text"])
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _stratified(rows: list[dict], fractions: tuple[float, ...], seed: int) -> list[list[dict]]:
    """Split rows into len(fractions) parts, stratified by label (fractions sum to 1)."""
    import random

    rng = random.Random(seed)
    by_label: dict[str, list[dict]] = {}
    for row in rows:
        by_label.setdefault(row["label"], []).append(row)
    parts: list[list[dict]] = [[] for _ in fractions]
    for label in LABELS:
        items = by_label.get(label, [])
        rng.shuffle(items)
        start = 0
        for i, frac in enumerate(fractions):
            end = len(items) if i == len(fractions) - 1 else start + int(round(frac * len(items)))
            parts[i].extend(items[start:end])
            start = end
    for part in parts:
        rng.shuffle(part)
    return parts


def build() -> dict[str, list[dict]]:
    seen: set[str] = set()
    tfns_test = _dedupe(load_tfns("sent_valid.csv"), seen)   # the official validation file is our test set
    tfns_train, tfns_val = _stratified(_dedupe(load_tfns("sent_train.csv"), seen), (0.9, 0.1), SEED)
    fpb_train, fpb_val, fpb_test = _stratified(_dedupe(load_fpb(), seen), (0.8, 0.1, 0.1), SEED)
    splits = {"train": fpb_train + tfns_train, "val": fpb_val + tfns_val, "test": fpb_test + tfns_test}
    import random

    rng = random.Random(SEED)
    for split, rows in splits.items():
        rng.shuffle(rows)
        for row in rows:
            row["split"] = split
    return splits


def save(splits: dict[str, list[dict]]) -> None:
    from ml.reports import write_jsonl

    for split, rows in splits.items():
        write_jsonl(PATHS[split], rows)


def load(split: str) -> list[dict]:
    from ml.reports import read_jsonl

    path = PATHS[split]
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing — run `python -m ml.sentiment_data` first")
    return read_jsonl(path)


def main() -> None:
    splits = build()
    save(splits)
    for split, rows in splits.items():
        by_source = Counter(r["source"] for r in rows)
        by_label = Counter(r["label"] for r in rows)
        print(f"{split:5s} {len(rows):6d} rows  {dict(by_source)}  {dict(by_label)} -> {PATHS[split].name}")


if __name__ == "__main__":
    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
