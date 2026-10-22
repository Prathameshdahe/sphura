# Sphura Finance — redesign plan (source of truth for the finance pivot)

Sphura becomes a **finance-only AI assistant**: personal finance, business accounting, investing & markets (educational), and finance education.
Everything below is binding for builders. CONTRACT.md still defines the HTTP/SSE contract; this file lists what changes.
Model/package choices were verified on 2026-10-22 against official docs (Ollama library, Hugging Face cards, PyPI, Groq/Gemini docs).

## 1. Product scope

| Mode | What the user does | Engine |
| --- | --- | --- |
| **Spending** | Uploads bank statements (CSV/XLSX/PDF) and asks "where does my money go?", "recurring charges?", "can I save 20%?" | Deterministic pandas analytics (existing `app/features/finance`) + **trained transaction categoriser** |
| **Documents** | Uploads balance sheets, P&L, invoices, policies, annual reports; asks grounded questions | Existing hybrid RAG (dense + BM25 + RRF + cross-encoder) with page citations |
| **Markets** | Asks about a stock / mutual fund / index / FX, or finance news | `yfinance` quotes (cached, NSE `.NS` / BSE `.BO` / global) + finance-restricted web search; **trained sentiment model** labels news |
| **Explain** | "What is SIP?", "EMI on 10 lakh at 9% for 5 years", "old vs new tax regime", "what is EBITDA?" | LLM with calculator tools (EMI, SIP, FD/RD, tax slab, ratios) |
| **Out of scope** | Anything not finance | Templated refusal from the **trained intent router** (no LLM call) |
| **Advice request** | "Should I buy X?" | Educational framing + "not a registered adviser" line; never a personalised buy/sell/allocation recommendation |

Removed (delete code, routes, nav, tests): Paper Lens (`features/papers`, `api/papers.py`, `/papers*`), Workspace reader (`features/workspace`, `api/workspace.py`, `/workspace`), Knowledge graph (`features/graph`, `api/graph.py`, `/graph`), Model arena (`features/arena`, `api/arena.py`, `/arena`), Deep Research plugin (`features/research`), Focus mode page and `/lab` from the product nav (keep the MorphOrb component file; `/lab` may stay as a dev-only route).
Kept: documents, finance dashboard, verified answers (NLI meter), memory, feedback, finance web search, hands-free voice, ML Lab (renamed "Model Lab").

## 2. Models (hybrid: local + Groq + Gemini)

| Role | Choice | Notes |
| --- | --- | --- |
| Local LLM (default when no key) | Ollama **`qwen3.5:4b`** (Apache-2.0, tools + thinking, 3.3–4 GB) | Set `think: false` for classification/tools; `num_ctx` 8192 |
| Local LLM (NVIDIA showcase) | Ollama **`nemotron-3-nano:4b`** (NVIDIA Nemotron Open Model License, tools, 2.8 GB) | Listed in the model picker as "NVIDIA Nemotron 3 Nano"; English only |
| Fine-tuned local model | **`sphura-fin-1.7b`** = Qwen3-1.7B + our QLoRA (see §6), imported into Ollama | Appears in the picker once trained; falls back to qwen3.5:4b if absent |
| Cloud fast | Groq `openai/gpt-oss-20b` (fallback `llama-3.1-8b-instant`) | 8K TPM on free tier → keep prompts < 6K tokens |
| Cloud strong | Groq `openai/gpt-oss-120b`; Gemini `gemini-3.8-flash` (1M ctx, PDF/audio in) | Gemini is the fallback when Groq 429s and vice-versa |
| Cloud cheap | Gemini `gemini-3.5-flash-lite` | title generation, memory extraction, judge |
| Embeddings / reranker | keep `BAAI/bge-small-en-v1.5` + `Xenova/ms-marco-MiniLM-L-6-v2` on CPU (fastembed) | do not move RAG to the GPU; Ollama owns the 6 GB |
| STT | Groq `whisper-large-v3-turbo` (server-side, Hindi + English); browser Web Speech as instant fallback | `POST /api/voice/transcribe` multipart webm/opus |
| TTS | Gemini `gemini-3.8-flash-lite-tts` (server-side, Hindi + English); browser `speechSynthesis` fallback | `POST /api/voice/speak` → audio/wav |
| Sentiment | our fine-tuned DistilBERT (Financial PhraseBank + TFNS) | never ship ProsusAI/finbert weights (CC BY-NC-SA) |

