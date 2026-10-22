"""Finance ML: datasets, trained artifacts (router / categoriser / sentiment), loaders with fallbacks, /api/ml."""
from __future__ import annotations

import asyncio
import json
import math
import shutil
import threading
import time
import uuid
from pathlib import Path

import pytest

from app.db.base import session_scope
from app.db.models import Conversation, Message, User
from app.features.finance import categoriser_model, categorize
from app.features.router import model as router_model
from app.features.router import plugin as router_plugin
from app.features.sentiment import model as sentiment_model
from ml import categoriser_data, indian_qa, reports, router_data, sentiment_data

LABELS = ["spending", "documents", "market", "explain", "advice", "out_of_scope"]
MODEL_KEYS = ["categoriser", "sentiment", "router"]


def _make_admin(user: dict) -> None:
    with session_scope() as db:
        db.get(User, user["user"]["id"]).is_admin = True


# ── datasets ─────────────────────────────────────────────────────────────────
def test_router_dataset_is_deterministic_and_committed():
    rows = router_data.build_dataset()
    assert rows == router_data.build_dataset() == router_data.load()
    assert router_data.LABELS == LABELS
    counts = {label: sum(r["label"] == label for r in rows) for label in LABELS}
    assert len(rows) >= 1700 and min(counts.values()) >= 250 and counts["out_of_scope"] >= 300
    assert sum(r["source"] == "hand" for r in rows) >= 200
    keys = [router_data._key(r["text"]) for r in rows]
    assert len(keys) == len(set(keys)), "examples must be de-duplicated"


def test_categoriser_dataset_is_committed_and_leak_free():
    train, test = categoriser_data.build_train(), categoriser_data.build_test()
    assert train == categoriser_data.load(categoriser_data.TRAIN_PATH)
    assert test == categoriser_data.load(categoriser_data.TEST_PATH)
    assert len(categoriser_data.LABELS) == 14 and len(train) >= 6000 and len(test) >= 400
    assert {r["label"] for r in test} == set(categoriser_data.LABELS)
    assert all(r["source"] == "author" for r in test)
    train_keys = {categoriser_data._key(r["text"]) for r in train}
    assert not any(categoriser_data._key(r["text"]) in train_keys for r in test)
    assert categoriser_data.model_text({"direction": "debit", "text": "UPI-ZEPTO"}) == categoriser_model.model_text("UPI-ZEPTO", "debit")


def test_sentiment_splits_are_stratified_and_leak_free():
    train, val, test = (sentiment_data.load(s) for s in ("train", "val", "test"))
    assert len(train) >= 10000 and len(test) >= 2500
    assert {r["label"] for r in test} == set(sentiment_data.LABELS)
    assert {r["source"] for r in test} == {"fpb", "tfns"}
    train_keys = {sentiment_data._key(r["text"]) for r in train}
    assert not any(sentiment_data._key(r["text"]) in train_keys for r in test + val)


def test_indian_qa_and_refusals_are_valid():
    counts = indian_qa.check()
    assert counts["qa"] >= 300 and counts["refusals"] >= 150 and counts["topics"] >= 10
    qa = reports.read_jsonl(indian_qa.QA_PATH)
    assert len(qa) == counts["qa"] and all(r["source"] and r["answer"] and r["question"] for r in qa)
    refusals = reports.read_jsonl(indian_qa.REFUSALS_PATH)
    assert len(refusals) == counts["refusals"] and all("not about finance" in r["answer"] for r in refusals)


# ── router artifact and plugin API ───────────────────────────────────────────
def test_router_predicts_the_finance_intents():
    expectations = {
        "where did my money go last month?": "spending",
        "TCS share price today": "market",
        "what is a SIP?": "explain",
        "should I buy Reliance?": "advice",
        "recipe for biryani": "out_of_scope",
        "write a Python script": "out_of_scope",
        "what is the current ratio in the balance sheet I uploaded?": "documents",
    }
    for text, label in expectations.items():
        pred = router_model.predict(text)
        assert pred is not None and pred.label == label, (text, pred)
        assert set(pred.probabilities) == set(LABELS)
        assert math.isclose(sum(pred.probabilities.values()), 1.0, abs_tol=1e-2)
        assert pred.confidence == max(pred.probabilities.values())


