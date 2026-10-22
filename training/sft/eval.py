"""Evaluate sphura-fin-1.7b against its base under identical decoding (docs/FINANCE_PLAN.md §5 row 4).

    training/.venv/Scripts/python training/sft/eval.py --run sphura-fin-1.7b [--judge ollama:qwen3.5:4b]

Both models run through transformers in fp16 on the GPU (one at a time; same prompts, same system prompt, greedy
decoding) so the comparison is fair:
  * held-out perplexity: mean NLL over assistant tokens of 200 held-out SFT rows (every slice is represented);
  * FinQA numeric exact match: 100 held-out flare-finqa TEST rows, last number in the answer vs gold, 1 % tolerance
    (percent / fraction forms accepted);
  * refusal rate on 100 off-topic prompts and false-refusal rate on 100 finance prompts (regex detector);
  * judged comparison on 100 held-out QA rows: the local qwen3.5:4b via Ollama judges base vs tuned (both
    orders, ties allowed) — a weaker local judge, used only because no cloud key exists; if GEMINI_API_KEY is set,
    gemini-3.5-flash-lite is used instead and named in the report;
  * MMLU-mini sanity: lm_eval (`mmlu`, 2 items per subject ≈ 114) if it is installed; otherwise null + a note.
Writes backend/ml/artifacts/finetune/report.json (FinetuneReport, section 8), training_curve.png and
eval_samples.jsonl. Takes the GPU lock while the models run; Ollama is only used after it is released.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAINING_DIR = HERE.parent
REPO = TRAINING_DIR.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TRAINING_DIR))

from gpu_lock import gpu_lock, stop_ollama_models  # noqa: E402
from ollama_client import gemini_chat as _gemini_chat  # noqa: E402
from ollama_client import ollama_chat as _ollama_chat  # noqa: E402
from prompts import SYSTEM_PROMPT  # noqa: E402

BASE = "Qwen/Qwen3-1.7B"
DATA = TRAINING_DIR / "data" / "sft"
ARTIFACT_DIR = REPO / "backend" / "ml" / "artifacts" / "finetune"
FINQA_NEW_TOKENS = 160  # room for a short worked solution from the base model; the tuned one answers in ~10
REFUSAL = re.compile(r"(not about finance|outside (?:what|my|the) |only (?:help|assist|answer|handle)[^.]{0,40}financ|"
                     r"finance[- ]only|can(?:'|’)?t help with (?:that|this)|cannot help with (?:that|this)|unable to help|"
                     r"isn(?:'|’)?t (?:about|related to) finance|unrelated to finance|not (?:a )?finance(?:-related)? (?:question|topic|request)|"
                     r"I(?:'|’)?m (?:a|an) (?:AI )?(?:finance|financial) assistant[^.]{0,60}(?:can(?:'|’)?t|cannot|only)|"
                     r"beyond (?:my|the) scope|out of (?:my )?scope|I can(?:'|’)?t (?:assist|help) you with)", re.I)
NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def chat_prompt(tokenizer, user: str) -> str:
    return tokenizer.apply_chat_template([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
                                         tokenize=False, add_generation_prompt=True, enable_thinking=False)


def generate(model, tokenizer, prompts: list[str], max_new_tokens: int, batch_size: int = 8) -> list[str]:
    import torch

    tokenizer.padding_side = "left"
    outs: list[str] = []
    for start in range(0, len(prompts), batch_size):
        texts = [chat_prompt(tokenizer, p) for p in prompts[start:start + batch_size]]
        enc = tokenizer(texts, return_tensors="pt", padding=True).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, temperature=None, top_p=None,
                                 top_k=None, pad_token_id=tokenizer.pad_token_id)
        for i in range(gen.shape[0]):
            text = tokenizer.decode(gen[i, enc["input_ids"].shape[1]:], skip_special_tokens=True)
            outs.append(re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S).strip())
    return outs


def perplexity(model, tokenizer, rows: list[dict]) -> float:
    """exp(mean NLL per assistant token) over the held-out rows."""
    import torch

    tokenizer.padding_side = "right"
    total_nll, total_tokens = 0.0, 0
    for row in rows:
        prompt = tokenizer.apply_chat_template(row["messages"][:2], tokenize=False, add_generation_prompt=True,
                                               enable_thinking=False)
        full = prompt + row["messages"][2]["content"] + "<|im_end|>"
        p_ids = tokenizer(prompt, return_tensors="pt")["input_ids"]
        ids = tokenizer(full, return_tensors="pt")["input_ids"].to(model.device)
        labels = ids.clone()
        labels[:, : p_ids.shape[1]] = -100
        with torch.no_grad():
            loss = model(input_ids=ids, labels=labels).loss
        n = int((labels != -100).sum()) - 1
        if n > 0 and math.isfinite(float(loss)):
            total_nll += float(loss) * n
            total_tokens += n
    return round(math.exp(total_nll / max(1, total_tokens)), 3)


def numbers(text: str) -> list[float]:
    out = []
    for m in NUMBER.findall(text.replace("₹", "").replace("$", "")):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return out


def finqa_match(answer: str, gold: str) -> bool:
    try:
        g = float(gold.replace("%", "").replace(",", ""))
    except ValueError:
        return False
    cands = numbers(answer)
    if not cands:
        return False
    pred = cands[-1]  # the final number is the answer in "The answer is X" style replies
    for variant in (pred, pred / 100, pred * 100, -pred):
        tol = max(abs(g) * 0.01, 0.005)
        if abs(variant - g) <= tol:
            return True
    return False


def is_refusal(text: str) -> bool:
    return bool(REFUSAL.search(text or ""))


def ollama_chat(model: str, messages: list[dict], num_predict: int = 16) -> str:
    return _ollama_chat(model, messages, num_predict=num_predict)["message"]["content"].strip()


def gemini_chat(model: str, messages: list[dict], num_predict: int = 16) -> str:
    return _gemini_chat(model, messages, num_predict=num_predict)


JUDGE_SYSTEM = ("You are a strict grader of answers to finance questions for Indian users. Compare two answers to the same "
                "question against the reference answer. Judge correctness first (numbers, rules, facts), then relevance "
                "and whether off-topic requests are declined politely. Reply with exactly one token: A, B or TIE.")


def judge(items: list[dict], base_answers: list[str], tuned_answers: list[str], backend: str, rng: random.Random):
    """[(verdict for tuned: 'win'|'loss'|'tie'|'error', votes)] — each item judged in both orders; a pick that flips
    with the order counts as a tie; an item whose judge calls both failed is 'error' (excluded from the win rate)."""
    call = gemini_chat if backend.startswith("gemini:") else ollama_chat
    model = backend.split(":", 1)[1]
    verdicts = []
    for n, (item, b, t) in enumerate(zip(items, base_answers, tuned_answers)):
        votes = []
        for order in ("bt", "tb"):
            first, second = (b, t) if order == "bt" else (t, b)
            user = (f"Question:\n{item['prompt']}\n\nReference answer:\n{item['reference'][:1500]}\n\n"
                    f"Answer A:\n{first[:1500]}\n\nAnswer B:\n{second[:1500]}\n\nWhich answer is better? Reply A, B or TIE.")
            try:
                raw = call(model, [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}], 8)
            except Exception as exc:  # noqa: BLE001
                print(f"[judge] item {n} failed: {type(exc).__name__}: {exc}")
                votes.append("error")
                continue
            letter = re.search(r"\b(A|B|TIE)\b", raw.upper())
            pick = letter.group(1) if letter else "TIE"
            tuned_letter = "B" if order == "bt" else "A"
            votes.append("win" if pick == tuned_letter else "tie" if pick == "TIE" else "loss")
        valid = [v for v in votes if v != "error"]
        verdict = "error" if not valid else valid[0] if len(set(valid)) == 1 else "tie"
        verdicts.append((verdict, votes))
        if n % 20 == 19:
            print(f"[judge] {n + 1}/{len(items)} judged")
    return verdicts


def mmlu_mini(model_dir: str, limit_per_subject: int = 2, device: str = "cuda", out_root: Path | None = None) -> float | None:
    """Accuracy over `mmlu` with lm_eval (≈114 items); None when lm_eval is not installed or fails."""
    try:
        import lm_eval  # noqa: F401
    except ImportError:
        return None
    out = (out_root or TRAINING_DIR / "runs" / "lm_eval") / Path(model_dir).name.replace("/", "_")
    out.mkdir(parents=True, exist_ok=True)
    dtype = "float16" if device.startswith("cuda") else "float32"
    cmd = [sys.executable, "-m", "lm_eval", "--model", "hf", "--model_args", f"pretrained={model_dir},dtype={dtype}",
           "--tasks", "mmlu", "--limit", str(limit_per_subject), "--batch_size", "8", "--device", device,
           "--output_path", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    if proc.returncode != 0:
        print("[mmlu] lm_eval failed:", proc.stderr[-800:])
        return None
    for path in sorted(out.rglob("results*.json"), key=lambda p: p.stat().st_mtime):
        data = json.loads(path.read_text(encoding="utf-8"))
        acc = (data.get("results") or {}).get("mmlu", {}).get("acc,none")
        if acc is not None:
            return round(float(acc), 4)
    return None


def training_curve(summary: dict, path: Path) -> bool:
    try:
        from matplotlib.figure import Figure
    except ImportError:
        return False
    hist = summary.get("history") or []
    steps = [h["step"] for h in hist if "loss" in h]
    losses = [h["loss"] for h in hist if "loss" in h]
    esteps = [h["step"] for h in hist if "eval_loss" in h]
    elosses = [h["eval_loss"] for h in hist if "eval_loss" in h]
    fig = Figure(figsize=(7, 4), dpi=150)
    ax = fig.subplots()
    ax.plot(steps, losses, label="train loss (assistant tokens)")
    if esteps:
        ax.plot(esteps, elosses, "o-", label="held-out loss")
    ax.set_xlabel("optimizer step")
    ax.set_ylabel("cross-entropy")
    ax.set_title(f"sphura-fin-1.7b QLoRA — {summary.get('rows')} rows, {summary.get('steps')} steps, "
                 f"{summary.get('trainMinutes')} min on {summary.get('gpu', 'GPU')}")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    return True


def run_model(name: str, model_dir: str, sets: dict, ppl_rows: list[dict], device: str = "cuda") -> dict:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"[{name}] loading {model_dir} on {device}")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    tokenizer.pad_token = tokenizer.pad_token or "<|endoftext|>"
    model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.float16 if device == "cuda" else torch.float32,
                                                 device_map={"": 0} if device == "cuda" else None)
    model.eval()
    t0 = time.perf_counter()
    out = {"perplexity": perplexity(model, tokenizer, ppl_rows)}
    print(f"[{name}] perplexity {out['perplexity']} ({time.perf_counter() - t0:.0f}s)")
    out["finqa"] = generate(model, tokenizer, [r["prompt"] for r in sets["finqa"]], FINQA_NEW_TOKENS, batch_size=4)
    out["finqaEm"] = round(sum(finqa_match(a, r["gold"]) for a, r in zip(out["finqa"], sets["finqa"])) / len(sets["finqa"]), 4)
    print(f"[{name}] FinQA EM {out['finqaEm']}")
    out["offtopic"] = generate(model, tokenizer, [r["prompt"] for r in sets["offtopic"]], 96)
    out["refusalRate"] = round(sum(map(is_refusal, out["offtopic"])) / len(out["offtopic"]), 4)
    out["finance"] = generate(model, tokenizer, [r["prompt"] for r in sets["finance"]], 96)
    out["falseRefusalRate"] = round(sum(map(is_refusal, out["finance"])) / len(out["finance"]), 4)
    print(f"[{name}] refusal {out['refusalRate']} false-refusal {out['falseRefusalRate']}")
    out["judge"] = generate(model, tokenizer, [r["prompt"] for r in sets["judge"]], 256)
    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    return out


def judge_backend_default() -> str:
    return "gemini:gemini-3.5-flash-lite" if os.environ.get("GEMINI_API_KEY") else "ollama:qwen3.5:4b"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="sphura-fin-1.7b")
    ap.add_argument("--judge", default=judge_backend_default(), help="ollama:<model> | gemini:<model> | none")
    ap.add_argument("--ppl-rows", type=int, default=200)
    ap.add_argument("--limit", type=int, default=0, help="use only the first N rows of every eval set (dry runs)")
    ap.add_argument("--skip-mmlu", action="store_true")
    ap.add_argument("--mmlu-per-subject", type=int, default=2)
    ap.add_argument("--base", default=BASE, help="base model id/dir (same one the adapter was trained on)")
    ap.add_argument("--runs-dir", type=Path, default=TRAINING_DIR / "runs")
    ap.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR)
    ap.add_argument("--cpu", action="store_true", help="run the models on the CPU without the GPU lock (dry run)")
    ap.add_argument("--reuse", action="store_true", help="reuse the cached generations in <run>/eval_outputs.json")
    ap.add_argument("--data", type=Path, default=DATA, help="SFT data dir with the hold-out and eval sets")
    args = ap.parse_args()
    run_dir = args.runs_dir / args.run
    merged = run_dir / "merged"
    assert (merged / "config.json").exists(), f"run export.py first ({merged} missing)"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rng = random.Random(7)
    data = args.data
    sets = {"finqa": load_jsonl(data / "finqa_eval.jsonl"), "offtopic": load_jsonl(data / "offtopic_eval.jsonl"),
            "finance": load_jsonl(data / "finance_eval.jsonl"), "judge": load_jsonl(data / "judge_eval.jsonl")}
    ppl_rows = load_jsonl(data / "holdout.jsonl")[: args.ppl_rows]
    if args.limit:
        sets = {k: v[: args.limit] for k, v in sets.items()}
        ppl_rows = ppl_rows[: args.limit]
    device = "cpu" if args.cpu else "cuda"
    cache = run_dir / "eval_outputs.json"
    started = time.perf_counter()
    if args.reuse and cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        base, tuned = cached["base"], cached["tuned"]
        mmlu_base, mmlu_tuned = cached["mmluBase"], cached["mmluTuned"]
        mmlu_note, gpu_minutes = cached["mmluNote"], cached["gpuMinutes"]
        print(f"[eval] reusing generations from {cache}")
    else:
        with nullcontext() if args.cpu else gpu_lock(f"eval-{args.run}"):
            base = run_model("base", args.base, sets, ppl_rows, device)
            tuned = run_model("tuned", str(merged), sets, ppl_rows, device)
            mmlu_base = mmlu_tuned = None
            mmlu_note = "MMLU-mini skipped (--skip-mmlu)"
            if not args.skip_mmlu:
                items = f"{args.mmlu_per_subject} items per subject (about {57 * args.mmlu_per_subject} items)"
                mmlu_base = mmlu_mini(args.base, args.mmlu_per_subject, device, run_dir / "lm_eval")
                if mmlu_base is not None:
                    mmlu_tuned = mmlu_mini(str(merged), args.mmlu_per_subject, device, run_dir / "lm_eval")
                mmlu_note = (f"MMLU-mini: lm_eval `mmlu`, {items}, 0-shot log-likelihood scoring"
                             if mmlu_tuned is not None else "MMLU-mini skipped: lm_eval failed or is not installed in "
                             "training/.venv; see the log")
        gpu_minutes = (time.perf_counter() - started) / 60
        cache.write_text(json.dumps({"base": base, "tuned": tuned, "mmluBase": mmlu_base, "mmluTuned": mmlu_tuned,
                                     "mmluNote": mmlu_note, "gpuMinutes": gpu_minutes}, ensure_ascii=False),
                         encoding="utf-8")

    # judged comparison (Ollama after the GPU lock is released; both orders; ties when the two orders disagree)
    judge_backend = args.judge
    if judge_backend == "none":
        verdicts, judge_model, win_rate = [], None, None
        wins = losses = ties = errors = 0
    else:
        verdicts = judge(sets["judge"], base["judge"], tuned["judge"], judge_backend, rng)
        if judge_backend.startswith("ollama:"):
            stop_ollama_models()
        errors = sum(1 for v, _ in verdicts if v == "error")
        wins = sum(v == "win" for v, _ in verdicts)
        losses = sum(v == "loss" for v, _ in verdicts)
        ties = len(verdicts) - wins - losses - errors
        judged = len(verdicts) - errors
        win_rate = round((wins + 0.5 * ties) / judged, 4) if judged else None
        judge_model = judge_backend.split(":", 1)[1] + (" (local Ollama judge — weaker than a cloud judge)"
                                                         if judge_backend.startswith("ollama:") else " (cloud judge)")

    out_dir: Path = args.artifact_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    for i, r in enumerate(sets["judge"]):
        samples.append({"set": "judge", "prompt": r["prompt"], "reference": r["reference"], "base": base["judge"][i],
                        "tuned": tuned["judge"][i], "verdict": verdicts[i][0] if verdicts else None,
                        "votes": verdicts[i][1] if verdicts else None})
    for key in ("finqa", "offtopic", "finance"):
        for i, r in enumerate(sets[key]):
            samples.append({"set": key, "prompt": r["prompt"][-1200:], "gold": r.get("gold"), "base": base[key][i],
                            "tuned": tuned[key][i]})
    with (out_dir / "eval_samples.jsonl").open("w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    smoke = {}
    if (out_dir / "smoke.json").exists():
        smoke = json.loads((out_dir / "smoke.json").read_text(encoding="utf-8"))
    smoke_rows = smoke.get("smoke") or []
    judge_note = (f"Judge: {judge_model}; {len(verdicts)} held-out QA rows, each judged in both orders (a pick that "
                  f"flips with the order counts as a tie) — tuned wins {wins}, losses {losses}, ties {ties}, judge "
                  f"errors {errors} (excluded); win rate counts ties as 0.5." if verdicts
                  else "Judged comparison not run (--judge none).")
    report = {
        "available": True, "name": "sphura-fin-1.7b", "base": args.base,
        "method": f"QLoRA SFT (nf4 base, LoRA r={summary['lora']['r']}, alpha={summary['lora']['alpha']}, bf16 compute, "
                  f"paged AdamW 8-bit, lr {summary['lr']}, bs 1 × GA {summary['gradAccum']}, seq {summary['seq']})",
        "rows": summary["rows"], "steps": summary["steps"], "epochs": summary["epochs"], "trainMinutes": summary["trainMinutes"],
        "gpu": summary["gpu"], "lora": {"r": summary["lora"]["r"], "alpha": summary["lora"]["alpha"],
                                        "targets": summary["lora"]["targets"]},
        "eval": {"heldoutPerplexityBase": base["perplexity"], "heldoutPerplexityTuned": tuned["perplexity"],
                 "finqaEmBase": base["finqaEm"], "finqaEmTuned": tuned["finqaEm"],
                 "refusalRate": tuned["refusalRate"], "falseRefusalRate": tuned["falseRefusalRate"],
                 "judgeWinRate": win_rate, "judgeModel": judge_model, "mmluMiniBase": mmlu_base, "mmluMiniTuned": mmlu_tuned},
        "ollamaTag": smoke.get("tag"),
        "notes": [
            f"Held-out perplexity over assistant tokens of {len(ppl_rows)} held-out rows (all slices); lower is better.",
            f"FinQA EM on {len(sets['finqa'])} held-out FinQA test rows (last number in the reply vs gold, 1 % tolerance, "
            f"percent/fraction forms accepted; up to {FINQA_NEW_TOKENS} new tokens).",
            f"Refusal rate on {len(sets['offtopic'])} off-topic prompts and false-refusal rate on {len(sets['finance'])} "
            f"finance prompts, regex detector; base model: refusal {base['refusalRate']}, false refusal {base['falseRefusalRate']}.",
            judge_note,
            mmlu_note, f"Greedy decoding, same system prompt for both models ({device}); generation time {gpu_minutes:.0f} min.",
            f"Final training eval loss {summary.get('finalEvalLoss')}; peak VRAM {summary.get('maxMemoryGB')} GB.",
        ] + ([f"Ollama smoke test: {sum(1 for s in smoke_rows if 'answer' in s)}/{len(smoke_rows)} prompts answered "
              f"via {smoke.get('method')} ({smoke.get('quantize')})"] if smoke_rows else []),
        "baseEval": {"refusalRate": base["refusalRate"], "falseRefusalRate": base["falseRefusalRate"]},
        "judgeCounts": {"wins": wins, "losses": losses, "ties": ties, "errors": errors},
        "evaluatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    training_curve(summary, out_dir / "training_curve.png")
    shutil.copy(run_dir / "summary.json", out_dir / "training_summary.json")
    print(json.dumps(report["eval"], indent=2))
    print(f"[eval] wrote {out_dir / 'report.json'}")


if __name__ == "__main__":
    main()
