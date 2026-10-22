"""QLoRA SFT of Qwen/Qwen3-1.7B → sphura-fin-1.7b (docs/FINANCE_PLAN.md §5 row 4).

    training/.venv/Scripts/python training/sft/train.py [--run NAME] [--max-steps N] [--seq 1024] [--r 16]

Config (section 5): 4-bit NF4 base, LoRA r=16 / alpha=32 on all attention + MLP projections, lr 2e-4 cosine,
batch 1 × grad-accum 16, seq 1,024, 1 epoch, bf16 compute (the RTX 3060 is Ampere; bf16 is more stable than fp16
with 4-bit bases — see the README), paged AdamW 8-bit, gradient checkpointing, adapter saved every 50 steps to
training/runs/<run>/. Loss is computed on assistant tokens only (TRL prompt-completion format; the prompt is
rendered with the Qwen3 chat template with thinking disabled). Honours the GPU_BUSY lock. If the GPU runs out of
memory, rerun with --seq 768 --r 8.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRAINING_DIR = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TRAINING_DIR))

from gpu_lock import gpu_lock  # noqa: E402

BASE = "Qwen/Qwen3-1.7B"
DATA = TRAINING_DIR / "data" / "sft"
RUNS = TRAINING_DIR / "runs"
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def to_prompt_completion(rows: list[dict], tokenizer) -> list[dict]:
    """Render system+user with the Qwen3 template (thinking off); the completion is the assistant text + <|im_end|>."""
    out = []
    for row in rows:
        prompt = tokenizer.apply_chat_template(row["messages"][:2], tokenize=False, add_generation_prompt=True,
                                               enable_thinking=False)
        out.append({"prompt": prompt, "completion": row["messages"][2]["content"] + "<|im_end|>\n"})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=time.strftime("sphura-fin-1.7b-%Y%m%d-%H%M"))
    ap.add_argument("--max-steps", type=int, default=-1)
    ap.add_argument("--seq", type=int, default=1024)
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--eval-rows", type=int, default=200)
    ap.add_argument("--resume", default=None, help="checkpoint dir to resume from")
    ap.add_argument("--data", type=Path, default=DATA, help="SFT data dir (e.g. training/data/sft_scoped)")
    args = ap.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    run_dir = RUNS / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(BASE)
    tokenizer.pad_token = tokenizer.pad_token or "<|endoftext|>"
    train_rows = load_rows(args.data / "train.jsonl")
    hold_rows = load_rows(args.data / "holdout.jsonl")[: args.eval_rows]
    train_ds = Dataset.from_list(to_prompt_completion(train_rows, tokenizer))
    eval_ds = Dataset.from_list(to_prompt_completion(hold_rows, tokenizer))
    print(f"train {len(train_ds)} rows, eval {len(eval_ds)} rows -> {run_dir}")

    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                             bnb_4bit_compute_dtype=torch.bfloat16)
    lora = LoraConfig(r=args.r, lora_alpha=2 * args.r, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                      target_modules=TARGETS)
    cfg = SFTConfig(
        output_dir=str(run_dir), per_device_train_batch_size=1, per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.grad_accum, num_train_epochs=args.epochs, max_steps=args.max_steps,
        learning_rate=args.lr, lr_scheduler_type="cosine", warmup_steps=10, weight_decay=0.0,
        bf16=True, gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit", logging_steps=5, save_steps=50, save_total_limit=3, eval_strategy="steps",
        eval_steps=50, max_length=args.seq, packing=False, completion_only_loss=True, report_to="none", seed=42,
        dataloader_pin_memory=False,
    )
    started = time.perf_counter()
    with gpu_lock(f"sft-{args.run}"):
        model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb, dtype=torch.bfloat16,
                                                     device_map={"": 0}, attn_implementation="sdpa")
        model.config.use_cache = False
        trainer = SFTTrainer(model=model, args=cfg, train_dataset=train_ds, eval_dataset=eval_ds,
                             processing_class=tokenizer, peft_config=lora)
        trainable = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in trainer.model.parameters())
        print(f"trainable params {trainable:,} / {total:,} ({100 * trainable / total:.2f}%)")
        trainer.train(resume_from_checkpoint=args.resume)
        final = trainer.evaluate()
        trainer.save_model(str(run_dir / "adapter"))
        tokenizer.save_pretrained(str(run_dir / "adapter"))
        minutes = (time.perf_counter() - started) / 60
        history = trainer.state.log_history
        summary = {
            "run": args.run, "base": BASE, "data": args.data.as_posix(), "rows": len(train_ds), "evalRows": len(eval_ds), "steps": trainer.state.global_step,
            "epochs": args.epochs, "trainMinutes": round(minutes, 1), "seq": args.seq, "lora": {"r": args.r,
            "alpha": 2 * args.r, "targets": TARGETS, "dropout": 0.05}, "lr": args.lr, "gradAccum": args.grad_accum,
            "optim": "paged_adamw_8bit", "precision": "bf16 compute, nf4 base", "finalEvalLoss": final.get("eval_loss"),
            "gpu": torch.cuda.get_device_name(0), "maxMemoryGB": round(torch.cuda.max_memory_allocated() / 1e9, 2),
            "trainableParams": trainable, "history": history,
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"done in {minutes:.1f} min, {trainer.state.global_step} steps, eval loss {final.get('eval_loss')}")


if __name__ == "__main__":
    main()
