# Sphura — web app

Vite + React 19 + TypeScript + Tailwind v4 + shadcn. The API contract lives in `../docs/CONTRACT.md` (mirrored in `src/lib/types.ts`); brand components follow `COMPONENTS.md`.

```bash
npm run dev      # http://localhost:5173 — proxies /api → http://localhost:8000
npm run build    # tsc -b + vite build → dist/
npm run lint     # oxlint
```

Docker (`docker compose up --build` from the repo root): `Dockerfile` builds the SPA and serves it with nginx; `nginx.conf` falls back to `index.html` for client routes and proxies `/api` → `backend:8000` with buffering off so chat streams token by token.

## Deploying on its own (Vercel)

Set the project's **Root Directory** to `frontend`; `vercel.json` provides the build, SPA fallback and an `/api/*` rewrite to the backend (replace `REPLACE-WITH-YOUR-BACKEND.onrender.com`). Alternatively set `VITE_API_URL` (see `.env.example`) to call the backend on its own domain — the backend then needs `CORS_ORIGINS` and `COOKIE_SAMESITE=none`. Every request is built by `apiUrl()` in `src/lib/api.ts`. Full guide: [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md).

## Map

| Path | What |
|---|---|
| `src/main.tsx` | fonts, KaTeX css, providers (React Query, next-themes, tooltips, toasts, router) |
| `src/App.tsx` | routes: `/login`, `/signup`, `/`, `/c/:id`, `/documents`, `/dashboard`, `/markets`, `/lab` (Model Lab), `/memory`; `/focus` is a dev-only orb page; `/finance` → `/dashboard` and `/insights` → `/lab` redirect |
| `src/lib/api.ts` | fetch wrapper (`credentials: "include"`, `ApiError(status, detail)`, 401 → /login) |
| `src/lib/sse.ts` | `/api/chat` SSE parser (CRLF, multi-line data, `: ping`) → typed `ChatEvent`s |
| `src/lib/chat-runner.ts` | runs one stream outside React; live state → `stores/chat-store.ts`, saved messages → query cache |
| `src/lib/queries.ts` | React Query hooks + optimistic rename/pin/delete |
| `src/lib/markdown.ts` | `[1]` / `[1, 2]` citation remark plugin, LaTeX/currency normalisation |
| `src/pages/ChatPage.tsx` | home (`/`) and conversation (`/c/:id`) — one component so a stream survives the start navigation |
| `src/components/chat/*` | thread, messages, markdown, sources, steps timeline, composer wrapper |
| `src/components/layout/*` | app shell, sidebar (sheet on mobile), user menu, top bar, `Page` + `PageHeader` (the one studio page frame) |
| `src/lib/feature-types.ts`, `src/lib/feature-api/*` | FINANCE_PLAN §8 mirror: markets, voice, agent graph, Model Lab report, finance analytics, memory |
| `src/components/features/*` | dashboard (KPIs, monthly bars, donut, ratios), markets (search, quote + sparkline, news with sentiment, watchlist), Model Lab sections, memory |
| `src/components/voice/*` | hands-free voice mode: server STT/TTS first (`/api/voice/*`), Web Speech / speechSynthesis fallbacks |

Shortcuts: `Ctrl/⌘ K` search chats · `Ctrl/⌘ Shift O` new chat · `Esc` stop generating.
