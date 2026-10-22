"""DistilBERT fine-tune for the transaction categoriser or the financial sentiment model, exported to ONNX.

    training/.venv/Scripts/python training/classifiers/train_bert.py --task categoriser   (~3 min on the 3060)
    training/.venv/Scripts/python training/classifiers/train_bert.py --task sentiment     (~5 min)

Data comes from backend/ml/data (built by ml/categoriser_data.py and ml/sentiment_data.py); the sklearn rungs
(ml/train_categoriser.py, ml/train_sentiment.py) must have run first so their numbers can be copied into the
ablation table. Outputs in backend/ml/artifacts/<task>/:
  model_quantized.onnx (int8; model.onnx fp32 is kept only when int8 loses > 1 pt), tokenizer.json, config.json
  (id2label), report.json (ModelCard, section 8) and confusion.png. The PyTorch checkpoint stays in
  training/runs/<task>-distilbert/ (not committed). The GPU lock protocol (gpu_lock.py) is honoured.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TRAINING_DIR = HERE.parent
REPO = TRAINING_DIR.parent
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(TRAINING_DIR))

from gpu_lock import gpu_lock  # noqa: E402
from ml import reports  # noqa: E402

SEED = 42
TASKS = {
    "categoriser": {"max_len": 64, "lr": 5e-5, "epochs": 2, "batch": 32,
                    "name": "Transaction categoriser", "task": "14-way bank-narration classification"},
    "sentiment": {"max_len": 128, "lr": 3e-5, "epochs": 2, "batch": 32,
                  "name": "Financial sentiment", "task": "3-way sentiment of finance headlines / sentences"},
}


def load_task(task: str) -> tuple[list[dict], list[dict], list[dict], list[str], dict]:
    """(train, val, test, labels, dataset_card) with rows {"text", "label", ...}."""
    if task == "categoriser":
        from sklearn.model_selection import train_test_split

        from ml import categoriser_data as cd

        rows = [{**r, "text": cd.model_text(r)} for r in cd.load(cd.TRAIN_PATH)]
        test = [{**r, "text": cd.model_text(r)} for r in cd.load(cd.TEST_PATH)]
        train, val = train_test_split(rows, test_size=0.1, stratify=[r["label"] for r in rows], random_state=SEED)
        card = {"name": "categoriser_train.jsonl (generated Indian narrations + demo statement) / "
                        "categoriser_test.jsonl (author-labelled)",
                "license": "Project-authored (same licence as the repository)",
                "note": f"{len(rows)} labelled narrations (10 % held out for early stopping); the test set was "
                        f"written and labelled by the author (see ml/data/README.md)"}
        return list(train), list(val), test, cd.LABELS, card
    from ml import sentiment_data as sd

    card = {"name": "Financial PhraseBank (sentences_50agree) + Twitter Financial News Sentiment",
            "license": "PhraseBank CC BY-NC-SA 3.0 (academic use); TFNS MIT",
            "note": "test = PhraseBank 10 % stratified hold-out + the official TFNS validation file; "
                    "see ml/data/README.md"}
    return sd.load("train"), sd.load("val"), sd.load("test"), sd.LABELS, card


def encode(tokenizer, rows: list[dict], label2id: dict[str, int], max_len: int):
    from datasets import Dataset

    ds = Dataset.from_dict({"text": [r["text"] for r in rows], "label": [label2id[r["label"]] for r in rows]})
    return ds.map(lambda b: tokenizer(b["text"], truncation=True, max_length=max_len), batched=True,
                  remove_columns=["text"])


def per_source(rows: list[dict], pred: list[str], labels: list[str]) -> dict[str, float]:
    out = {}
    for source in sorted({r.get("source", "") for r in rows}):
        idx = [i for i, r in enumerate(rows) if r.get("source") == source]
        if source and len(idx) >= 20:
            s = reports.scores([rows[i]["label"] for i in idx], [pred[i] for i in idx], labels)
            out[f"{source}Accuracy"], out[f"{source}MacroF1"] = s["accuracy"], s["macroF1"]
    return out


def export_onnx(model_dir: Path, out_dir: Path, max_len: int) -> Path:
    """Save tokenizer.json + config.json and the fp32 ONNX graph; returns the ONNX path."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir, attn_implementation="eager",
                                                               torch_dtype=torch.float32)
    model.config.return_dict = False
    model.eval()
    with tempfile.TemporaryDirectory() as tmp:
        tokenizer.save_pretrained(tmp)
        shutil.copy(Path(tmp) / "tokenizer.json", out_dir / "tokenizer.json")
    model.config.save_pretrained(out_dir)  # config.json with id2label
    enc = tokenizer(["debit | UPI-ZEPTO-zepto@ybl-311307459751-UPI", "credit | salary"], padding=True,
                    truncation=True, max_length=max_len, return_tensors="pt")
    args = (enc["input_ids"], enc["attention_mask"])
    path = out_dir / "model.onnx"
    dynamic = {"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"}, "logits": {0: "batch"}}
    try:
        torch.onnx.export(model, args, str(path), input_names=["input_ids", "attention_mask"], output_names=["logits"],
                          dynamic_axes=dynamic, opset_version=17, dynamo=False)
    except Exception as exc:  # noqa: BLE001 — the TorchScript exporter may be gone in a newer torch
        print(f"[export] legacy exporter failed ({type(exc).__name__}: {str(exc)[:200]}); trying dynamo")
        program = torch.onnx.export(
            model, args, dynamo=True, input_names=["input_ids", "attention_mask"], output_names=["logits"],
            dynamic_shapes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"}})
        program.save(str(path))
    return path


def quantize(fp32: Path) -> Path:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    int8 = fp32.with_name("model_quantized.onnx")
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    return int8


def onnx_predict(onnx_path: Path, tokenizer_json: Path, texts: list[str], id2label: dict[int, str],
                 max_len: int) -> tuple[list[str], float]:
    """Labels from onnxruntime + tokenizers (the backend's stack) and the per-text latency in ms."""
    import onnxruntime as ort
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(tokenizer_json))
    tok.enable_truncation(max_len)
    tok.enable_padding()
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    out: list[str] = []
    started = time.perf_counter()
    for start in range(0, len(texts), 64):
        enc = tok.encode_batch(texts[start:start + 64])
        feeds = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                 "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
        logits = session.run(None, feeds)[0]
        out.extend(id2label[int(i)] for i in logits.argmax(axis=1))
    latency = (time.perf_counter() - started) * 1000 / max(1, len(texts))
    return out, latency


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=sorted(TASKS), required=True)
    ap.add_argument("--model", default="distilbert/distilbert-base-uncased")
    ap.add_argument("--epochs", type=float)
    ap.add_argument("--batch", type=int)
    ap.add_argument("--lr", type=float)
    ap.add_argument("--max-len", type=int)
    ap.add_argument("--no-lock", action="store_true", help="skip the GPU_BUSY lock (CPU smoke runs)")
    args = ap.parse_args()
    spec = TASKS[args.task]
    epochs, batch = args.epochs or spec["epochs"], args.batch or spec["batch"]
    lr, max_len = args.lr or spec["lr"], args.max_len or spec["max_len"]

    import torch
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding, Trainer,
                              TrainingArguments, set_seed)

    set_seed(SEED)
    train_rows, val_rows, test_rows, labels, dataset_card = load_task(args.task)
    label2id = {lab: i for i, lab in enumerate(labels)}
    id2label = {i: lab for lab, i in label2id.items()}
    print(f"[{args.task}] train {len(train_rows)} / val {len(val_rows)} / test {len(test_rows)} rows, "
          f"{len(labels)} labels, {args.model}, {epochs} epochs, bs {batch}, lr {lr}, max_len {max_len}")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    ds_train, ds_val, ds_test = (encode(tokenizer, rows, label2id, max_len) for rows in (train_rows, val_rows, test_rows))
    run_dir = TRAINING_DIR / "runs" / f"{args.task}-distilbert"
    best_dir = run_dir / "best"
    out_dir = reports.artifact_dir(args.task)
    out_dir.mkdir(parents=True, exist_ok=True)

    def compute_metrics(pred):
        preds = pred.predictions.argmax(axis=-1)
        y_true = [id2label[int(i)] for i in pred.label_ids]
        y_pred = [id2label[int(i)] for i in preds]
        s = reports.scores(y_true, y_pred, labels)
        return {"accuracy": s["accuracy"], "macro_f1": s["macroF1"]}

    use_cuda = torch.cuda.is_available()
    started = time.perf_counter()
    with (gpu_lock(f"bert-{args.task}") if (use_cuda and not args.no_lock) else _null()):
        model = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=len(labels),
                                                                   id2label=id2label, label2id=label2id)
        total_steps = int(-(-len(train_rows) // batch) * epochs)
        targs = TrainingArguments(
            output_dir=str(run_dir), per_device_train_batch_size=batch, per_device_eval_batch_size=128,
            learning_rate=lr, num_train_epochs=epochs, warmup_steps=max(1, int(0.06 * total_steps)), weight_decay=0.01,
            fp16=use_cuda, eval_strategy="epoch", save_strategy="epoch", save_total_limit=1,
            load_best_model_at_end=True, metric_for_best_model="macro_f1", greater_is_better=True,
            logging_steps=20, report_to="none", seed=SEED, dataloader_pin_memory=use_cuda,
        )
        trainer = Trainer(model=model, args=targs, train_dataset=ds_train, eval_dataset=ds_val,
                          data_collator=DataCollatorWithPadding(tokenizer), compute_metrics=compute_metrics)
        trainer.train()
        train_minutes = (time.perf_counter() - started) / 60
        val = trainer.evaluate()
        test_out = trainer.predict(ds_test)
        trainer.save_model(str(best_dir))
        tokenizer.save_pretrained(str(best_dir))
        history = [{k: v for k, v in rec.items() if k in ("loss", "eval_loss", "eval_macro_f1", "eval_accuracy",
                                                           "epoch", "step")} for rec in trainer.state.log_history]
        del trainer, model
        if use_cuda:
            torch.cuda.empty_cache()

    y_true = [r["label"] for r in test_rows]
    y_pred = [id2label[int(i)] for i in test_out.predictions.argmax(axis=-1)]
    torch_scores = reports.scores(y_true, y_pred, labels)
    print(f"[{args.task}] PyTorch test: {torch_scores}  val macro-F1 {val.get('eval_macro_f1')}  "
          f"({train_minutes:.1f} min)")

    # ONNX export (fp32) → dynamic int8; both checked with the backend's onnxruntime + tokenizers stack
    fp32 = export_onnx(best_dir, out_dir, max_len)
    int8 = quantize(fp32)
    texts = [r["text"] for r in test_rows]
    fp32_pred, fp32_ms = onnx_predict(fp32, out_dir / "tokenizer.json", texts, id2label, max_len)
    int8_pred, int8_ms = onnx_predict(int8, out_dir / "tokenizer.json", texts, id2label, max_len)
    fp32_scores, int8_scores = reports.scores(y_true, fp32_pred, labels), reports.scores(y_true, int8_pred, labels)
    print(f"[{args.task}] ONNX fp32 {fp32_scores} {fp32_ms:.1f} ms/row | int8 {int8_scores} {int8_ms:.1f} ms/row")
    keep_int8 = int8_scores["accuracy"] >= fp32_scores["accuracy"] - 0.01
    deployed_pred, deployed_name = (int8_pred, "int8") if keep_int8 else (fp32_pred, "fp32")
    if keep_int8:
        fp32.unlink()
    else:
        int8.unlink()
        print(f"[{args.task}] int8 lost more than 1 pt; keeping fp32 model.onnx")

    sklearn_card = reports.read_json(out_dir / "report_sklearn.json") or {}
    ablation = list(sklearn_card.get("ablation") or [])
    # The ladder deploys whichever rung wins on the held-out test set; the app's loader reads deploy.json.
    sklearn_acc = float((sklearn_card.get("metrics") or {}).get("accuracy") or 0.0)
    deployed_scores = int8_scores if keep_int8 else fp32_scores
    winner = "onnx" if deployed_scores["accuracy"] >= sklearn_acc else "sklearn"
    reports.write_json(out_dir / "deploy.json", {
        "backend": winner, "onnxAccuracy": deployed_scores["accuracy"], "sklearnAccuracy": sklearn_acc,
        "reason": f"held-out test accuracy: DistilBERT ONNX {deployed_scores['accuracy']:.4f} vs sklearn "
                  f"{sklearn_acc:.4f}; the app loads the winner and falls back to the other",
    })
    print(f"[{args.task}] deploy.json -> {winner}")
    extras = {
        **per_source(test_rows, deployed_pred, labels),
        "pytorchAccuracy": torch_scores["accuracy"], "pytorchMacroF1": torch_scores["macroF1"],
        "onnxFp32Accuracy": fp32_scores["accuracy"], "onnxInt8Accuracy": int8_scores["accuracy"],
        "valMacroF1": reports.r4(val.get("eval_macro_f1", 0.0)), "epochs": float(epochs), "batchSize": float(batch),
        "learningRate": lr, "maxTokens": float(max_len), "trainMinutes": reports.r4(train_minutes),
        "cpuLatencyMsPerRow": reports.r4(int8_ms if keep_int8 else fp32_ms), "trainRows": float(len(train_rows)),
    }
    for k in ("tfidfLrAccuracy", "bgeSmallLrAccuracy", "bgeSmallLrMacroF1"):
        if k in (sklearn_card.get("extras") or {}):
            extras[k] = sklearn_card["extras"][k]
    if sklearn_card.get("metrics"):
        extras["tfidfLrAccuracy"] = sklearn_card["metrics"]["accuracy"]
        extras["tfidfLrMacroF1"] = sklearn_card["metrics"]["macroF1"]
    model_name = f"DistilBERT-base-uncased fine-tuned, ONNX {deployed_name}"
    card = reports.card(
        args.task, name=spec["name"], task=spec["task"], model=model_name,
        dataset={**dataset_card, "train": len(train_rows) + len(val_rows), "test": len(test_rows)},
        y_true=y_true, y_pred=deployed_pred, labels=labels, baseline=sklearn_card.get("baseline"), extras=extras,
    )
    ablation.append({"name": model_name, **card["metrics"], **per_source(test_rows, deployed_pred, labels)})
    card["ablation"] = ablation
    card["deployed"] = winner
    if winner == "sklearn":  # the deployed card must describe the model the app actually runs
        bert_card = dict(card)
        card = dict(sklearn_card)
        card["name"], card["trainedAt"] = spec["name"], card.get("trainedAt") or reports.now_iso()
        card["extras"] = {**(card.get("extras") or {}), "distilbertAccuracy": bert_card["metrics"]["accuracy"],
                          "distilbertMacroF1": bert_card["metrics"]["macroF1"], "trainMinutes": reports.r4(train_minutes),
                          "cpuLatencyMsPerRow": extras["cpuLatencyMsPerRow"]}
        card["ablation"], card["deployed"] = ablation, winner
        card["distilbert"] = {k: bert_card[k] for k in ("model", "metrics", "perClass", "confusion", "extras")}
    card["training"] = {"base": args.model, "epochs": epochs, "batchSize": batch, "learningRate": lr,
                        "maxTokens": max_len, "fp16": use_cuda, "gpu": torch.cuda.get_device_name(0) if use_cuda else "cpu",
                        "trainMinutes": reports.r4(train_minutes), "history": history}
    reports.write_json(out_dir / "report.json", card)
    reports.confusion_png(card["confusion"], labels, f"{spec['name']} — DistilBERT, held-out test (n={len(test_rows)})\n"
                          f"accuracy {card['metrics']['accuracy']:.1%} · macro-F1 {card['metrics']['macroF1']:.3f}",
                          out_dir / "confusion.png")
    (run_dir / "history.json").write_text(json.dumps(history, indent=1), encoding="utf-8")
    print(f"[{args.task}] wrote {out_dir / 'report.json'}: {card['metrics']} (deployed: {winner}; ONNX {deployed_name} kept)")


class _null:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


if __name__ == "__main__":
    main()
