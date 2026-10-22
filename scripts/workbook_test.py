"""Check the deterministic finance analysis against samples/test_workbooks/answer_key.json (no LLM, no server).

For each bank statement: was it recognised, were all rows parsed, do inflow/outflow match to the rupee, and how
accurate is the transaction categoriser on merchants it never saw in training. For each balance sheet: totals and
the current / quick / debt-to-equity ratios.

Usage: backend/.venv/Scripts/python scripts/workbook_test.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from app.features.finance import bank, categoriser_model  # noqa: E402
from app.features.finance.parsing import find_table, read_sheets  # noqa: E402
from app.features.finance.report import analyze_file  # noqa: E402

BOOKS = ROOT / "samples" / "test_workbooks"


def close(a: float | None, b: float | None, rel: float = 0.01) -> bool:
    return a is not None and b is not None and abs(a - b) <= max(0.5, abs(b) * rel)


def label_of(display: str) -> str:
    inverse = {v.lower(): k for k, v in categoriser_model._load_display().items()}
    return inverse.get(display.lower(), display.lower())


def check_bank(path: Path, key: dict) -> dict:
    report = analyze_file(path, path.name, "test")
    table = find_table(read_sheets(path))
    txs, _, _ = bank._transactions(table, [])
    totals = report.get("totals") or {}
    out = {"kind": report["kind"], "rowsParsed": len(txs), "rowsExpected": key["rows"],
           "inflow": totals.get("inflow"), "inflowExpected": key["inflow"],
           "outflow": totals.get("outflow"), "outflowExpected": key["outflow"],
           "period": report.get("period"), "warnings": report.get("warnings")}
    checks = {"recognised": report["kind"] == "bank_statement", "allRows": len(txs) == key["rows"],
              "inflow": close(totals.get("inflow"), key["inflow"], 0.0),
              "outflow": close(totals.get("outflow"), key["outflow"], 0.0)}
    if len(txs) == key["rows"]:
        expected = [row[1] for row in key["labels"]]
        got = [label_of(t.category) for t in txs]
        right = sum(e == g for e, g in zip(expected, got))
        per = Counter(e for e in expected)
        per_ok = Counter(e for e, g in zip(expected, got) if e == g)
        out["categoriserAccuracy"] = round(right / len(expected), 4)
        out["perClass"] = {c: f"{per_ok[c]}/{n}" for c, n in sorted(per.items())}
        out["mistakes"] = [{"text": t.description[:90], "expected": e, "got": g}
                           for t, e, g in zip(txs, expected, got) if e != g][:12]
    out["checks"] = checks
    return out


def check_balance(path: Path, key: dict) -> dict:
    report = analyze_file(path, path.name, "test")
    bs = report.get("balanceSheet") or {}
    out = {"kind": report["kind"], "got": bs, "warnings": report.get("warnings")}
    out["checks"] = {
        "recognised": report["kind"] == "balance_sheet",
        "totalAssets": close(bs.get("totalAssets"), key["totalAssets"]),
        "equity": close(bs.get("equity"), key["equity"]),
        "currentRatio": close(bs.get("currentRatio"), key["currentRatio"], 0.02),
        "quickRatio": close(bs.get("quickRatio"), key["quickRatio"], 0.02),
        "debtToEquity": close(bs.get("debtToEquity"), key["debtToEquity_liabilities"], 0.02),
    }
    out["expected"] = {k: key[k] for k in ("totalAssets", "equity", "currentRatio", "quickRatio",
                                           "debtToEquity_liabilities")}
    return out


def main() -> int:
    key = json.loads((BOOKS / "answer_key.json").read_text(encoding="utf-8"))["files"]
    results, failed = {}, 0
    for name, k in key.items():
        res = (check_bank if k["kind"] == "bank_statement" else check_balance)(BOOKS / name, k)
        results[name] = res
        bad = [c for c, ok in res["checks"].items() if not ok]
        failed += bool(bad)
        acc = f"  categoriser {res['categoriserAccuracy']:.1%}" if "categoriserAccuracy" in res else ""
        print(f"{'FAIL' if bad else 'ok  '} {name:42s}{acc}  {'failed: ' + ', '.join(bad) if bad else ''}")
        if bad:
            shown = {k2: v for k2, v in res.items() if k2 not in ("mistakes", "perClass", "checks")}
            print("      ", json.dumps(shown, default=str)[:600])
        for m in res.get("mistakes", [])[:5]:
            print(f"       ✗ {m['expected']:>12s} → {m['got']:<12s} {m['text']}")
    (ROOT / "scripts" / "workbook_results.json").write_text(json.dumps(results, indent=1, default=str),
                                                             encoding="utf-8")
    print(f"\n{len(key) - failed}/{len(key)} workbooks passed -> scripts/workbook_results.json")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
