"""Train and evaluate Sphura's finance intent router (the `classify` node of the LangGraph).

Pipeline
  data      ml/data/fin_router.jsonl (ml/router_data.py; 6 labels, templated + hand-written boundary cases)
  features  BAAI/bge-small-en-v1.5 passage embeddings (384-d, L2-normalised) — the production RAG embedder,
            so the router adds no model download (app/features/router/model.py::embed_texts)
  model     multinomial LogisticRegression; C picked by 5-fold stratified CV (macro-F1) on the training split
  eval      stratified 80/20 hold-out: accuracy, macro-F1, per-class P/R/F1, confusion matrix; keyword-rules and
            TF-IDF + LR baselines; accuracy on the hand-written subset; 5-fold "unseen template" group CV
  deploy    refit on all rows → ml/artifacts/fin_router.joblib (read by app/agent/classify.py and
            app/features/router/model.py); ModelCard → ml/artifacts/fin_router/report.json + confusion.png

Run from backend/:  .venv/Scripts/python -m ml.train_router
"""
from __future__ import annotations

import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

if __package__ in (None, ""):  # allow `python ml/train_router.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from ml import reports, router_data  # noqa: E402

SEED = 42
TEST_SIZE = 0.2
C_GRID = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
CV_FOLDS = 5
ROUTER_THRESHOLD = 0.6
MODEL_NAME = "Logistic regression on bge-small embeddings"
LABELS = router_data.LABELS
KEY = "router"

# Tiny ordered keyword rules used only when app.agent.classify is unavailable (the real app fallback is
# `app.agent.classify.keyword_classify`, which is the preferred baseline).
_FALLBACK_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("out_of_scope", re.compile(r"\b(python|javascript|code|recipe|cook|match|cricket|homework|essay|weather|joke|"
                                r"movie|trip|poem|translate)\b", re.I)),
    ("advice", re.compile(r"\b(should i|which .* (?:should|to) (?:i )?buy|recommend|best .* to (?:buy|invest)|"
                          r"where should i invest|good buy|tip)\b", re.I)),
    ("spending", re.compile(r"\b(my (?:money|spending|expenses|statement|salary|budget)|spent|spend|where did my "
                            r"money|subscriptions i|save \d|recurring)\b", re.I)),
    ("documents", re.compile(r"\b(uploaded|attached|this (?:document|file|pdf|report|invoice|policy)|balance "
                             r"sheet|p&l|annual report|invoice|clause|page \d)\b", re.I)),
    ("market", re.compile(r"\b(price|share|stock|nifty|sensex|news|nav|rate today|today|live|results|usd|inr|"
                          r"gold|bitcoin)\b", re.I)),
]


def keyword_baseline(text: str) -> str:
    """The app's keyword classifier (app.agent.classify) when importable, else the small rule list above."""
    try:
        from app.agent.classify import keyword_classify

        return keyword_classify(text).intent
    except Exception:  # noqa: BLE001 — the backend module is owned by another engineer and may be mid-change
        for label, pattern in _FALLBACK_RULES:
            if pattern.search(text):
                return label
        return "explain"


def _logreg(c: float):
    from sklearn.linear_model import LogisticRegression

    return LogisticRegression(C=c, max_iter=5000, class_weight="balanced")


def _tfidf_fit_predict(train_texts: list[str], train_y: np.ndarray, test_texts: list[str]) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    clf = _logreg(10.0).fit(vectorizer.fit_transform(train_texts), train_y)
    return clf.predict(vectorizer.transform(test_texts))