Model routing inside the graph: **classification and tool-light steps run locally**; **drafting and synthesis prefer cloud** when a key exists, else local; verification (NLI) is always local. A user can pin any model from the picker.

## 3. Agent = LangGraph `StateGraph` (replaces `app/agent/orchestrator.py`)

Package pins (Python 3.13 OK): `langgraph==1.2.16 langchain==1.4.7 langchain-core==1.6.13 langchain-groq==1.1.3 langchain-google-genai==4.4.2 langchain-ollama==1.1.0 langgraph-checkpoint-sqlite==3.1.2 aiosqlite==0.22.1 langchain-tavily==0.2.18 yfinance==1.7.0`. Do **not** use `create_react_agent` (deprecated) or `create_pandas_dataframe_agent` (executes code). Do not add `langchain-qdrant`: retrieval stays on our tested `app.rag.service`.

```
START → guard_in → classify ─┬─ spending   → analytics ─┐
                             ├─ documents  → retrieve ──┤
                             ├─ market     → market ────┤→ draft ⇄ tools → verify → finalize → END
                             ├─ explain ───────────────┘
                             ├─ advice     → draft (disclaimer system prompt) …
                             └─ out_of_scope → refuse → END
```

- `FinState(TypedDict)`: `messages: Annotated[list, add_messages]`, `intent`, `intent_confidence`, `user_id`, `conversation_id`, `doc_ids`, `web_search`, `model_id`, `effort`, `analytics: dict|None`, `retrieved: list[dict]`, `market: dict|None`, `sources: list[dict]` (CONTRACT `Source`), `steps: list[dict]`, `draft: str`, `verification: dict|None`, `refusal: str|None`, `memory_used: int`, `title: str|None`.
- **guard_in**: regex-redact card/account/Aadhaar/PAN numbers in the user text before anything is logged or sent to a cloud model.
- **classify**: the trained intent router (`backend/ml/artifacts/fin_router.joblib`) first; if confidence < 0.6 or artifact missing, structured output from the local model (`with_structured_output`). Emits step `router` ("Spending question · 94%").
- **analytics**: existing `app.features.finance` report over the user's ready tabular documents (all, if none attached) + the trained categoriser; the compact markdown summary becomes a `doc` source so the answer cites exact figures.
- **retrieve**: `app.rag.service.search_documents(user_id, query, doc_ids, k=8)` → `doc` sources.
- **market**: tools `get_quote(symbol)`, `get_history(symbol, period)` (yfinance; SQLite TTL cache ≥ 60 s; single-flight; backoff; NSE `.NS` suffix auto-added for Indian names via a small symbol map), `finance_news(query)` (existing `app.tools.web` with `include_domains` biased to finance/news; results → `web` sources; the sentiment model labels each headline), `fx_rate`.
- **draft**: LangChain chat model (`init_chat_model` with `groq:` / `google_genai:` / `ollama:` prefixes) with tools bound: `emi`, `sip_future_value`, `fd_rd_maturity`, `income_tax_estimate` (India FY 2026-27 **new regime** slabs stored in `backend/app/finance_rules.yaml` with the source URL and date — the agent must say which FY/regime it used), `ratio_calculator`, `get_quote`, `finance_news`, `search_documents`. Bounded loop (effort fast 1 / balanced 3 / deep 6). Provider fail-over Groq ⇄ Gemini → local before the first token.
- **verify**: existing `app.features.verify` NLI over the draft vs sources → `verification` event.
- **finalize**: title, memory write (existing memory plugin, rebuilt as a node), persist Message exactly as today.
- Checkpointer: `AsyncSqliteSaver` at `data/graph.db`, `thread_id = conversation_id` (opened in FastAPI lifespan). Our `messages` table remains the source of truth for the UI; the checkpointer gives the graph its own state.
- Export: `GET /api/agent/graph` → `{mermaid: str, nodes: [...]}` from `graph.get_graph().draw_mermaid()`; the Model Lab page renders it.
- Streaming: `graph.astream(..., stream_mode=["updates","messages","custom"], version="v2")`; map `updates` → CONTRACT `status`/`step`, `messages` from the `draft` node → `delta`, custom writer → `sources`/`step`. **The SSE event names and payloads in CONTRACT.md do not change**, so the existing frontend streaming code keeps working. Phase labels: classify "Understanding your question" (thinking), analytics "Crunching your statements" (analyzing), retrieve "Reading your documents" (reading), market "Fetching market data" (searching), draft "Writing the answer" (composing), verify "Checking claims against sources" (analyzing).
- `ChatRequest.mode` becomes optional/ignored (the classifier decides); keep `webSearch` (forces the market/news branch) and `docIds`.

