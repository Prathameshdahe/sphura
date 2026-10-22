"""TF-IDF baseline for financial sentiment (the DistilBERT rung is training/classifiers/train_bert.py).

Data   ml/data/sentiment_{train,val,test}.jsonl (ml/sentiment_data.py: PhraseBank 50 % agreement + TFNS)
Model  word 1-2 grams + char_wb 2-5 grams TF-IDF, logistic regression (C by 3-fold CV on train)
Eval   the combined test set, plus PhraseBank-only and TFNS-only accuracy; the lexicon in
       app.features.market.sentiment is the baseline
Saves  artifacts/sentiment/sklearn.joblib (fallback when the ONNX model is absent) + report_sklearn.json

Run from backend/:  .venv/Scripts/python -m ml.train_sentiment
"""
from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml import reports, sentiment_data  # noqa: E402

KEY = "sentiment"
SEED = 42
C_GRID = [1.0, 4.0, 16.0]
LABELS = sentiment_data.LABELS
TFIDF_NAME = "TF-IDF (word 1-2 + char 2-5 grams) + logistic regression"
DATASET = {"name": "Financial PhraseBank (sentences_50agree) + Twitter Financial News Sentiment",
           "license": "PhraseBank CC BY-NC-SA 3.0 (academic use); TFNS MIT"}


def lexicon_predict(texts: list[str]) -> list[str]:
    try:
        from app.features.market.sentiment import lexicon

        return [lexicon(t)[0] for t in texts]
    except Exception:  # noqa: BLE001 — the market feature belongs to another engineer
        return ["neutral"] * len(texts)


def tfidf_pipeline(c: float):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=3)),
    ])
    return Pipeline([("features", features),
                     ("clf", LogisticRegression(C=c, max_iter=3000, class_weight="balanced"))])


def per_source(rows: list[dict], pred: list[str]) -> dict[str, float]:
    out = {}
    for source in ("fpb", "tfns"):
        idx = [i for i, r in enumerate(rows) if r["source"] == source]
        if idx:
            s = reports.scores([rows[i]["label"] for i in idx], [pred[i] for i in idx], LABELS)
            out[f"{source}Accuracy"], out[f"{source}MacroF1"] = s["accuracy"], s["macroF1"]
    return out


def train(write: bool = True, log: Callable[[str], None] = print) -> dict:
    import joblib
    from sklearn.model_selection import GridSearchCV, StratifiedKFold

    started = time.perf_counter()
    train_rows, test_rows = sentiment_data.load("train"), sentiment_data.load("test")
    x_tr, y_tr = [r["text"] for r in train_rows], [r["label"] for r in train_rows]
    x_te, y_te = [r["text"] for r in test_rows], [r["label"] for r in test_rows]
    log(f"train {len(train_rows)} rows, test {len(test_rows)} rows")

    baseline_pred = lexicon_predict(x_te)
    baseline = reports.scores(y_te, baseline_pred, LABELS)
    log(f"lexicon baseline: {baseline} {per_source(test_rows, baseline_pred)}")

    search = GridSearchCV(tfidf_pipeline(1.0), {"clf__C": C_GRID}, scoring="f1_macro",
                          cv=StratifiedKFold(3, shuffle=True, random_state=SEED), n_jobs=1)
    search.fit(x_tr, y_tr)
    best_c = float(search.best_params_["clf__C"])
    pipeline = tfidf_pipeline(best_c).fit(x_tr, y_tr)
    pred = [str(p) for p in pipeline.predict(x_te)]
    main = reports.scores(y_te, pred, LABELS)
    sources = per_source(test_rows, pred)
    log(f"tf-idf + LR (C={best_c}): {main} {sources}")

    trained_at = reports.now_iso()
    card = reports.card(
        KEY, name="Financial sentiment (sklearn fallback)", task="3-way sentiment of finance headlines / sentences",
        model=TFIDF_NAME, trained_at=trained_at,
        dataset={**DATASET, "train": len(train_rows), "test": len(test_rows),
                 "note": "test = PhraseBank 10 % stratified hold-out + the official TFNS validation file; "
                         "see ml/data/README.md"},
        y_true=y_te, y_pred=pred, labels=LABELS,
        baseline={"name": "Lexicon (app.features.market.sentiment)", **baseline},
        extras={**sources, "bestC": best_c, "trainingSeconds": reports.r4(time.perf_counter() - started)},
    )
    card["ablation"] = [{"name": "Lexicon (app.features.market.sentiment)", **baseline,
                         **per_source(test_rows, baseline_pred)}, {"name": TFIDF_NAME, **main, **sources}]
    if write:
        out_dir = reports.artifact_dir(KEY)
        out_dir.mkdir(parents=True, exist_ok=True)
        bundle = {"pipeline": pipeline, "labels": LABELS, "model_name": TFIDF_NAME, "trained_at": trained_at,
                  "C": best_c, "version": 1}
        tmp = out_dir / "sklearn.joblib.tmp"
        joblib.dump(bundle, tmp)
        tmp.replace(out_dir / "sklearn.joblib")
        reports.write_json(out_dir / "report_sklearn.json", card)
        try:
            from app.features.sentiment import model as sentiment_model

            sentiment_model.reset()
        except Exception:  # noqa: BLE001
            pass
        log(f"saved {out_dir / 'sklearn.joblib'} and report_sklearn.json")
    return card


def main() -> None:
    if not all(p.exists() for p in sentiment_data.PATHS.values()):
        sentiment_data.save(sentiment_data.build())
    train()


if __name__ == "__main__":
    main()