def test_router_plugin_route_marks_market_turns_for_auto_search():
    market = asyncio.run(router_plugin.route("news about HDFC Bank"))
    assert market is not None and market.label == "market" and market.auto_search is True
    assert market.meta() == {"label": "market", "confidence": market.confidence, "autoSearch": True}
    explain = asyncio.run(router_plugin.route("how does 80C work?"))
    assert explain is not None and explain.label == "explain" and explain.auto_search is False


def test_router_ignores_an_artifact_trained_on_another_embedder(monkeypatch, tmp_path):
    import joblib

    path = tmp_path / "fin_router.joblib"
    joblib.dump({**joblib.load(router_model.MODEL_PATH), "embedding_model": "some/other-embedder"}, path)
    monkeypatch.setattr(router_model, "MODEL_PATH", path)
    router_model.reload()
    try:
        assert router_model.load() is None and router_model.predict("TCS share price today") is None
    finally:
        router_model.reload()


def test_router_is_absent_without_an_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(router_model, "MODEL_PATH", tmp_path / "missing.joblib")
    router_model.reload()
    try:
        assert not router_model.available() and router_model.predict("hi") is None
        assert asyncio.run(router_plugin.route("TCS share price today")) is None
    finally:
        router_model.reload()


# ── categoriser loader and fallbacks ─────────────────────────────────────────
@pytest.fixture
def categoriser_dir(monkeypatch):
    def use(path: Path) -> None:
        monkeypatch.setattr(categoriser_model, "ARTIFACT_DIR", path)
        categoriser_model.reset()

    yield use
    monkeypatch.setattr(categoriser_model, "ARTIFACT_DIR", categoriser_model.artifact_dir.__globals__["BACKEND_DIR"]
                        / "ml" / "artifacts" / "categoriser")
    categoriser_model.reset()


def test_categoriser_model_is_loaded_and_beats_rules_on_unseen_merchants():
    assert categoriser_model.available()
    assert categoriser_model.backend_name() != "none"
    pred = categoriser_model.predict_one("UPI-RAMESHWARAM CAFE-rameshwaramcafe@icici-628812345708-UPI", "debit")
    assert pred is not None and pred[0] == "Dining" and 0 < pred[1] <= 1
    assert categorize.categorize("UPI-SRI LAKSHMI PROVISION STORES-q98765432@ybl-628812345685-sabzi", -320) == "Groceries"
    assert categorize.rules_category("UPI-SRI LAKSHMI PROVISION STORES-q98765432@ybl-628812345685-sabzi", -320) == "Shopping"


def test_categorize_keeps_credit_only_rules_and_rule_fallback():
    assert categorize.categorize("REFUND-AMAZON", 999) == "Refunds"
    assert categorize.categorize("CREDIT INTEREST CAPITALISED", 1200) == "Interest"
    assert categorize.categorize("NEFT CR-ACME LTD-SALARY APR", 85000) == "Salary"
    assert categorize.categorize("MYSTERY MERCHANT", -10) in categorize.CATEGORIES


def test_categoriser_falls_back_to_sklearn_then_rules(categoriser_dir, tmp_path):
    source = categoriser_model.ARTIFACT_DIR
    only_sklearn = tmp_path / "sklearn_only"
    only_sklearn.mkdir()
    for name in ("sklearn.joblib", "labels.json"):
        shutil.copy(source / name, only_sklearn / name)
    categoriser_dir(only_sklearn)
    assert categoriser_model.available() and "logistic" in categoriser_model.backend_name()
    assert categoriser_model.predict_one("UPI-SWIGGY-swiggy@icici", "debit")[0] == "Dining"

    categoriser_dir(tmp_path / "empty")
    assert not categoriser_model.available() and categoriser_model.backend_name() == "none"
    assert categoriser_model.predict_one("UPI-SWIGGY-swiggy@icici", "debit") is None
    assert categorize.categorize("UPI-SWIGGY-swiggy@icici", -320) == "Dining"   # rules still work
    assert categorize.categorize("UPI-SRI LAKSHMI PROVISION STORES-q98765432@ybl-628812345685-sabzi", -320) == "Shopping"