def train(write: bool = True, log: Callable[[str], None] = print) -> dict:
    """Train, evaluate and (when `write`) save the router artifacts. Returns the ModelCard dict."""
    import joblib
    from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold, StratifiedKFold, train_test_split

    from app.core.config import settings
    from app.features.router import model as router_model

    started = time.perf_counter()
    rows = router_data.load()
    texts = [r["text"] for r in rows]
    y = np.array([r["label"] for r in rows])
    hand = np.array([r.get("source") == "hand" for r in rows])
    groups = np.array([r.get("template") or f"row:{i}" for i, r in enumerate(rows)])
    log(f"dataset: {len(rows)} examples, {int(hand.sum())} hand-written")

    t0 = time.perf_counter()
    X = router_model.embed_texts(texts)
    log(f"embedded {len(texts)} texts with {settings.embedding_model} in {time.perf_counter() - t0:.1f}s")

    idx = np.arange(len(rows))
    train_idx, test_idx = train_test_split(idx, test_size=TEST_SIZE, stratify=y, random_state=SEED)
    X_tr, X_te, y_tr, y_te = X[train_idx], X[test_idx], y[train_idx], y[test_idx]

    search = GridSearchCV(_logreg(1.0), {"C": C_GRID}, scoring="f1_macro",
                          cv=StratifiedKFold(CV_FOLDS, shuffle=True, random_state=SEED), n_jobs=1)
    search.fit(X_tr, y_tr)
    best_c = float(search.best_params_["C"])
    cv_scores = {str(c): reports.r4(s) for c, s in zip(C_GRID, search.cv_results_["mean_test_score"])}
    log(f"CV macro-F1 by C: {cv_scores} -> C={best_c}")

    clf = _logreg(best_c).fit(X_tr, y_tr)
    pred = clf.predict(X_te)
    y_te_l, pred_l = list(y_te), list(pred)
    main = reports.scores(y_te_l, pred_l, LABELS)

    base_all = np.array([keyword_baseline(t) for t in texts])
    baseline = reports.scores(y_te_l, list(base_all[test_idx]), LABELS)
    tfidf_pred = _tfidf_fit_predict([texts[i] for i in train_idx], y_tr, [texts[i] for i in test_idx])
    tfidf = reports.scores(y_te_l, list(tfidf_pred), LABELS)

    hard_mask = hand[test_idx]
    hard_acc = reports.r4(np.mean(pred[hard_mask] == y_te[hard_mask])) if hard_mask.any() else None

    # generalisation to new phrasing: whole templates held out per fold (hand-written rows are their own groups)
    oof = np.empty(len(rows), dtype=object)
    oof_tfidf = np.empty(len(rows), dtype=object)
    for fold_train, fold_test in StratifiedGroupKFold(CV_FOLDS, shuffle=True, random_state=SEED).split(X, y, groups):
        oof[fold_test] = _logreg(best_c).fit(X[fold_train], y[fold_train]).predict(X[fold_test])
        oof_tfidf[fold_test] = _tfidf_fit_predict([texts[i] for i in fold_train], y[fold_train],
                                                  [texts[i] for i in fold_test])
    unseen = reports.scores(list(y), list(oof), LABELS)
    unseen_tfidf = reports.scores(list(y), list(oof_tfidf), LABELS)
    unseen_base = reports.scores(list(y), list(base_all), LABELS)  # rules have nothing to fit: all rows are unseen

    final = _logreg(best_c).fit(X, y)
    latencies = []
    for text in [texts[i] for i in test_idx[:40]]:
        t = time.perf_counter()
        final.predict_proba(router_model.embed_texts([text]))
        latencies.append((time.perf_counter() - t) * 1000)
    latencies = latencies[5:] or [0.0]

    # how often the deployed threshold would fall back to keywords on the test split
    conf = clf.predict_proba(X_te).max(axis=1)
    covered = reports.r4(np.mean(conf >= ROUTER_THRESHOLD))

    trained_at = reports.now_iso()
    card = reports.card(
        KEY, name="Finance intent router", task="6-way intent classification (spending / documents / market / "
        "explain / advice / out_of_scope)", model=MODEL_NAME, trained_at=trained_at,
        dataset={"name": "fin_router.jsonl (templated + hand-written, project-authored)", "train": int(len(train_idx)),
                 "test": int(len(test_idx)), "license": "Project-authored (same licence as the repository)",
                 "note": f"{len(rows)} examples: {int(hand.sum())} hand-written boundary cases + templated "
                         f"messages; test = stratified 20 % hold-out; see ml/data/README.md"},
        y_true=y_te_l, y_pred=pred_l, labels=LABELS,
        baseline={"name": "Keyword rules (app.agent.classify)", **baseline},
        extras={"unseenTemplatesAccuracy": unseen["accuracy"], "unseenTemplatesMacroF1": unseen["macroF1"],
                "hardSubsetAccuracy": hard_acc if hard_acc is not None else -1.0,
                "hardSubsetSize": float(int(hard_mask.sum())), "tfidfLrAccuracy": tfidf["accuracy"],
                "tfidfLrMacroF1": tfidf["macroF1"], "bestC": best_c, "routerThreshold": ROUTER_THRESHOLD,
                "coverageAtThreshold": covered, "latencyMsP50": reports.r4(np.percentile(latencies, 50)),
                "latencyMsP95": reports.r4(np.percentile(latencies, 95)),
                "trainingSeconds": reports.r4(time.perf_counter() - started)},
    )
    card["ablation"] = [
        {"name": "Keyword rules (app.agent.classify)", **baseline, "unseenTemplatesAccuracy": unseen_base["accuracy"],
         "unseenTemplatesMacroF1": unseen_base["macroF1"]},
        {"name": "TF-IDF (1-2 grams) + logistic regression", **tfidf,
         "unseenTemplatesAccuracy": unseen_tfidf["accuracy"], "unseenTemplatesMacroF1": unseen_tfidf["macroF1"]},
        {"name": MODEL_NAME, **main, "unseenTemplatesAccuracy": unseen["accuracy"],
         "unseenTemplatesMacroF1": unseen["macroF1"]},
    ]
    card["hyperparameters"] = {"C": best_c, "grid": C_GRID, "cvFolds": CV_FOLDS, "cvMacroF1ByC": cv_scores,
                               "classWeight": "balanced", "embedding": settings.embedding_model}
    card["unseenTemplates"] = {"folds": CV_FOLDS, **unseen}
    log(f"test: accuracy {main['accuracy']:.4f} macro-F1 {main['macroF1']:.4f} | keywords {baseline['accuracy']:.4f}/"
        f"{baseline['macroF1']:.4f} | tf-idf {tfidf['accuracy']:.4f}/{tfidf['macroF1']:.4f} | hard subset "
        f"{hard_acc} (n={int(hard_mask.sum())}) | unseen templates {unseen['accuracy']:.4f}/{unseen['macroF1']:.4f} "
        f"(tf-idf {unseen_tfidf['accuracy']:.4f}, keywords {unseen_base['accuracy']:.4f}) "
        f"| coverage@{ROUTER_THRESHOLD} {covered:.3f} | latency p50 {card['extras']['latencyMsP50']} ms")

    if write:
        out_dir = reports.artifact_dir(KEY)
        out_dir.mkdir(parents=True, exist_ok=True)
        bundle = {"model": final, "labels": LABELS, "model_name": MODEL_NAME, "embedding_model": settings.embedding_model,
                  "trained_at": trained_at, "C": best_c, "threshold": ROUTER_THRESHOLD, "version": 2}
        tmp = router_model.MODEL_PATH.with_suffix(".joblib.tmp")
        joblib.dump(bundle, tmp)
        tmp.replace(router_model.MODEL_PATH)
        reports.write_json(out_dir / "report.json", card)
        router_model.reload()
        if not reports.confusion_png(card["confusion"], LABELS, f"Finance intent router — held-out test (n="
                                     f"{len(test_idx)})\naccuracy {main['accuracy']:.1%} · macro-F1 "
                                     f"{main['macroF1']:.3f}", out_dir / "confusion.png"):
            log("matplotlib is not installed; skipped the confusion-matrix chart")
        log(f"saved {router_model.MODEL_PATH.name} and {out_dir / 'report.json'}")
    return card


def main() -> None:
    router_data.save(router_data.build_dataset())  # always rebuild: the dataset is deterministic
    train()


if __name__ == "__main__":
    main()
