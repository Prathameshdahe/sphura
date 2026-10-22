"""ModelCard helpers shared by the classifier trainers (docs/FINANCE_PLAN.md section 8 shape).

A trained classifier lives in ml/artifacts/<key>/ with `report.json` (the deployed model's ModelCard) and,
for the sklearn ladder, `report_sklearn.json`. `load_card(key)` returns whichever is present so the API and
the README never invent a number. This module must stay importable from the training venv (no `app` import).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ML_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = ML_DIR / "artifacts"
DATA_DIR = ML_DIR / "data"
KEYS = ("categoriser", "sentiment", "router")
ARTIFACT_SUBDIR = {"categoriser": "categoriser", "sentiment": "sentiment", "router": "fin_router"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def r4(x: Any) -> float:
    return round(float(x), 4)


def scores(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, f1_score

    return {"accuracy": r4(accuracy_score(y_true, y_pred)),
            "macroF1": r4(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))}


def per_class(y_true: list[str], y_pred: list[str], labels: list[str]) -> list[dict[str, Any]]:
    from sklearn.metrics import precision_recall_fscore_support

    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    return [{"label": lab, "precision": r4(p[i]), "recall": r4(r[i]), "f1": r4(f[i]), "support": int(s[i])}
            for i, lab in enumerate(labels)]


def confusion(y_true: list[str], y_pred: list[str], labels: list[str]) -> list[list[int]]:
    from sklearn.metrics import confusion_matrix

    return confusion_matrix(y_true, y_pred, labels=labels).astype(int).tolist()


def card(key: str, *, name: str, task: str, model: str, dataset: dict[str, Any], y_true: list[str],
         y_pred: list[str], labels: list[str], baseline: dict[str, Any] | None = None,
         extras: dict[str, float] | None = None, trained_at: str | None = None) -> dict[str, Any]:
    """A ModelCard dict (section 8) from one test-set prediction."""
    y_true, y_pred = [str(y) for y in y_true], [str(y) for y in y_pred]
    return {
        "key": key, "name": name, "task": task, "model": model, "trainedAt": trained_at or now_iso(),
        "dataset": dataset, "metrics": scores(y_true, y_pred, labels), "baseline": baseline, "labels": list(labels),
        "perClass": per_class(y_true, y_pred, labels), "confusion": confusion(y_true, y_pred, labels),
        "extras": extras or None,
    }


def confusion_png(matrix: list[list[int]] | np.ndarray, labels: list[str], title: str, path: Path) -> bool:
    """Row-normalised confusion heat-map; returns False when matplotlib is missing (the chart is optional)."""
    try:
        from matplotlib.figure import Figure
    except ImportError:
        return False
    m = np.asarray(matrix, dtype=float)
    share = m / np.maximum(m.sum(axis=1, keepdims=True), 1)
    n = len(labels)
    fig = Figure(figsize=(max(6.5, 0.55 * n + 3), max(5.5, 0.5 * n + 2.5)), dpi=150)
    ax = fig.subplots()
    image = ax.imshow(share, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(n), labels, rotation=35, ha="right", fontsize=8)
    ax.set_yticks(range(n), labels, fontsize=8)
    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True label")
    for i in range(n):
        for j in range(n):
            count = int(m[i, j])
            if count:
                ax.text(j, i, str(count), ha="center", va="center", fontsize=7,
                        color="white" if share[i, j] > 0.55 else "#1f2937", fontweight="bold" if i == j else None)
    ax.set_title(title, fontsize=10)
    cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Share of true label (row-normalised)", fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    return True


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def artifact_dir(key: str) -> Path:
    return ARTIFACT_DIR / ARTIFACT_SUBDIR[key]


def load_card(key: str) -> dict[str, Any] | None:
    """The deployed classifier's ModelCard: report.json, else the sklearn ladder's report_sklearn.json."""
    for name in ("report.json", "report_sklearn.json"):
        data = read_json(artifact_dir(key) / name)
        if data and data.get("metrics"):
            return data
    return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
