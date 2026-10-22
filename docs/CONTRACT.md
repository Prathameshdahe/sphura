# Sphura — API contract (source of truth)

Frontend (`frontend/src/lib/types.ts`) and backend (`backend/app/schemas.py`) MUST match this file exactly.
If you need to change the contract, change this file, `types.ts` and `schemas.py` together.

## Conventions
- Base path: `/api`. All JSON keys are **camelCase** (backend uses pydantic `alias_generator=to_camel`, `populate_by_name=True`, and always serialises `by_alias=True`).
- IDs are UUID4 strings. Timestamps are ISO-8601 UTC strings (`2026-10-21T18:00:00Z`).
- Errors: every non-2xx response body is `{"detail": "<human readable string>"}` — never a list/object (the backend flattens FastAPI 422 validation errors into one string).
- Auth: login/register set an **httpOnly cookie `sphura_session`** (JWT, SameSite=Lax, path=/). The backend also accepts `Authorization: Bearer <jwt>` (used by tests). The frontend uses `credentials: "include"` and never touches the token. 401 → frontend redirects to `/login`.
- Dev: Vite proxies `/api` → `http://localhost:8000`. Docker: nginx serves the SPA and proxies `/api` → backend. So the browser is always same-origin.

## Model ids
`"<provider>:<model>"`, split on the FIRST colon. Providers: `gemini`, `groq`, `ollama`, `lmstudio`, `mock` (tests only, enabled by `SPHURA_ENABLE_MOCK=1`).
Examples: `groq:llama-3.3-70b-versatile`, `gemini:gemini-2.5-flash`, `ollama:qwen2.5:7b`, `lmstudio:qwen/qwen2.5-coder-14b`.
All providers are called through their OpenAI-compatible Chat Completions endpoints (streaming + tool calling).

## Types
```ts
type ISODate = string;
type ChatMode = "chat" | "research" | "finance";   // "research" = Deep Research (wave 2); Day-1 backend treats it like chat with web search on
type Effort = "fast" | "balanced" | "deep";          // max agent tool rounds: 1 / 3 / 6
type Phase = "thinking" | "searching" | "reading" | "analyzing" | "composing";

interface User { id: string; email: string; name: string; isAdmin: boolean; createdAt: ISODate }

interface ModelInfo {
  id: string;                 // "groq:llama-3.3-70b-versatile"
  provider: "gemini" | "groq" | "ollama" | "lmstudio" | "mock";
  label: string;              // "Llama 3.3 70B"
  description: string;        // "Groq · ultra fast"
  available: boolean;         // key present / local server reachable
  reason?: string | null;     // why unavailable, e.g. "Set GROQ_API_KEY in .env"
  supportsTools: boolean;
  supportsVision: boolean;
  isDefault: boolean;
}

interface ConversationSummary { id: string; title: string; mode: ChatMode; pinned: boolean; createdAt: ISODate; updatedAt: ISODate }

interface Source {
  index: number;              // 1-based; the answer cites it as [1], [2] ...
  type: "web" | "doc";
  title: string;
  url?: string | null;        // web
  domain?: string | null;     // web, e.g. "arxiv.org"
  docId?: string | null;      // doc
  filename?: string | null;   // doc
  page?: number | null;       // doc (1-based)
  snippet: string;            // <= 400 chars of the supporting text
  score?: number | null;
}

interface ToolStep {
  id: string;
  name: string;               // "web_search" | "read_page" | "search_documents" | ...
  label: string;              // "Searching the web for “transformer attention”"
  status: "running" | "done" | "error";
  detail?: string | null;     // "6 results" / error text
  startedAt: ISODate;
  finishedAt?: ISODate | null;
}

interface AttachmentRef { docId: string; filename: string; mimeType: string; sizeBytes: number }

interface Message {
  id: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string;            // markdown; assistant cites sources inline as [1]
  createdAt: ISODate;
  model?: string | null;
  status: "complete" | "stopped" | "error";
  error?: string | null;
  sources: Source[];
  steps: ToolStep[];
  attachments: AttachmentRef[];
  meta?: Record<string, unknown> | null;   // e.g. { durationMs, promptTokens, completionTokens }
}

interface ConversationDetail { conversation: ConversationSummary; messages: Message[] }

interface DocumentInfo {
  id: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  status: "queued" | "processing" | "ready" | "error";
  error?: string | null;
  pageCount?: number | null;
  chunkCount: number;
  ocrUsed: boolean;
  conversationId?: string | null;   // set when attached from a chat
  createdAt: ISODate;
}

interface ChatRequest {
  conversationId?: string | null;   // null/absent → create a new conversation
  content: string;                  // ignored when regenerate=true
  model?: string | null;            // null → server default
  webSearch: boolean;               // true → server ALWAYS searches the web first (deterministic), model may search more
  docIds: string[];                 // documents to ground on (attachments of this message + earlier ones in the chat)
  mode: ChatMode;
  effort: Effort;
  regenerate?: boolean;             // re-answer the last user message; deletes the last assistant message
  editMessageId?: string | null;    // replace that user message's content, delete everything after it, answer again
}

interface Health {
  ok: boolean; version: string;
  providers: Record<"gemini" | "groq" | "ollama" | "lmstudio", boolean>;
  search: { tavily: boolean; duckduckgo: boolean };
  vectorStore: "qdrant" | "qdrant-local";
  embeddings: string;               // embedding model name
}
```

