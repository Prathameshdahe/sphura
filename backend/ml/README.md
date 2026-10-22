# Sphura ML — finance models

This folder holds the machine learning behind Sphura's finance pivot: the datasets, the training and evaluation
scripts, and the artifacts the app loads. Four trained components:

1. **Transaction categoriser** — 14-way bank-narration classifier used by the spending dashboard and the
   `analytics` node (`app/features/finance/categorize.py`).
2. **Financial sentiment** — labels finance headlines on the Markets page (`app/features/sentiment/`).
3. **Finance intent router** — the `classify` node of the LangGraph (`app/agent/classify.py`,
   `app/features/router/`).
4. **sphura-fin-1.7b** — Qwen3-1.7B fine-tuned with QLoRA on finance instructions and an author-written Indian
   finance QA set, imported into Ollama.

Plus the earlier **RAG retrieval benchmark** (section 5). `GET /api/ml/report` serves all of it to the Model Lab
page. **Every number below is copied from the committed `artifacts/*/report.json` files** (reproduced by the
commands in section 7); nothing is estimated. Dataset cards: [`data/README.md`](data/README.md); GPU scripts:
[`../training/README.md`](../training/README.md).

| Model | Deployed artifact | Test set | Accuracy | Macro-F1 | Baseline (acc / F1) |
|---|---|---|---|---|---|
| Transaction categoriser | TF-IDF + logistic regression (`categoriser/sklearn.joblib`) | 430 author-labelled narrations | **98.6 %** | **0.987** | rules 72.3 % / 0.766 |
| Financial sentiment | DistilBERT fine-tune, ONNX int8 (`sentiment/model_quantized.onnx`) | 2,861 (PhraseBank 484 + TFNS 2,377) | **86.8 %** | **0.832** | lexicon 69.3 % / 0.579 |
| Finance intent router | LR on bge-small embeddings (`fin_router.joblib`) | 425 held-out messages | **95.8 %** | **0.960** | keyword rules 56.7 % / 0.566 |
| sphura-fin-1.7b | see section 4 | held-out SFT rows, FinQA, refusal sets | see section 4 | | base Qwen3-1.7B |

---

## 1. Transaction categoriser

### 1.1 Problem

The spending dashboard needs a category for every statement line ("UPI-ZEPTO-zepto@ybl-311307459751-UPI" →
Groceries). Narrations are terse, bank-specific and full of reference numbers; a keyword list breaks on every new
merchant and on generic rails ("UPI-RAHUL SHARMA-…-rent for oct" is rent, not a transfer). We frame it as **14-class
classification of `"<credit|debit> | <narration>"`**: salary, rent, groceries, dining, travel, fuel, utilities,
shopping, subscriptions, emi_loan, investments, transfers, fees, cash. Refunds and interest stay rule-based
(credit-only, keyword-trivial, needed by the sign inference) and *Other* is the fallback.

### 1.2 Data

6,817 training narrations (6,720 generated from Indian bank export formats × merchant lists × noise, 97 from the
demo statement) and a **430-row test set written and labelled by hand by the author** using banks, merchants and
layouts the generator does not produce (card: `data/README.md` §1). No test narration appears in training.

### 1.3 The ladder (`train_categoriser.py`, `training/classifiers/train_bert.py --task categoriser`)

All rungs are scored on the same author-labelled test set.

| Rung | Model | Accuracy | Macro-F1 | CPU latency |
|---|---|---|---|---|
| 0 | Rules (`categorize.rules_category`, the pre-ML categoriser) | 72.3 % | 0.766 | — |
| 1 | **TF-IDF (word 1-2 + char_wb 2-5 grams) + logistic regression**, C = 16 by 3-fold CV | **98.6 %** | **0.987** | < 1 ms/row |
| 2 | bge-small-en-v1.5 embeddings + logistic regression | 89.8 % | 0.902 | ~6 ms/row |
| 3 | DistilBERT-base-uncased fine-tune (4 epochs, lr 5e-5, bs 32, 64 tokens, fp16, 0.9 min on the RTX 3060) → ONNX int8 | 95.4 % | 0.955 | 5.7 ms/row |