## 4. UI — "Rose quartz evening", product-level, symmetric

Palette (from the user): `#64242F` maroon · `#B44446` brick · `#FC8F8F` blush · `#DFD9D8` rose-grey.
Light theme (default): background `#F7F3F3`, surface/sidebar `#DFD9D8` at 60–100 %, card `#FFFCFC`, primary `#64242F`, primary-foreground `#FFF7F7`, accent `#B44446`, highlight/ring `#FC8F8F`, text `#2A1B1E`, muted text `#7A6368`, border `#E8DEDE`, success `#2F7D5B`, warning `#B8860B`, danger `#B44446`. Dark theme: background `#1B1114`, card `#241619`, sidebar `#20141A`, primary `#FC8F8F`, primary-foreground `#2A1B1E`, accent `#D86A6C`, text `#F3EAEA`, muted `#B59FA3`, border `#3A262B`. Brand gradient = `#64242F → #B44446 → #FC8F8F`. Set these as the shadcn tokens in `index.css` (`--sphura-1/2/3` likewise) so every component follows. Fonts stay (Fraunces brand, Geist UI, Source Serif prose). The spark logo and orb use the new gradient.

Layout rules: one 3-column rhythm (sidebar 272 px · centred main `max-w-3xl` · optional right panel 360 px for the dashboard/artifacts); consistent page header (title + one-line subtitle + primary action, same height everywhere); 8-px spacing scale; cards with equal padding and radius `--radius 0.9rem`; every grid symmetric (2/3/4 columns, equal heights); mobile 360 px.

Motion (framer-motion, `MotionConfig reducedMotion="user"`): page transitions (fade + 8 px rise, 220 ms), staggered lists (40 ms), number count-up on dashboard KPIs, charts animate in, orb/logo states as today, composer send pulse, chips spring in, skeletons shimmer. No gratuitous motion; nothing longer than 400 ms except the orb.

Pages: `/` Home (finance greeting, 4 symmetric starter cards: "Analyse my statement", "Explain a concept", "Check a stock", "Ask about a document"; composer with model picker + mic), `/c/:id` chat, `/documents`, `/dashboard` (was `/finance`: KPIs, monthly bars, category donut, top transactions, ratios for balance sheets, insights, "Discuss in chat"), `/markets` (quote search with sparkline, news with sentiment chips, watchlist in memory), `/lab` → "Model Lab" (router + categoriser + sentiment metrics, RAG benchmark, groundedness stats, LangGraph diagram, fine-tune results), `/memory`, `/login`, `/signup`. Voice mode overlay stays (server-side STT/TTS with browser fallback).

## 5. Training (all on this laptop; GPU jobs run one at a time; stop Ollama before the SFT)

Training venv: `training/.venv` (torch cu128, transformers, peft, trl, datasets, bitsandbytes, sentence-transformers, scikit-learn). Artifacts land in `backend/ml/artifacts/` and are loaded by the app.