def test_categoriser_deploy_file_picks_the_backend(categoriser_dir, tmp_path):
    source = categoriser_model.ARTIFACT_DIR
    both = tmp_path / "both"
    shutil.copytree(source, both)
    (both / "deploy.json").write_text(json.dumps({"backend": "sklearn"}), encoding="utf-8")
    categoriser_dir(both)
    assert "logistic" in categoriser_model.backend_name()
    (both / "deploy.json").write_text(json.dumps({"backend": "onnx"}), encoding="utf-8")
    categoriser_dir(both)
    expected = "distilbert" if (both / "model_quantized.onnx").exists() or (both / "model.onnx").exists() else "logistic"
    assert expected in categoriser_model.backend_name()


# ── sentiment loader ─────────────────────────────────────────────────────────
def test_sentiment_label_and_shapes():
    assert sentiment_model.available()
    pos = sentiment_model.label("Shares surged 8% after the company posted record quarterly profits")
    neg = sentiment_model.label("The bank reported a huge loss and the stock plunged")
    assert set(pos) == {"label", "score"} and pos["label"] == "positive" and 0 < pos["score"] <= 1
    assert neg["label"] == "negative"
    many = sentiment_model.label_many(["Infosys beats estimates", "Markets closed flat"])
    assert len(many) == 2 and all(m["label"] in sentiment_model.LABELS for m in many)
    assert sentiment_model.predict([]) == []
    import app.features.sentiment as pkg

    assert callable(pkg.predict)  # what app.features.market.sentiment probes for


def test_sentiment_is_absent_without_an_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(sentiment_model, "ARTIFACT_DIR", tmp_path / "none")
    sentiment_model.reset()
    try:
        assert not sentiment_model.available() and sentiment_model.backend_name() == "none"
        with pytest.raises(LookupError):
            sentiment_model.predict(["anything"])
        import app.features.sentiment as pkg

        with pytest.raises(AttributeError):
            pkg.predict  # noqa: B018 — hidden so the markets lexicon takes over silently
    finally:
        monkeypatch.undo()
        sentiment_model.reset()


# ── /api/ml ──────────────────────────────────────────────────────────────────
def test_model_lab_report_shape(client, user):
    r = client.get("/api/ml/report", headers=user["headers"])
    assert r.status_code == 200, r.text
    rep = r.json()
    assert set(rep) == {"models", "finetune", "ragEval", "generatedAt"} and rep["generatedAt"].endswith("Z")
    keys = [m["key"] for m in rep["models"]]
    assert keys == [k for k in MODEL_KEYS if k in keys] and set(keys) == set(MODEL_KEYS)
    for card in rep["models"]:
        assert {"key", "name", "task", "model", "trainedAt", "dataset", "metrics", "labels", "perClass", "confusion"} <= set(card)
        n = len(card["labels"])
        assert len(card["confusion"]) == n and all(len(row) == n for row in card["confusion"])
        assert sum(map(sum, card["confusion"])) == card["dataset"]["test"] == sum(c["support"] for c in card["perClass"])
        assert [c["label"] for c in card["perClass"]] == card["labels"]
        assert 0 < card["metrics"]["accuracy"] <= 1 and 0 < card["metrics"]["macroF1"] <= 1
        assert {"name", "train", "test", "license", "note"} <= set(card["dataset"])
        if card.get("baseline"):
            assert card["metrics"]["macroF1"] > card["baseline"]["macroF1"]
    router = next(m for m in rep["models"] if m["key"] == "router")
    assert router["labels"] == LABELS and router["extras"]["unseenTemplatesMacroF1"] > 0.8
    assert rep["ragEval"]["available"] is True
    assert rep["finetune"] is None or {"available", "name", "base", "eval", "notes"} <= set(rep["finetune"])
    assert client.get("/api/ml/report").status_code == 401


