# Dataset cards — Sphura finance models

Every dataset the finance models train or evaluate on, with source, licence, size, how it was built and what was
checked by hand. Counts are the committed files' line counts (`wc -l`). Raw downloads live in `training/data/raw/`
(git-ignored); everything in this folder is derived from them by the scripts named below.

| File | Rows | Built by | Used by |
|---|---|---|---|
| `categoriser_train.jsonl` | 6,817 | `ml/categoriser_data.py` | categoriser (TF-IDF+LR, bge+LR, DistilBERT) |
| `categoriser_test.jsonl` | 430 | `ml/categoriser_test_set.py` (author-labelled) | categoriser test set |
| `fin_router.jsonl` | 2,123 | `ml/router_data.py` | finance intent router |
| `sentiment_train.jsonl` / `_val` / `_test` | 12,296 / 1,419 / 2,861 | `ml/sentiment_data.py` | sentiment (TF-IDF, DistilBERT) |
| `indian_finance_qa.jsonl` | 371 | `ml/indian_qa/` (author-written) | SFT + judge/finance evals |
| `refusals.jsonl` | 155 | `ml/indian_qa/refusals.py` (author-written) | SFT + off-topic eval |
| `training/data/sft/*.jsonl` (not committed) | 3,134 train / 349 held-out + 4 × 100 eval sets | `training/sft/build_data.py` | sphura-fin-1.7b |

## 1. Transaction categoriser (`categoriser_train.jsonl`, `categoriser_test.jsonl`)

**Task.** 14-way classification of a bank-statement narration plus its direction: `salary, rent, groceries, dining,
travel, fuel, utilities, shopping, subscriptions, emi_loan, investments, transfers, fees, cash` (display names in
`ml/categoriser_data.DISPLAY`). The two credit-only dashboard categories *Refunds* and *Interest* stay rule-based
(`app/features/finance/categorize.py`) and *Other* is the fallback. Model input = `"<credit|debit> | <narration>"`.

**Construction (train, 6,817 rows).**
* 6,720 generated narrations: Indian bank export formats (HDFC/SBI/ICICI/Axis/Kotak styles of UPI, POS, NEFT/IMPS/RTGS,
  ACH/NACH mandates, ATM, BillDesk/BBPS, EMI/SI) × merchant/payee lists (33–63 merchants per class, 60 person names,
  65 employers, 19 rent platforms) × noise (lower/title case, dropped separators, truncation, masked digits, trailing
  city codes, Hinglish notes). Fixed seed 2026, per-template caps, de-duplicated on a lower-case alphanumeric key.
  ~480 rows per class.
* 97 rows from `samples/bank_statement_demo.csv` (the demo statement), labelled by the author by substring rules
  (`SAMPLE_LABELS`); refund/interest credits skipped.
* `mitulshah/transaction-categorization` (MIT) was planned as an India slice but the repository is **gated on Hugging
  Face** (401 without a token on this machine), so it is not included. Its 10 coarse categories would in any case
  only map cleanly onto 4 of our 14 classes.

**Test set (430 rows, author-labelled).** Written and labelled by hand by the project author (October 2026) in
`ml/categoriser_test_set.py`, then cross-checked against the rule categoriser; disagreements were resolved by reading
the narration (e.g. `UPI-RAHUL SHARMA-…-rent for oct` → rent, `POS … IOCL SRI SAI SERVICE STN` → fuel,
`GST ON SMS CHG` → fees). The narrations deliberately use banks, merchants, cities, spellings and layouts the
generator does not produce (Canara/Union/HSBC/Standard Chartered formats, regional merchants, credit-card statement
wording, truncated exports), so the score measures generalisation rather than memorisation. 24–36 rows per class; no
test narration key appears in the training set (checked by `tests/test_fin_ml.py`).

**Spot check.** 40 random generated rows were read by the author: all 40 labels agreed with the intended class; the
only ambiguity found (a `RAZORPAY*NOBROKER` row that could be read as a platform fee) was accepted as rent.

**Licence.** Project-authored (same licence as the repository). Merchant names are used descriptively.

## 2. Finance intent router (`fin_router.jsonl`)

