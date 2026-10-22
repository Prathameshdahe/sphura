"""The sklearn rungs of the transaction-categoriser ladder (the DistilBERT rung is training/classifiers/).

Ladder (all scored on the author-labelled test set, ml/data/categoriser_test.jsonl):
  0. rules      app.features.finance.categorize.rules_category (the pre-ML categoriser) — the baseline
  1. TF-IDF+LR  word 1-2 grams + char_wb 2-5 grams, multinomial logistic regression (C by 3-fold CV)
  2. bge+LR     BAAI/bge-small-en-v1.5 embeddings of the narration + logistic regression
  3. DistilBERT fine-tune (GPU; training/classifiers/train_bert.py --task categoriser) → ONNX

Rung 1 is saved as the in-app fallback (`artifacts/categoriser/sklearn.joblib`, self-contained, no embedder)
and its ModelCard as `report_sklearn.json`; rung 2 is reported as an ablation. The DistilBERT trainer writes
`report.json` (the deployed card) and copies the numbers below into its ablation table.

Run from backend/:  .venv/Scripts/python -m ml.train_categoriser
"""
from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from ml import categoriser_data as cd  # noqa: E402
from ml import reports  # noqa: E402

KEY = "categoriser"
SEED = 42
C_GRID = [1.0, 4.0, 16.0]
LABELS = cd.LABELS
DISPLAY_TO_LABEL = {v: k for k, v in cd.DISPLAY.items()}
TFIDF_NAME = "TF-IDF (word 1-2 + char 2-5 grams) + logistic regression"
BGE_NAME = "Logistic regression on bge-small embeddings"
DATASET = {"name": "categoriser_train.jsonl (generated Indian narrations + demo statement) / categoriser_test.jsonl "
                   "(author-labelled)", "license": "Project-authored (same licence as the repository)"}


def rules_predict(rows: list[dict]) -> list[str]:
    """The rule categoriser mapped onto the 14 model labels ('Other', 'Refunds', 'Interest' count as wrong)."""
    from app.features.finance.categorize import rules_category

    out = []
    for row in rows:
        amount = row["amount"] if row["direction"] == "credit" else -row["amount"]
        out.append(DISPLAY_TO_LABEL.get(rules_category(row["text"], amount), "other"))
    return out


def tfidf_pipeline(c: float):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1, token_pattern=r"[A-Za-z0-9@.]+")),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)),
    ])
    return Pipeline([("features", features),
                     ("clf", LogisticRegression(C=c, max_iter=3000, class_weight="balanced"))])


def train(write: bool = True, log: Callable[[str], None] = print) -> dict:
    """Fit the sklearn rungs, score them on the author test set, save rung 1 + report_sklearn.json."""
    import joblib
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GridSearchCV, StratifiedKFold

    from app.core.config import settings
    from app.features.router import model as router_model

    started = time.perf_counter()
    train_rows, test_rows = cd.load(cd.TRAIN_PATH), cd.load(cd.TEST_PATH)
    x_tr, x_te = [cd.model_text(r) for r in train_rows], [cd.model_text(r) for r in test_rows]
    y_tr, y_te = [r["label"] for r in train_rows], [r["label"] for r in test_rows]
    log(f"train {len(train_rows)} rows, test {len(test_rows)} rows (author-labelled)")

    baseline = reports.scores(y_te, rules_predict(test_rows), LABELS)
    log(f"rules baseline: {baseline}")

    search = GridSearchCV(tfidf_pipeline(1.0), {"clf__C": C_GRID}, scoring="f1_macro",
                          cv=StratifiedKFold(3, shuffle=True, random_state=SEED), n_jobs=1)
    search.fit(x_tr, y_tr)
    best_c = float(search.best_params_["clf__C"])
    pipeline = tfidf_pipeline(best_c).fit(x_tr, y_tr)
    tfidf_pred = [str(p) for p in pipeline.predict(x_te)]
    tfidf = reports.scores(y_te, tfidf_pred, LABELS)
    log(f"tf-idf + LR (C={best_c}): {tfidf}")

    t0 = time.perf_counter()
    e_tr, e_te = router_model.embed_texts(x_tr), router_model.embed_texts(x_te)
    log(f"embedded {len(x_tr) + len(x_te)} narrations with {settings.embedding_model} in {time.perf_counter() - t0:.0f}s")
    bge_clf = LogisticRegression(C=8.0, max_iter=5000, class_weight="balanced").fit(e_tr, y_tr)
    bge_pred = [str(p) for p in bge_clf.predict(e_te)]
    bge = reports.scores(y_te, bge_pred, LABELS)
    log(f"bge-small + LR: {bge}")

    sample_mask = np.array([r["source"] == "sample" for r in train_rows])
    trained_at = reports.now_iso()
    card = reports.card(
        KEY, name="Transaction categoriser (sklearn fallback)", task="14-way bank-narration classification",
        model=TFIDF_NAME, trained_at=trained_at,
        dataset={**DATASET, "train": len(train_rows), "test": len(test_rows),
                 "note": f"{int((~sample_mask).sum())} generated + {int(sample_mask.sum())} demo-statement rows; "
                         f"test rows were written and labelled by the author (see ml/data/README.md)"},
        y_true=y_te, y_pred=tfidf_pred, labels=LABELS,
        baseline={"name": "Rules (app.features.finance.categorize)", **baseline},
        extras={"bgeSmallLrAccuracy": bge["accuracy"], "bgeSmallLrMacroF1": bge["macroF1"], "bestC": best_c,
                "trainingSeconds": reports.r4(time.perf_counter() - started)},
    )
    card["ablation"] = [{"name": "Rules (app.features.finance.categorize)", **baseline},
                        {"name": TFIDF_NAME, **tfidf}, {"name": BGE_NAME, **bge}]
    if write:
        out_dir = reports.artifact_dir(KEY)
        out_dir.mkdir(parents=True, exist_ok=True)
        bundle = {"pipeline": pipeline, "labels": LABELS, "display": cd.DISPLAY, "model_name": TFIDF_NAME,
                  "trained_at": trained_at, "C": best_c, "version": 1}
        tmp = out_dir / "sklearn.joblib.tmp"
        joblib.dump(bundle, tmp)
        tmp.replace(out_dir / "sklearn.joblib")
        reports.write_json(out_dir / "labels.json", {"labels": LABELS, "display": cd.DISPLAY})
        reports.write_json(out_dir / "report_sklearn.json", card)
        try:
            from app.features.finance import categoriser_model

            categoriser_model.reset()
        except Exception:  # noqa: BLE001
            pass
        log(f"saved {out_dir / 'sklearn.joblib'} and report_sklearn.json")
    return card


def main() -> None:
    cd.save(cd.build_train(), cd.TRAIN_PATH)
    cd.save(cd.build_test(), cd.TEST_PATH)
    train()


if __name__ == "__main__":
    main()