Per-class F1 of the deployed TF-IDF model: salary 0.98, rent 1.00, groceries 0.97, dining 0.99, travel 0.98,
fuel 0.98, utilities 0.97, shopping 1.00, subscriptions 1.00, emi_loan 0.98, investments 0.97, transfers 0.99,
fees 1.00, cash 1.00 (confusion matrix: `artifacts/categoriser/confusion.png`).

**Why the small model wins here.** Narrations are keyword-like strings where character n-grams capture merchant
fragments ("ZEPTO", "IOCL", "NACH-") and rails exactly; the uncased WordPiece tokenizer splits unseen merchants
into fragments DistilBERT never saw, and 6k short rows are too few to learn them (its in-distribution validation
macro-F1 is 0.987, so the gap is generalisation to new merchants, not under-fitting; going from 2 to 4 epochs
raised test accuracy from 92.8 % to 95.4 %). bge-small embeddings lose the exact-token information entirely.
The trainer records this comparison in `artifacts/categoriser/deploy.json` and **the app loads the rung that won
on the held-out test** (`app/features/finance/categoriser_model.py`: deploy.json → sklearn or ONNX → the other → rules).
Both artifacts are committed, so the DistilBERT ONNX model is one line away if more real data changes the ranking.

### 1.4 In the app

`categorize(description, amount)`: credit-only rules (Refunds, Interest) → the model when its confidence is
≥ 0.55 → the regex rules. The sklearn pipeline is self-contained (no embedder), so categorising a 5,000-line
statement takes well under a second; predictions are cached per narration.

---

## 2. Financial sentiment

### 2.1 Problem and data

The Markets page labels each finance headline positive / neutral / negative. We never ship FinBERT weights
(CC BY-NC-SA) and instead fine-tune our own model on **Financial PhraseBank `sentences_50agree`** (4,846
sentences, CC BY-NC-SA 3.0, academic use) and **Twitter Financial News Sentiment** (11,931 tweets, MIT). Splits
are stratified per source; the test set is the PhraseBank 10 % hold-out (484) plus the official TFNS validation
file (2,377). Card: `data/README.md` §3.

### 2.2 Models (`train_sentiment.py`, `training/classifiers/train_bert.py --task sentiment`)

| Model | Test acc | Test macro-F1 | PhraseBank acc / F1 | TFNS acc / F1 |
|---|---|---|---|---|
| Lexicon (`app.features.market.sentiment.lexicon`, the fallback) | 69.3 % | 0.579 | 66.1 % / 0.513 | 69.9 % / 0.592 |
| TF-IDF (word + char) + logistic regression (`sklearn.joblib`, C = 4) | 80.9 % | 0.752 | 74.6 % / 0.705 | 82.2 % / 0.763 |
| **DistilBERT-base-uncased fine-tune, 2 epochs, lr 3e-5, bs 32, 128 tokens, fp16, 1.2 min → ONNX int8** | **86.8 %** | **0.832** | **85.5 % / 0.842** | **87.0 % / 0.830** |

ONNX fp32 scores 87.3 % / 0.839; int8 dynamic quantisation costs 0.6 pt and halves latency (8.8 ms/row on CPU),
so the int8 file is the one committed (67 MB). Per-class F1: negative 0.79, neutral 0.91, positive 0.80 — the
usual pattern on PhraseBank where the 50 %-agreement neutral/positive boundary is noisy.

**Literature check.** FinBERT (Araci, 2019) reports ~0.86 accuracy on Financial PhraseBank; our 85.5 % on the
PhraseBank slice is in the same range with a model half FinBERT's size, trained in about a minute, and without
the non-commercial weights.

### 2.3 In the app