**Task.** 6 labels = branches of the LangGraph: `spending, documents, market, explain, advice, out_of_scope`.

**Construction (2,123 rows).** 243 hand-written boundary cases (`router_data.HARD`: "TCS share price today" → market vs
"what is TCS?" → explain vs "should I buy TCS?" → advice; "python script to parse my bank CSV" → out_of_scope;
Hinglish rows) + 1,880 templated messages: 48–56 templates per label × typed slot vocabularies (30 slots: categories,
periods, documents, ratios, stocks, indices, funds, FX pairs, concepts, calculations, comparisons, coding tasks,
dishes, sports, subjects, places, health, gadgets …) × phrasing noise (prefix/suffix, casing, dropped punctuation).
Seed 1729, per-template cap, de-duplicated; hand-written rows are inserted first so a template never shadows one.
Per label: out_of_scope 425, explain 373, spending 335, advice 331, documents 330, market 329.

**Evaluation protocol.** Stratified 20 % hold-out for the headline numbers, plus a 5-fold *unseen-template* group CV
(whole templates held out; hand-written rows are their own groups) that measures generalisation to new phrasing.

**Licence.** Project-authored.

## 3. Financial sentiment (`sentiment_{train,val,test}.jsonl`)

**Sources.**
* Financial PhraseBank v1.0, `Sentences_50Agree` (Malo et al., 2014): 4,846 sentences from financial news labelled
  positive / neutral / negative by 5–8 annotators; the 50 %-agreement file is the largest. **Licence CC BY-NC-SA 3.0
  (academic / non-commercial use).** Read from the cached `FinancialPhraseBank-v1.0.zip`.
* `zeroshot/twitter-financial-news-sentiment` (TFNS): 9,543 train + 2,388 validation finance tweets labelled
  Bearish / Bullish / Neutral. **Licence MIT.** `https://t.co/…` links are stripped.

**Label map.** Bearish → negative, Bullish → positive, Neutral → neutral.

**Splits (seed 7, stratified by label within each source).** PhraseBank 80/10/10 → 3,868 / 483 / 484; TFNS: the
official validation file is our test set (2,377 after de-duplication), 10 % of the official train file is val
(936), the rest train (8,428). Exact duplicates are kept once and never cross splits (`tests/test_fin_ml.py`).
Test = 2,861 rows (neutral 1,844, positive 611, negative 406).

**Spot check.** 30 random test rows read by the author: 28 agreed with the label; the 2 disagreements were neutral
PhraseBank sentences that read mildly positive — the known annotator-agreement noise of the 50 % file.

## 4. Indian finance QA (`indian_finance_qa.jsonl`) and refusals (`refusals.jsonl`)

**Indian finance QA — 371 rows, author-written.** `{"question", "answer", "topic", "source"}` over 17 topics:
GST (33: slabs after the September 2025 rationalisation, ITC and blocked credits, registration, composition, RCM,
returns, e-invoicing), ITR forms and filing (24), income-tax regimes and slabs (26), deductions 80C/80D/80CCD/80E/
80G (23), TDS/TCS (13), capital gains (12), UPI limits and failed-transaction rules (20), EPF/PPF/NPS/gratuity (28),
credit score and cards (20), loans and EMI maths (28), deposits and banking (20), RBI basics (12), mutual-fund types
(32), SIP and compounding maths (24), markets/SEBI basics (28), insurance (8), business accounting ratios (20).
Every row carries a one-line **source note** (section of the Act, regulator circular, or "computed with …").
Rates follow `backend/app/finance_rules.yaml` (Finance Act 2025 slabs carried into FY 2026-27) so the model and the
calculator tools agree; EMI/SIP/FD/PPF numbers were produced by the same formulas as the app's tools before being
written down (see the docstrings). Hinglish variants are included for the persona questions.

**Refusals — 155 rows.** 155 hand-written off-topic prompts (coding, recipes, sports, homework, travel, health,
entertainment, chit-chat, general knowledge, Hinglish) paired with one of six refusal templates and one of eight
finance alternatives, chosen deterministically. Every answer contains the phrase "not about finance", which the
evaluation's refusal detector keys on.