| # | Model | Data | Method | Report |
| --- | --- | --- | --- | --- |
| 1 | Transaction categoriser (12 classes: salary, rent, groceries, dining, transport, fuel, utilities, shopping, subscriptions, emi_loan, investments, transfers, fees, cash, health, education, other → pick 12–16 and document) | 6–10k labelled narrations: Indian UPI/NEFT/IMPS templates we generate (merchant lists × formats), `mitulshah/transaction-categorization` India slice (MIT), our sample statement; 400 rows hand-labelled by the author for the test set | TF-IDF+LR → MiniLM+LR → DistilBERT fine-tune (GPU, ~15 min) | accuracy, macro-F1, confusion matrix, per-class F1; ablation table |
| 2 | Financial sentiment | Financial PhraseBank `sentences_50agree` (CC BY-NC-SA, academic) + `zeroshot/twitter-financial-news-sentiment` (MIT) | DistilBERT fine-tune (~5 min) | acc/F1 on both test sets vs literature (FinBERT 0.86 acc on FPB) |
| 3 | Finance intent router (spending / documents / market / explain / advice / out_of_scope) | ≥1,500 generated + ≥200 hand-written examples, ≥300 out-of-scope | MiniLM embeddings + LR (same recipe as today's router) | accuracy, macro-F1, confusion; unseen-template hold-out |
| 4 | **`sphura-fin-1.7b`**: QLoRA SFT of `Qwen/Qwen3-1.7B` | ~4k rows: `sujet-ai/Sujet-Finance-Instruct-177k` stratified subset (QA, QA-with-context, conversation; cap sentiment ≤ 10 %), `TheFinAI/Fino1_Reasoning_Path_FinQA` (≤ 1,024 tokens), **our Indian finance QA set** (≥ 300 authored pairs: GST, ITR forms, 80C/80D, EPF/PPF/NPS, UPI limits & failed-txn rules, SIP/EMI maths, credit score; each with a source note) + ≥ 150 refusal rows | 4-bit, r=16, lr 2e-4, bs 1 × GA 16, seq 1024, 1 epoch, fp16, `adamw_8bit`, gradient checkpointing; save every 50 steps | held-out loss/perplexity base vs tuned; FinQA numeric EM on 100 held-out Fino1 rows (normalised, 1 % tolerance); refusal rate on 100 off-topic prompts; 100-item judged comparison (local judge if no cloud key; say so); MMLU-mini sanity (`--limit 100`) |
| 5 | Export | merge LoRA → safetensors → `ollama create sphura-fin-1.7b --quantize q4_K_M -f Modelfile` (fallback: `llama.cpp` `convert_hf_to_gguf.py` f16) | smoke test: 10 finance prompts through Ollama | |

Every dataset gets a card in `backend/ml/data/README.md` (source, license, size, how built, spot-check agreement). `backend/ml/README.md` is rewritten for the finance models (numbers from artifacts only).

## 6. Persona tests (run before the demo, fix what fails)

1. **Asha, college student** — uploads `samples/bank_statement_demo.csv`: "where did my money go last month?", "any subscriptions I forgot?", "how much can I save if I cut dining by half?"
2. **Rahul, salaried** — "I earn 12 LPA, which tax regime is better?", "EMI for 25 lakh home loan at 8.5% for 20 years", "how does 80C work?"
3. **Meera, small business** — uploads `samples/balance_sheet_2025.csv`: "is my liquidity healthy?", "current ratio and what it means", "what should I watch?"
4. **Vikram, beginner investor** — "what is a SIP?", "TCS share price today", "news about HDFC Bank", "should I buy Reliance?" (must get education + disclaimer, not advice)
5. **Off-topic** — "write a Python script", "recipe for biryani", "who won the match?" → polite refusal, zero LLM cost, no hallucinated finance.
6. **Voice** — Rahul's question spoken; answer read back.
Each persona runs through the API (SSE) and the browser; record latency per step; everything must work with no cloud key (local model) and, when keys exist, with Groq/Gemini.

## 8. API additions (camelCase JSON, `{"detail": string}` errors, auth cookie — same conventions as CONTRACT.md)

```ts
// markets (backend/app/api/market.py)
GET /api/market/search?q=tcs            → { matches: { symbol: string; name: string; exchange: string }[] }
GET /api/market/quote?symbol=TCS.NS     → Quote { symbol; name: string; price: number; currency: string; change: number; changePercent: number;
                                                   dayHigh?: number|null; dayLow?: number|null; asOf: ISODate; source: "yfinance"; delayed: true }
GET /api/market/history?symbol=&period=1mo|3mo|6mo|1y|5y → { symbol: string; period: string; points: { date: string; close: number }[] }
GET /api/market/news?query=HDFC%20Bank  → { items: NewsItem[] }   // NewsItem { title; url; domain; snippet; publishedAt?: string|null;
                                                                    //   sentiment: { label: "positive"|"neutral"|"negative"; score: number } }
// voice (backend/app/api/voice.py)
POST /api/voice/transcribe  multipart `audio` (webm/opus or wav, ≤ 25 MB, ≤ 120 s) → { text: string; language: string|null; provider: "groq"|"local" }  (503 when no STT: client uses Web Speech)
POST /api/voice/speak       { text: string (≤ 2000 chars); voice?: string } → audio/wav bytes                                               (503 when no TTS: client uses speechSynthesis)
// agent
GET /api/agent/graph        → { mermaid: string; nodes: { id: string; label: string }[]; edges: { source: string; target: string; label?: string|null }[] }
// model lab (replaces /api/ml/router + /api/ml/rag-eval; keep /api/ml/verification)
GET /api/ml/report → ModelLabReport {
  models: ModelCard[];              // one per trained classifier
  finetune: FinetuneReport | null;  // sphura-fin-1.7b
  ragEval: RagEvalReport;           // unchanged shape from CONTRACT.md
  generatedAt: ISODate;
}
ModelCard { key: "categoriser"|"sentiment"|"router"; name: string; task: string; model: string; trainedAt: ISODate;
            dataset: { name: string; train: number; test: number; license: string; note: string };
            metrics: { accuracy: number; macroF1: number }; baseline?: { name: string; accuracy: number; macroF1: number } | null;
            labels: string[]; perClass: { label: string; precision: number; recall: number; f1: number; support: number }[];
            confusion: number[][]; extras?: Record<string, number> | null }     // e.g. { unseenTemplates: 0.93 }
FinetuneReport { available: boolean; name: string; base: string; method: string; rows: number; steps: number; epochs: number; trainMinutes: number;
                 gpu: string; lora: { r: number; alpha: number; targets: string[] };
                 eval: { heldoutPerplexityBase: number|null; heldoutPerplexityTuned: number|null; finqaEmBase: number|null; finqaEmTuned: number|null;
                         refusalRate: number|null; falseRefusalRate: number|null; judgeWinRate: number|null; judgeModel: string|null; mmluMiniBase: number|null; mmluMiniTuned: number|null };
                 ollamaTag: string|null; notes: string[] }
POST /api/ml/train/{key}  (admin) → ModelCard   // retrain a classifier in a thread
```
Frontend mirrors these in `frontend/src/lib/feature-types.ts` (replace the removed paper/workspace/graph/arena types). `ChatRequest.mode` stays in the type for compatibility but the UI no longer shows a mode switch.

## 7. Work split (strict file ownership, parallel)

- **backend-agent**: `backend/app/agent/**` (new LangGraph graph, tools, SSE mapping), `backend/app/api/chat.py`, `backend/app/api/agent.py`, `backend/app/api/voice.py`, `backend/app/features/{market,voice}/**`, `backend/app/finance_rules.yaml`, `backend/app/llm/catalog.py` (model list), deletion of papers/workspace/graph/arena/research backend code and their tests, `backend/tests/test_fin_*.py`.
- **frontend**: everything under `frontend/src` except `components/ui/{sphura-*,ai-*}.tsx` and `lib/orb-engine.ts` (restyle via tokens only): theme, deletions, new pages, motion, voice client.
- **training**: `training/**`, `backend/ml/**`, `backend/app/features/{router,finance/categorize.py,sentiment}/**` (load the new artifacts), `backend/app/api/ml.py`.
- Shared read-only: CONTRACT.md, this file, `app/rag/**`, `app/features/{finance,verify,memory}/**` (except where listed).