`app/features/sentiment/model.py` runs the ONNX model with onnxruntime + tokenizers (no torch in the backend
venv) and falls back to the sklearn pipeline; `app/features/market/sentiment.py` probes `app.features.sentiment.
predict` and keeps its lexicon as the last resort. `label(text) -> {label, score}`.

---

## 3. Finance intent router

### 3.1 Problem

The LangGraph needs to pick a branch for every message: `spending`, `documents`, `market`, `explain`, `advice` or
`out_of_scope` (templated refusal, no LLM call). Keyword rules are brittle at the boundaries — "TCS share price today"
(market) vs "what is TCS?" (explain) vs "should I buy TCS?" (advice).

### 3.2 Data and model (`router_data.py`, `train_router.py`)

2,123 messages: 243 hand-written boundary cases + 1,880 templated (card: `data/README.md` §2). Features are the
production RAG embedder (`BAAI/bge-small-en-v1.5`, 384-d, L2-normalised) so routing adds no new model; the
classifier is multinomial logistic regression with C chosen by 5-fold CV on the training split
(C = 32; CV macro-F1 0.911 → 0.966 across the grid). Stratified 80/20 hold-out: 1,698 / 425.

### 3.3 Results

| Model | Held-out acc | Held-out macro-F1 | Unseen templates (5-fold group CV) acc / F1 |
|---|---|---|---|
| Keyword rules (`app.agent.classify.keyword_classify`, the graph's fallback) | 56.7 % | 0.566 | 55.0 % / 0.541 |
| TF-IDF (1-2 grams) + logistic regression | 97.9 % | 0.980 | 85.6 % / 0.857 |
| **Logistic regression on bge-small embeddings (deployed)** | **95.8 %** | **0.960** | **92.1 % / 0.921** |

Per-class F1 (held-out): spending 0.95, documents 0.98, market 0.98, explain 0.93, advice 0.99, out_of_scope 0.93.
Hand-written subset in the hold-out: 86.4 % (n = 59). 96.5 % of held-out messages clear the graph's 0.6 confidence
threshold (below it the keyword classifier decides). Latency: 5.9 ms p50 per message on CPU after warm-up.

**Why embeddings although TF-IDF scores higher on the random split.** The random split shares templates between
train and test, so a lexical model memorises them (97.9 %). When whole templates are held out — the honest proxy for
real users' phrasing — TF-IDF drops to 85.6 % while the embedding model keeps 92.1 %. The keyword baseline is weak
mostly because "what is a SIP?" style questions trip its market/explain rules; the graph therefore trusts the router
first. Confusion matrix: `artifacts/fin_router/confusion.png`; remaining errors are explain↔out_of_scope
("explain the offside rule") and spending↔out_of_scope chit-chat.

---

## 4. sphura-fin-1.7b (QLoRA SFT of Qwen3-1.7B)

> Status: training was launched after the classifiers; this section is completed by `training/sft/eval.py`, which
> writes `artifacts/finetune/report.json` (FinetuneReport) and `training_curve.png`. If the file is missing or
> `available` is false, the run did not finish — the Model Lab shows "not available" rather than invented numbers.

### 4.1 Data

3,134 training rows / 349 held out before training (10 % of every slice), mean 403 tokens, max 1,024:
Sujet-Finance-Instruct-177k subset 2,146 (qa 990, qa-with-context 630, conversation 301, sentiment 225 ≤ 10 %),
FinQA 515 (flare-finqa train rows; Fino1 is gated), **author-written Indian finance QA 334** (371 total; GST, ITR,
80C/80D/80CCD, EPF/PPF/NPS, UPI rules, SIP/EMI/FD maths with worked numbers, credit score, regimes, SEBI/RBI,
mutual funds, accounting — each with a source note) and **139 scoped refusals** (155 total). Card: `data/README.md` §4–5.

### 4.2 Method (`training/sft/train.py`)

Qwen/Qwen3-1.7B loaded in 4-bit NF4 (double quant), LoRA r = 16 / α = 32 / dropout 0.05 on q,k,v,o,gate,up,down
(17.4 M trainable parameters, 1.7 %), lr 2e-4 cosine with 10 warm-up steps, batch 1 × grad-accum 16, seq 1,024,
1 epoch, paged AdamW 8-bit, gradient checkpointing, **bf16 compute** (the RTX 3060 is Ampere; bf16 avoids the
fp16 overflow seen with 4-bit bases — the only deviation from the plan's "fp16"), adapter saved every 50 steps.
Loss on assistant tokens only (TRL prompt-completion format; prompts rendered with the Qwen3 chat template,
thinking disabled). The same system prompt (`training/sft/prompts.py`) is used in training, evaluation and the
Ollama Modelfile.

### 4.3 Evaluation protocol (`training/sft/eval.py`) — base vs tuned under identical greedy decoding

* held-out perplexity over assistant tokens of 200 held-out rows;
* FinQA numeric exact match on 100 held-out flare-finqa **test** rows (1 % tolerance, percent forms accepted);
* refusal rate on 100 off-topic prompts and false-refusal rate on 100 finance prompts (regex detector);
* judged comparison on 100 held-out QA rows by **qwen3.5:4b through Ollama (a weaker local judge — no cloud key
  on this machine)**, each pair judged in both orders, disagreement counted as a tie;
* MMLU-mini sanity: `lm_eval` `mmlu` with 2 items per subject (≈114 items).

Results: see `artifacts/finetune/report.json` → `eval` and the table appended below by the training engineer once
the evaluation has run (section 4.4).

### 4.4 Results

_(filled in from `artifacts/finetune/report.json` — see the end of this file)_

---

## 5. RAG retrieval benchmark (unchanged from the earlier wave)

`eval_rag.py` over `eval_corpus/` (18 documents, 122 questions with gold passages; 154 production chunks) compares
BM25, dense bge-small, hybrid RRF and hybrid + cross-encoder rerank with Recall@k, MRR, nDCG@10 and latency.
Numbers from `artifacts/rag_eval.json` (chart `artifacts/rag_eval.png`):

| Config | R@1 | R@3 | R@5 | R@10 | MRR | nDCG@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|
| BM25 | 0.689 | 0.844 | 0.877 | 0.926 | 0.775 | 0.811 | 0.7 | 1.5 |
| Dense (bge-small) | 0.680 | 0.877 | 0.918 | 0.959 | 0.783 | 0.825 | 14.5 | 79.5 |
| Hybrid (RRF) | 0.689 | 0.902 | 0.910 | 0.975 | 0.795 | 0.838 | 11.8 | 51.4 |
| **Hybrid + cross-encoder rerank** | **0.795** | **0.926** | **0.943** | **0.975** | **0.866** | **0.892** | 556 | 741 |

Findings: lexical and dense retrieval fail in opposite places (keyword IDs vs paraphrases); fusion lifts recall and
the cross-encoder fixes the top-1 ordering (+15 % relative Recall@1) at ~0.5 s per query on CPU. Served as `ragEval`
in `GET /api/ml/report`.

---

## 6. API (`app/api/ml.py`)

* `GET /api/ml/report` → `ModelLabReport { models: ModelCard[], finetune: FinetuneReport | null, ragEval, generatedAt }`
  (section 8 of docs/FINANCE_PLAN.md). Each `ModelCard` is read from `artifacts/<model>/report.json` (the deployed
  model) or `report_sklearn.json` and carries `extras` plus an `ablation` list for the Model Lab table; a model whose
  artifact is missing is simply absent.
* `POST /api/ml/train/{categoriser|sentiment|router}` (admin) retrains one classifier in a worker thread and returns
  its card. For the categoriser and sentiment keys this refits the sklearn rung (the DistilBERT rung needs the GPU
  venv); the router retrains fully.
* `GET /api/ml/verification` → verification statistics over the current user's answers (unchanged).
* The old `/api/ml/router*` and `/api/ml/rag-eval*` routes are removed.

---

## 7. How to reproduce

From the repo root (Windows / Git Bash; `backend/.venv` for CPU work, `training/.venv` for GPU work):

```bash
# datasets (deterministic; builders are checked against the committed files by the tests)
backend/.venv/Scripts/python -m ml.categoriser_data          # → data/categoriser_{train,test}.jsonl   (run from backend/)
backend/.venv/Scripts/python -m ml.router_data               # → data/fin_router.jsonl
backend/.venv/Scripts/python -m ml.sentiment_data            # → data/sentiment_{train,val,test}.jsonl
backend/.venv/Scripts/python -m ml.indian_qa                 # → data/indian_finance_qa.jsonl, data/refusals.jsonl

# classifiers, sklearn rungs (CPU, 1–4 min each) → artifacts/{categoriser,sentiment}/sklearn.joblib + report_sklearn.json,
# artifacts/fin_router.joblib + artifacts/fin_router/report.json
backend/.venv/Scripts/python -m ml.train_categoriser
backend/.venv/Scripts/python -m ml.train_sentiment
backend/.venv/Scripts/python -m ml.train_router

# DistilBERT rungs (GPU, ~1 min each) → artifacts/<model>/{model_quantized.onnx,tokenizer.json,config.json,deploy.json,report.json,confusion.png}
set PYTHONUTF8=1
training/.venv/Scripts/python training/classifiers/train_bert.py --task categoriser --epochs 4
training/.venv/Scripts/python training/classifiers/train_bert.py --task sentiment

# sphura-fin-1.7b
training/.venv/Scripts/python training/sft/build_data.py
training/.venv/Scripts/python training/sft/train.py --run sphura-fin-1.7b
training/.venv/Scripts/python training/sft/export.py --run sphura-fin-1.7b     # merge → GGUF q8_0 → ollama create sphura-fin-1.7b
backend/.venv/Scripts/python training/sft/scope_filter.py                      # optional: off-topic-filtered mix → training/data/sft_scoped/
training/.venv/Scripts/python training/sft/eval.py --run sphura-fin-1.7b       # → artifacts/finetune/report.json

# tests
backend/.venv/Scripts/python -m pytest -q backend/tests/test_fin_ml.py
```

Seeds: categoriser 2026, router 1729, sentiment splits 7, sklearn splits/CV 42, SFT mix 2026, SFT 42.
Logistic regression and the embeddings are deterministic; GPU fine-tunes vary by ±0.5 pt between runs.

---

## 8. Limitations and honest notes

* **Synthetic categoriser training data.** The narrations are generated; the author-labelled test set is the only
  real-looking signal and it was written by the same person who wrote the generator (with different formats on
  purpose). Real statements from more banks would be the next step; `mitulshah/transaction-categorization` could not
  be used (gated).
* **The transformer did not win the categoriser.** Reported as measured: TF-IDF + LR 98.6 % vs DistilBERT 95.4 %. The
  app deploys the winner and keeps the ONNX model as an alternative.
* **Sentiment labels are noisy** (PhraseBank 50 % agreement) and the model is English-only; Hindi headlines fall back to
  the lexicon's neutral.
* **Router**: templated data inflates the random-split score; the unseen-template CV (92.1 %) and the hand-written
  subset (86.4 %, n = 59) are the better estimates. Hinglish coverage is thin.
* **SFT data**: Fino1 reasoning paths were unavailable (gated), so the FinQA slice teaches only "the answer is X";
  the judged comparison uses a 4B local judge, which is weaker and may favour fluent-but-wrong answers; MMLU-mini
  with ~114 items has wide confidence intervals and is a sanity check, not a benchmark.
* **Facts drift.** The Indian QA set encodes rules as of October 2026 (Finance Act 2025 slabs, GST 2.0 rates). Tax
  and GST answers must be re-checked each Budget; `finance_rules.yaml` is the single place the calculator reads.