**Licence.** Project-authored. Facts are the author's summary of public law and regulator material as of
October 2026; they are not legal or tax advice.

## 5. SFT mix for sphura-fin-1.7b (`training/data/sft/`, built by `training/sft/build_data.py`)

| Slice | Source | Licence | Train | Held-out | Notes |
|---|---|---|---|---|---|
| `sujet_qa` | sujet-ai/Sujet-Finance-Instruct-177k, task `qa` (finance-alpaca StackExchange answers) | Apache-2.0 | 990 | 110 | finance-keyword + length filters; forum noise dropped |
| `sujet_qa_with_context` | same, task `qa_with_context` (FinTalk-19k, ConvFinQA, finqabench; alpaca rows only with ≥3 finance terms) | Apache-2.0 | 630 | 70 | |
| `sujet_conversation` | same, task `qa_conversation`, `amphora/lmsys-finance` only (the "contrived" set is synthetic) | Apache-2.0 | 301 | 34 | |
| `sujet_sentiment` | same, task `sentiment_analysis` (PhraseBank + TFNS rows) | Apache-2.0 | 225 | 25 | capped at ≤10 % of the Sujet subset |
| `finqa` | ChanceFocus/flare-finqa **train** split (FinQA, MIT) — gold number as the answer | MIT | 515 | 57 | 572 of 6,251 rows fit 1,024 tokens with the system prompt |
| `indian_qa` | `indian_finance_qa.jsonl` | project | 334 | 37 | |
| `refusal` | `refusals.jsonl` | project | 139 | 16 | |
| **total** | | | **3,134** | **349** | mean 403 tokens, max 1,024 |

* **Fino1 substitution.** `TheFinAI/Fino1_Reasoning_Path_FinQA` is gated (401 without a token), so the FinQA slice
  uses the same FinQA questions from the cached `flare-finqa` parquet without GPT-4o reasoning paths; answers are
  `The answer is <gold>.`
* **Hold-out before training.** 10 % of every slice (seed 2026) is held out and used for perplexity and the judged
  comparison; nothing in `holdout.jsonl` is trained on.
* **Evaluation sets (100 rows each).** `finqa_eval.jsonl` = flare-finqa **test** rows with numeric gold answers that
  fit the window (never trained on); `offtopic_eval.jsonl` = the router's hand-written out_of_scope rows + held-out
  refusal prompts + templated out_of_scope rows; `finance_eval.jsonl` = the router's hand-written finance rows;
  `judge_eval.jsonl` = held-out `indian_qa` / `sujet_*` QA rows with their reference answers.
* Every row is `{"messages": [system, user, assistant], "source", "meta"}` with the shared system prompt
  (`training/sft/prompts.py`) rendered through the Qwen3 chat template with thinking disabled.
* **Spot-check finding: off-topic rows in the Sujet slices.** Sujet-Finance-Instruct aggregates several instruction
  sets, and the finance-keyword filter let general tasks through. Running the trained router over the Sujet prompts
  labels **556 of 2,146 training rows out_of_scope** (sujet_qa 415 / 990, conversation 84 / 301, qa-with-context
  52 / 630, sentiment 5 / 225); in a random sample of 25 of them, 24 are clearly non-finance ("Write a short story
  about a robot…", "Name three food items high in proteins") and 1 is borderline (e-commerce). These answered
  off-topic rows contradict the 139 refusal rows. **The first SFT run (`sphura-fin-1.7b`) was trained on the
  unfiltered mix** (found while it was running), so its refusal numbers should be read with this in mind.
  `training/sft/scope_filter.py` (backend venv) writes a filtered copy to `training/data/sft_scoped/` — same rule
  applied to train, hold-out and the judge set: **2,578 train / 286 held-out / 100 judge rows** (`stats.json`,
  dropped rows in `dropped.jsonl`). Train on it with `train.py --data training/data/sft_scoped`.

## 6. RAG benchmark (`ml/eval_corpus/`)

Unchanged from the earlier wave: 18 documents written for the benchmark and 122 questions with gold passages;
`ml/artifacts/rag_eval.json` is read by `GET /api/ml/report` as `ragEval`.
