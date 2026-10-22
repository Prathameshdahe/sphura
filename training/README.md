# training/ — GPU jobs for the Sphura finance models

Everything here runs in `training/.venv` (Python 3.13, torch 2.11 cu128, transformers 5.20, peft 0.21, trl 1.16,
bitsandbytes 0.50, datasets, onnxruntime, matplotlib, pyarrow). The CPU-only sklearn scripts live in `backend/ml/`
and run in `backend/.venv`. Results and model cards: `backend/ml/README.md`; dataset cards: `backend/ml/data/README.md`.

## GPU sharing protocol

The RTX 3060 has 6 GB and Ollama models live in the same VRAM. Every GPU script wraps its work in
`gpu_lock.gpu_lock(job)`, which

1. refuses to start if `training/GPU_BUSY` already exists,
2. runs `ollama stop <model>` for every model in `ollama ps`,
3. creates `training/GPU_BUSY` (job name, pid, start time) and deletes it when the job ends, even on failure.

The backend must not call Ollama while `training/GPU_BUSY` exists (use the mock model). `python training/gpu_lock.py`
prints the lock state; `python training/gpu_lock.py release` clears a stale lock after a crash.

Run the scripts with UTF-8 stdout on Windows (`set PYTHONUTF8=1`) and, once the Hugging Face caches are warm,
`HF_HUB_OFFLINE=1 HF_HUB_DISABLE_XET=1` (the xet downloader 404s on the legacy `distilbert-base-uncased` id; use
`distilbert/distilbert-base-uncased`).

## Order of jobs (one GPU job at a time)

```bash
# 0. datasets (CPU, backend venv) — see backend/ml/README.md "How to reproduce"
# 1. DistilBERT classifiers (GPU, ~1 min each incl. ONNX export + int8 quantisation)
training/.venv/Scripts/python training/classifiers/train_bert.py --task categoriser --epochs 4
training/.venv/Scripts/python training/classifiers/train_bert.py --task sentiment
# 2. SFT data (CPU) → training/data/sft/{train,holdout,finqa_eval,offtopic_eval,finance_eval,judge_eval}.jsonl
training/.venv/Scripts/python training/sft/build_data.py
# 2b. (optional) drop off-topic Sujet rows → training/data/sft_scoped/ (backend venv; see dataset card §5)
backend/.venv/Scripts/python training/sft/scope_filter.py
# 3. QLoRA SFT of Qwen/Qwen3-1.7B (GPU, adapter every 50 steps in training/runs/<run>/); add --data training/data/sft_scoped
training/.venv/Scripts/python training/sft/train.py --run sphura-fin-1.7b        # OOM? add --seq 768 --r 8
# 4. merge → GGUF q8_0 (llama.cpp converter) → ollama create → 10-prompt + tool-call smoke test;
#    eval base vs tuned → backend/ml/artifacts/finetune/
training/.venv/Scripts/python training/sft/export.py --run sphura-fin-1.7b
training/.venv/Scripts/python training/sft/eval.py --run sphura-fin-1.7b          # judge: local qwen3.5:4b unless GEMINI_API_KEY
```

`training/data/raw/` holds the cached Hugging Face downloads (Sujet-Finance-Instruct-177k CSV, flare-finqa parquet,
Financial PhraseBank zip, TFNS CSVs). `TheFinAI/Fino1_Reasoning_Path_FinQA` and `mitulshah/transaction-categorization`
are gated and were **not** available without a token — see the dataset cards for the substitutions.
`training/runs/`, `training/data/sft/` and `training/data/raw/` are git-ignored.

## Files

| Path | What |
|---|---|
| `gpu_lock.py` | the lock + `ollama stop` helper |
| `classifiers/train_bert.py` | DistilBERT fine-tune (categoriser / sentiment), ONNX export, int8 quantisation, `deploy.json`, ModelCard |
| `sft/prompts.py` | the system prompt shared by training, evaluation and the Modelfile |
| `sft/build_data.py` | SFT mix + held-out and evaluation sets |
| `sft/scope_filter.py` | optional: drops Sujet rows the finance router labels out_of_scope → `data/sft_scoped/` |
| `sft/train.py` | QLoRA SFT (TRL `SFTTrainer`, prompt-completion format, assistant-only loss) |
| `sft/export.py` | LoRA merge → fp16 safetensors → llama.cpp `convert_hf_to_gguf.py --outtype q8_0` → Modelfile (Qwen3 non-thinking + tool-calling template) → `ollama create` → smoke test |
| `sft/ollama_client.py` | stdlib (urllib) client for Ollama `/api/chat` and Gemini — the training venv has no `httpx` |
| `sft/eval.py` | perplexity, FinQA EM, refusal / false-refusal, judged comparison, MMLU-mini, training-curve PNG → `FinetuneReport` (`--reuse` re-judges cached generations without the GPU) |

## Export notes (Ollama 0.40.3)

The plan's `ollama create --quantize q4_K_M` does not work on this Ollama: a dry run on a tiny random Qwen3 showed that
create-time quantization is only offered for **safetensors** imports and only as `int4 | int8 | nvfp4 | mxfp4 | mxfp8`,
and a GGUF import must already be quantized ("quantize GGUF models before importing"). K-quants need a compiled
`llama-quantize`, so `export.py` uses llama.cpp's pure-Python converter with `--outtype q8_0` (≈1.8 GB for 1.7B,
near-lossless) and imports that GGUF. `--via safetensors --quantize int4` tries Ollama's own importer instead.

## Dry runs (no GPU)

`export.py --cpu` and `eval.py --cpu --limit N --judge none` run end-to-end on a tiny random Qwen3 (real tokenizer,
2 layers, hidden 256) with a random LoRA adapter, which is how both scripts were checked while the SFT run held the
GPU: merge → GGUF → `ollama create` (then `ollama rm`), perplexity / FinQA / refusal / report writing, and lm_eval
MMLU on the CPU. `--base`, `--runs-dir` and `--artifact-dir` point the scripts at the fixture.
