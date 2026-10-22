# Deploying Sphura

Sphura is two apps that deploy independently:

| App | Folder | What it is | Recommended host |
|---|---|---|---|
| Frontend | `frontend/` | Static React SPA (Vite build → `dist/`) | Vercel |
| Backend | `backend/` | FastAPI + LangGraph API in Docker (~1 GB RAM at runtime) | Render (≥ 2 GB) or Hugging Face Spaces (free, 16 GB) |

Plus two managed services that keep data across redeploys:

| Service | Used for | Free option |
|---|---|---|
| Supabase Postgres | users, conversations, documents metadata, memory | Free project (choose the region nearest your users, e.g. Mumbai) |
| Qdrant Cloud | document embeddings | Free 1 GB cluster |

> Deploy the **backend first** — the frontend needs its URL.

---

## 1. Database (Supabase)

1. Create a project at <https://supabase.com> (region close to your backend host).
2. *Connect* → **Session pooler** URI → this is `DATABASE_URL` (`postgresql://…` works as-is).
3. Optional Google sign-in: *Authentication → Sign In / Providers → Google* (client ID + secret from Google Cloud),
   then *URL Configuration*: Site URL = your Vercel URL, redirect URL = `https://<your-site>/auth/callback`.
   Set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` on the backend.

Tables are created automatically when the API starts.

## 2. Vector store (Qdrant Cloud, recommended)

Create a free cluster at <https://cloud.qdrant.io>, then set `QDRANT_URL` and `QDRANT_API_KEY` on the backend.
Without it the API uses an embedded Qdrant on local disk, which most hosts wipe on every redeploy.

## 3. Backend

### Option A — Render (Docker)

1. Render → **New → Blueprint** → select this repository. Render reads [`render.yaml`](../render.yaml)
   (service `sphura-api`, `rootDir: backend`, health check `/api/health`).
2. Fill in the secrets the dashboard asks for (`DATABASE_URL`, `GROQ_API_KEY`, `NVIDIA_API_KEY`, `CORS_ORIGINS`, …).
   `JWT_SECRET` is generated for you.
3. Keep the **standard** plan or larger: the embedding model, reranker, NLI verifier and ONNX classifiers stay in
   memory (~1 GB). The free 512 MB instance is killed at start-up.
4. Note the URL, e.g. `https://sphura-api.onrender.com`, and check `https://sphura-api.onrender.com/api/health`.

### Option B — Hugging Face Spaces (free, Docker)

1. Create a Space → SDK **Docker** → hardware *CPU basic* (2 vCPU, 16 GB RAM).
2. Push the contents of `backend/` to the Space repository (the `Dockerfile` must be at its root).
3. In the Space README front matter set `app_port: 7860`; under *Settings → Variables and secrets* add `PORT=7860`
   and the same variables as above (`ENVIRONMENT=production`, a 32+ character `JWT_SECRET`, `DATABASE_URL`, keys, …).
4. The API is served at `https://<user>-<space>.hf.space`.

### Option C — any Docker host

```bash
docker build -t sphura-api ./backend
docker run -p 8000:8000 --env-file .env -e ENVIRONMENT=production sphura-api
```

The image honours `$PORT`, runs as a non-root user and trusts `X-Forwarded-*` headers from the host's proxy.

### Backend variables for production

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` (refuses weak `JWT_SECRET`) |
| `JWT_SECRET` | 32+ random characters (keeps sessions valid across restarts) |
| `DATABASE_URL` | Supabase session pooler URI |
| `QDRANT_URL`, `QDRANT_API_KEY` | Qdrant Cloud cluster |
| `GROQ_API_KEY`, `NVIDIA_API_KEY` | model providers (the local Ollama member is simply unavailable in the cloud) |
| `DEFAULT_MODEL` | `ensemble:sphura` |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` with the Vercel rewrite (below); `none` for a direct cross-origin API |
| `CORS_ORIGINS` | your frontend origin(s), e.g. `https://sphura.vercel.app` |
| `TAVILY_API_KEY` | optional, finance news |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `ADMIN_EMAILS` | optional, Google sign-in and admins |

## 4. Frontend (Vercel)

1. Vercel → **Add New → Project** → import this repository.
2. **Root Directory: `frontend`**. Vercel reads [`frontend/vercel.json`](../frontend/vercel.json)
   (`npm run build`, output `dist`, SPA fallback, long-cache `/assets`).
3. Connect it to the backend — pick one:

   **a) Rewrite (recommended).** In `frontend/vercel.json` replace
   `https://REPLACE-WITH-YOUR-BACKEND.onrender.com` with your backend URL and leave `VITE_API_URL` unset. The browser
   only talks to your Vercel domain, so the session cookie is first-party (`COOKIE_SAMESITE=lax`) and no CORS is
   involved. Chat streaming (SSE) passes through the rewrite.

   **b) Direct.** Set the environment variable `VITE_API_URL=https://<your-backend>` in Vercel, and on the backend
   `CORS_ORIGINS=https://<your-vercel-site>`, `COOKIE_SAMESITE=none`, `COOKIE_SECURE=true`. Some browsers block
   third-party cookies, so (a) is more reliable.
4. Deploy, open the site, create an account (or sign in with Google).

## 5. Checklist

- [ ] `https://<backend>/api/health` returns `{"ok": true, …}` with your providers `true`
- [ ] `/api/models` (signed in) lists *Sphura Ensemble* and the Groq / NVIDIA models as available
- [ ] Sign-up and sign-in keep you logged in after a page refresh (cookie mode correct)
- [ ] A chat answer streams token by token (SSE not buffered)
- [ ] Uploading `samples/bank_statement_demo.csv` shows the dashboard and charts
- [ ] Supabase redirect URLs include the production `/auth/callback` (Google sign-in only)