## Endpoints
| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/api/auth/register` | `{email, password, name}` (password ≥ 8 chars) | `User` + sets cookie. The first registered user becomes admin. 409 if email exists |
| POST | `/api/auth/login` | `{email, password}` | `User` + sets cookie. 401 `"Invalid email or password"` |
| POST | `/api/auth/logout` | – | `{ok: true}`, clears cookie |
| GET | `/api/auth/me` | – | `User` (401 if not logged in) |
| GET | `/api/models` | – | `ModelInfo[]` |
| GET | `/api/health` | – | `Health` (public) |
| GET | `/api/conversations` | `?q=` optional title/content search | `ConversationSummary[]` sorted pinned first, then updatedAt desc |
| GET | `/api/conversations/{id}` | – | `ConversationDetail` (404 if not owner) |
| PATCH | `/api/conversations/{id}` | `{title?, pinned?}` | `ConversationSummary` |
| DELETE | `/api/conversations/{id}` | – | 204 |
| POST | `/api/chat` | `ChatRequest` | **`text/event-stream`** (see below) |
| POST | `/api/documents` | multipart: `file` (+ optional form field `conversationId`) | `DocumentInfo` (status `queued`; ingestion runs in background). 413 if > MAX_UPLOAD_MB, 415 if unsupported type |
| GET | `/api/documents` | `?conversationId=` optional | `DocumentInfo[]` newest first |
| GET | `/api/documents/{id}` | – | `DocumentInfo` (poll until `ready`/`error`) |
| DELETE | `/api/documents/{id}` | – | 204 (removes row, chunks, vectors and file) |

Supported uploads: `.pdf .docx .txt .md .csv .xlsx .xls .json .html .png .jpg .jpeg .webp` (images and scanned PDF pages go through OCR).

## `/api/chat` Server-Sent Events
Each event is `event: <name>\ndata: <json>\n\n`. Order: `start` → (`status` | `step` | `sources` | `delta`)* → (`done` | `error`). A `title` event may arrive any time after `start` for new conversations.

| event | data |
|---|---|
| `start` | `{conversationId, userMessage: Message, assistantMessageId, model}` |
| `status` | `{phase: Phase, label: string}` — drives the Sphura orb (thinking→program 0, searching→1, reading/analyzing→2, composing→3) |
| `step` | `ToolStep` — upsert by `id` |
| `sources` | `{sources: Source[]}` — the full cumulative list (replace, don't append) |
| `delta` | `{text: string}` — append to the assistant message |
| `title` | `{conversationId, title}` |
| `done` | `{message: Message}` — the final saved assistant message (authoritative) |
| `error` | `{message: string}` — the assistant message is saved with `status:"error"` |

Stopping: the client aborts the fetch. The server detects the disconnect, stops generation and saves the partial assistant message with `status: "stopped"`.
A heartbeat comment line (`: ping`) is sent every 15 s.

## Backend internal interfaces (between backend modules)
- `app/rag/service.py`
  - `async def search_documents(user_id: str, query: str, doc_ids: list[str] | None, k: int = 8) -> list[RetrievedChunk]` — hybrid (dense + BM25, RRF) + cross-encoder rerank, restricted to the user's documents (and to `doc_ids` if given).
  - `@dataclass RetrievedChunk: doc_id, filename, page (int|None), chunk_index, text, score, section (str|None)`
  - `def schedule_ingestion(document_id: str) -> None` and `def delete_document_artifacts(document_id: str) -> None`
- `app/llm/registry.py`
  - `def list_models() -> list[ModelInfo]`, `def resolve_model(model_id: str | None) -> ResolvedModel` (client + model name + capabilities)
  - `async def chat_stream(model_id, messages, tools=None, temperature=0.4) -> AsyncIterator[LLMChunk]` and `async def complete(model_id, messages, temperature=0.2, json_mode=False) -> str`
- `app/tools/web.py`: `async def web_search(query, max_results=6) -> list[WebResult]`, `async def read_page(url, max_chars=12000) -> PageContent`

---

# Wave 2 additions (research superpowers, real ML, wow features)

TS mirror: `frontend/src/lib/feature-types.ts` (plus the additions to `types.ts` noted below). Same conventions as above (camelCase, `{"detail": string}` errors, auth cookie, other users' resources → 404).
Backend agent features plug into chat through `backend/app/agent/plugins.py` (hooks `before_answer`, `tools`, `run_tool`, `after_answer`); each feature lives in `backend/app/features/<name>/` and its router in `backend/app/api/<name>.py`.

## Chat additions
- `ChatRequest.workspaceId?: string | null` — attach a workspace; the agent gets Claude Code-style tools `list_files(glob?)`, `grep(pattern, glob?)`, `read_file(path, startLine?, endLine?)`. File hits become sources with `type:"doc"`, `filename` = file path, `page` = start line.
- New SSE event **`verification`** (after the last `delta`, before `done`; only when the verifier ran): `{verification: Verification}`. Also persisted as `message.meta.verification`.
- New step names: `research_plan`, `router`, `memory_recall`, `workspace_list`, `workspace_grep`, `workspace_read`, `finance_analyze`, `verify`.
- `message.meta` may also carry: `router: {label, confidence, autoSearch}`, `memoryUsed: number`, `memoriesAdded: string[]`, `research: {subQuestions: string[], pagesRead: number}`, `workspace: {id, name}`, `finance: {docIds: string[]}`.
- mode `"research"` = **Deep Research**: plan 3-6 sub-questions → parallel web searches → read the best pages → a long structured, cited report (Executive summary, themed sections, Key findings, Open questions). Progress is shown through the normal `status`/`step` events.

```ts
interface VerifiedSentence {
  text: string; start: number; end: number;          // char offsets into message.content
  sourceIndexes: number[];                            // citations found in the sentence
  verdict: "supported" | "partial" | "unsupported" | "uncited";
  score: number;                                      // 0..1 entailment probability (uncited → 0)
}
interface Verification {
  score: number;                                      // 0..1 share of checkable claims supported (partial counts 0.5)
  label: "grounded" | "mostly grounded" | "partially grounded" | "ungrounded" | "not checkable";
  supported: number; partial: number; unsupported: number; uncited: number;
  model: string;                                      // e.g. "nli-deberta-v3-xsmall (ONNX)"
  sentences: VerifiedSentence[];
}
```
`POST /api/verify/{messageId}` → `Verification` (recompute + persist; owner only).

## Feedback
`POST /api/feedback` `{messageId, value: 1 | -1, comment?: string}` → `{ok: true}` (one vote per user+message, last wins).

## Memory
`MemoryItem { id: string; content: string; createdAt: ISODate; sourceMessageId?: string | null }`
- GET `/api/memory` → `{enabled: boolean, items: MemoryItem[]}`
- POST `/api/memory` `{content}` → `MemoryItem`
- DELETE `/api/memory/{id}` → 204 · DELETE `/api/memory` → 204 (forget everything)
- PUT `/api/memory/settings` `{enabled}` → `{enabled}` (stored in `User.memory_enabled`)

The memory plugin injects the user's most relevant memories into the system prompt and, after each answer, extracts at most 2 new durable facts about the user (preferences, background, goals) — never secrets or credentials.

## Paper Lens
```ts
interface PaperInfo {
  docId: string; title: string; authors: string[]; year?: number | null; venue?: string | null;
  abstract: string; arxivId?: string | null; doi?: string | null; url?: string | null; pdfUrl?: string | null;
  citationCount?: number | null; referenceCount?: number | null;
  status: "queued" | "processing" | "ready" | "error"; createdAt: ISODate;
}
interface PaperSummary {
  tldr: string; problem: string; method: string; keyContributions: string[]; results: string; limitations: string;
  keyTerms: { term: string; definition: string }[];
  sections: { title: string; summary: string; page?: number | null }[];
  generatedAt: ISODate; model: string;
}
```
- POST `/api/papers/import` `{query}` — arXiv id/URL, DOI, Semantic Scholar URL, or a title → `PaperInfo`. The open-access PDF is downloaded and ingested like an upload (the Document gets `meta.paper`); without a PDF the abstract is ingested. 404 `"Paper not found"`.
- GET `/api/papers` → `PaperInfo[]` newest first
- GET `/api/papers/{docId}` → `{paper: PaperInfo, summary: PaperSummary | null}`
- POST `/api/papers/{docId}/summary` → `PaperSummary` (LLM over the paper's chunks; cached in Document.meta)
- GET `/api/papers/{docId}/citations` → `Graph` of the paper + its references + citing papers (Semantic Scholar; cached)

## Knowledge graph
```ts
interface GraphNode {
  id: string; label: string;
  kind: "paper" | "reference" | "citation" | "concept" | "method" | "dataset" | "metric" | "person" | "organization" | "document" | "other";
  weight: number; url?: string | null; year?: number | null; docId?: string | null; description?: string | null;
}
interface GraphEdge { source: string; target: string; label?: string | null; weight: number }
interface Graph { nodes: GraphNode[]; edges: GraphEdge[] }
```
POST `/api/graph` `{docIds: string[]}` → `Graph` — entities + relations extracted by the LLM from each document's most representative chunks (cached per document in Document.meta), merged across documents, plus one `document` node per doc.

## Workspaces (Claude Code-style reader)
`WorkspaceInfo { id: string; name: string; fileCount: number; totalBytes: number; languages: Record<string, number>; createdAt: ISODate }`
- POST `/api/workspaces` multipart: `archive` (.zip) OR repeated `files` + repeated `paths` (relative paths from a folder picker), optional `name` → `WorkspaceInfo`. Limits 2,000 files / 50 MB; skips `.git`, `node_modules`, venvs, build output and binaries; zip-slip and path-traversal safe.
- GET `/api/workspaces` → `WorkspaceInfo[]`
- GET `/api/workspaces/{id}/tree` → `{files: {path: string, size: number}[]}`
- GET `/api/workspaces/{id}/file?path=` → `{path, content, truncated: boolean, lines: number}` (text files, ≤ 200 KB)
- DELETE `/api/workspaces/{id}` → 204

## Finance
```ts
interface FinanceReport {
  docId: string; filename: string; kind: "bank_statement" | "balance_sheet" | "table";
  currency: string | null; period: { start: string; end: string } | null;
  totals: { inflow: number; outflow: number; net: number } | null;
  byMonth: { month: string; inflow: number; outflow: number; net: number }[];
  byCategory: { category: string; amount: number; count: number }[];
  topTransactions: { date: string; description: string; amount: number; category: string }[];
  balanceSheet: { totalAssets: number | null; totalLiabilities: number | null; equity: number | null;
                  currentRatio: number | null; quickRatio: number | null; debtToEquity: number | null } | null;
  insights: string[]; warnings: string[];
}
```
POST `/api/finance/analyze` `{docId}` → `FinanceReport` (deterministic pandas analytics over a ready CSV/XLSX document + short LLM insights when a model is available). In chat, mode `"finance"` with tabular attachments adds the same analytics as context.

## Model Arena
- POST `/api/arena/battles` `{prompt, modelA?, modelB?}` → `{id, prompt}` (two distinct available models picked at random when omitted; identities hidden until the vote)
- POST `/api/arena/battles/{id}/stream` `{side: "a" | "b"}` → SSE: `delta {text}` … then `done {text}` or `error {message}`
- POST `/api/arena/battles/{id}/vote` `{winner: "a" | "b" | "tie" | "both_bad"}` → `{modelA: {id, label}, modelB: {id, label}}`
- GET `/api/arena/leaderboard` → `{models: {id, label, rating, wins, losses, ties, battles}[], totalVotes}` (Elo, K=32, start 1000, replayed over all votes)

## ML Lab (`/api/ml`)
```ts
interface RouterReport {
  available: boolean; trainedAt?: ISODate; model?: string;              // "Logistic regression on bge-small embeddings"
  labels?: string[];                                                    // ["chat","web","documents","research","finance","code"]
  datasetSize?: { train: number; test: number };
  accuracy?: number; macroF1?: number;
  perClass?: { label: string; precision: number; recall: number; f1: number; support: number }[];
  confusion?: number[][];                                               // rows = true label, cols = predicted, same order as labels
  baseline?: { name: string; accuracy: number; macroF1: number };       // keyword-rules baseline
}
interface RagEvalConfig { name: string; recallAt1: number; recallAt3: number; recallAt5: number; recallAt10: number; mrr: number; ndcg10: number; latencyMsP50: number; latencyMsP95: number }
interface RagEvalReport { available: boolean; runAt?: ISODate; dataset?: { name: string; documents: number; chunks: number; questions: number }; k?: number; configs?: RagEvalConfig[]; notes?: string[] }
interface VerificationStats { answers: number; avgScore: number | null; labelCounts: Record<string, number>; histogram: { bucket: string; count: number }[] }
```
- GET `/api/ml/router` → `RouterReport`
- POST `/api/ml/router/predict` `{text}` → `{label, confidence, probabilities: Record<string, number>}`
- POST `/api/ml/router/train` → `RouterReport` (admin)
- GET `/api/ml/rag-eval` → `RagEvalReport` (latest saved run)
- POST `/api/ml/rag-eval/run` → `RagEvalReport` (admin; configs "BM25", "Dense (bge-small)", "Hybrid (RRF)", "Hybrid + cross-encoder rerank")
- GET `/api/ml/verification` → `VerificationStats` over the current user's answers

## Frontend navigation contract
New-chat hand-off from any page: `navigate("/", { state: NewChatState })`
```ts
interface NewChatState { fresh: true; attachDoc?: DocumentInfo; attachDocs?: DocumentInfo[]; prompt?: string; mode?: ChatMode; workspace?: { id: string; name: string } }
```
`prompt` pre-fills the composer (NOT auto-sent). App routes: `/papers`, `/papers/:docId`, `/workspace`, `/arena`, `/insights` (ML Lab), `/memory`, `/graph`, `/finance`.