def test_model_lab_report_without_artifacts(tmp_path):
    from app.api import ml as ml_api

    rep = ml_api.build_report(tmp_path)
    assert rep["models"] == [] and rep["finetune"] is None and rep["ragEval"] == {"available": False}
    (tmp_path / "finetune").mkdir()
    (tmp_path / "finetune" / "report.json").write_text(json.dumps({"available": False, "name": "sphura-fin-1.7b"}))
    assert ml_api.build_report(tmp_path)["finetune"]["available"] is False
    assert ml_api.model_card("router", tmp_path) is None


FINETUNE_EVAL_KEYS = {"heldoutPerplexityBase", "heldoutPerplexityTuned", "finqaEmBase", "finqaEmTuned", "refusalRate",
                      "falseRefusalRate", "judgeWinRate", "judgeModel", "mmluMiniBase", "mmluMiniTuned"}


def test_committed_finetune_report_matches_the_contract():
    """artifacts/finetune/report.json is a FinetuneReport (section 8); when `available` it carries real results."""
    from app.api import ml as ml_api

    rep = ml_api.finetune_report()
    assert rep is not None
    assert {"available", "name", "base", "method", "rows", "steps", "epochs", "trainMinutes", "gpu", "lora", "eval",
            "ollamaTag", "notes"} <= set(rep)
    assert set(rep["eval"]) == FINETUNE_EVAL_KEYS and {"r", "alpha", "targets"} <= set(rep["lora"])
    assert rep["name"] == "sphura-fin-1.7b" and isinstance(rep["notes"], list) and rep["notes"]
    for key, value in rep["eval"].items():
        if key != "judgeModel" and value is not None:
            assert isinstance(value, (int, float)) and value >= 0, key
    if rep["available"]:
        assert rep["steps"] > 0 and rep["trainMinutes"] > 0 and rep["rows"] > 0
        assert rep["eval"]["heldoutPerplexityBase"] and rep["eval"]["heldoutPerplexityTuned"]
        for key in ("finqaEmBase", "finqaEmTuned", "refusalRate", "falseRefusalRate"):
            assert 0 <= rep["eval"][key] <= 1, key
        assert (ml_api.ARTIFACT_DIR / "finetune" / "training_curve.png").exists()


def test_old_ml_routes_are_gone(client, user):
    for path in ("/api/ml/router", "/api/ml/rag-eval"):
        assert client.get(path, headers=user["headers"]).status_code == 404
    assert client.post("/api/ml/router/predict", json={"text": "x"}, headers=user["headers"]).status_code == 404


def test_train_endpoint_is_admin_only_and_wired(client, user, monkeypatch):
    r = client.post("/api/ml/train/router", headers=user["headers"])
    assert r.status_code == 403 and r.json() == {"detail": "Admin only"}
    assert client.post("/api/ml/train/router").status_code == 401
    _make_admin(user)
    assert client.post("/api/ml/train/nope", headers=user["headers"]).status_code == 404

    from ml import train_categoriser, train_router, train_sentiment

    fake = {"available": True, "metrics": {"accuracy": 0.9, "macroF1": 0.9}, "labels": ["a"], "ablation": [], "junk": 1}
    for module in (train_router, train_categoriser, train_sentiment):
        monkeypatch.setattr(module, "train", lambda write=True, log=print, fake=fake: fake)
    for key in MODEL_KEYS:
        body = client.post(f"/api/ml/train/{key}", headers=user["headers"]).json()
        assert body["key"] == key and body["metrics"] == fake["metrics"] and "junk" not in body


def test_train_job_conflicts_and_failures(client, user, monkeypatch):
    from app.api import ml as ml_api
    from ml import train_router

    _make_admin(user)
    lock = ml_api._jobs["router"]
    assert lock.acquire(blocking=False)
    try:
        r = client.post("/api/ml/train/router", headers=user["headers"])
        assert r.status_code == 409 and isinstance(r.json()["detail"], str)
    finally:
        lock.release()
    monkeypatch.setattr(train_router, "train", lambda write=True, log=print: 1 / 0)
    r = client.post("/api/ml/train/router", headers=user["headers"])
    assert r.status_code == 500 and r.json() == {"detail": "The job failed: ZeroDivisionError"}
    assert not lock.locked()


def test_job_lock_is_held_until_the_worker_finishes_even_if_the_request_drops():
    from app.api import ml as ml_api

    lock, gate = ml_api._jobs["sentiment"], threading.Event()

    def slow() -> dict:
        gate.wait(5)
        return {"available": True}

    async def scenario() -> None:
        task = asyncio.create_task(ml_api._run_job("sentiment", slow))
        await asyncio.sleep(0.05)
        task.cancel()  # the client went away
        with pytest.raises(asyncio.CancelledError):
            await task
        assert lock.locked()  # the training thread is still running: a second job must get 409
        gate.set()

    asyncio.run(scenario())  # waits for the worker thread on shutdown
    assert not lock.locked()


def test_verification_stats_over_own_answers(client, user, other_user):
    def add(meta):
        return Message(conversation_id=cid, role="assistant", content="x", status="complete", sources=[], steps=[],
                       attachments=[], meta=meta)

    cid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Conversation(id=cid, user_id=user["user"]["id"], title="v"))
        db.flush()
        db.add_all([
            add({"verification": {"score": 0.95, "label": "grounded"}}),
            add({"verification": {"score": 0.5, "label": "partially grounded"}}),
            add({"verification": {"score": 0.1, "label": "ungrounded"}}),
            add({"verification": {"score": 0.0, "label": "not checkable"}}),
            add({"durationMs": 5}),
            add(None),
        ])
    stats = client.get("/api/ml/verification", headers=user["headers"]).json()
    assert stats["answers"] == 4
    assert stats["labelCounts"] == {"grounded": 1, "partially grounded": 1, "ungrounded": 1, "not checkable": 1}
    assert stats["avgScore"] == pytest.approx((0.95 + 0.5 + 0.1) / 3, abs=1e-3)
    assert [h["count"] for h in stats["histogram"]] == [1, 0, 1, 0, 1]
    other = client.get("/api/ml/verification", headers=other_user["headers"]).json()
    assert other["answers"] == 0 and other["avgScore"] is None


def test_reports_helpers_build_a_consistent_card():
    card = reports.card("router", name="n", task="t", model="m", dataset={"name": "d", "train": 2, "test": 4,
                        "license": "l", "note": ""}, y_true=["a", "b", "a", "b"], y_pred=["a", "b", "b", "b"],
                        labels=["a", "b"], baseline={"name": "x", "accuracy": 0.5, "macroF1": 0.4})
    assert card["metrics"] == {"accuracy": 0.75, "macroF1": pytest.approx(0.7333, abs=1e-3)}
    assert card["confusion"] == [[1, 1], [0, 2]] and card["perClass"][0]["support"] == 2
    assert card["trainedAt"].endswith("Z") and card["extras"] is None
    for key in MODEL_KEYS:
        assert reports.load_card(key) is not None


def test_predict_latency_is_interactive():
    t = time.perf_counter()
    for _ in range(20):
        categoriser_model.predict_many(["UPI-ZEPTO-zepto@ybl-311307459751-UPI"] * 5, ["debit"] * 5)
    assert (time.perf_counter() - t) / 100 < 0.1  # < 100 ms per narration on CPU
