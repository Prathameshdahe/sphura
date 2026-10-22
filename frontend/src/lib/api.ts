import type {
  ConversationDetail,
  ConversationSummary,
  DocumentInfo,
  Health,
  ModelInfo,
  User,
} from "./types";

/** Every non-2xx response becomes an ApiError whose message is the server's `detail` string. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Backend origin for split deploys (frontend on Vercel, API on Render): `VITE_API_URL=https://api.example.com`.
 * Empty (the default) means same-origin `/api` — the Vite dev proxy, nginx in Docker, or a Vercel rewrite.
 * Every request already sends `credentials: "include"`, so the session cookie also works cross-origin.
 */
export const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

/** Absolute URL of an API path ("/documents/1/file" → `${API_BASE}/api/documents/1/file`). */
export const apiUrl = (path: string): string => `${API_BASE}/api${path.startsWith("/") ? path : `/${path}`}`;

export const NETWORK_MESSAGE = "Can't reach the Sphura server. Check your connection or that the backend is running.";

const AUTH_PAGES = ["/login", "/signup", "/auth/callback"];
/** Public pages a visitor can sit on without a session: a 401 there must never bounce them to /login. */
const PUBLIC_PAGES = [...AUTH_PAGES, "/welcome"];
let unauthorizedHandler: (() => void) | null = null;

/** App registers a router-aware handler; falls back to a hard redirect. */
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  unauthorizedHandler = fn;
}

export function handleUnauthorized(): void {
  if (PUBLIC_PAGES.includes(window.location.pathname)) return;
  if (unauthorizedHandler) unauthorizedHandler();
  else window.location.assign("/login");
}

/** Where to land after signing in: the in-app page that sent you to /login (router state), else home. */
export function returnPath(state: unknown): string {
  const from = (state as { from?: unknown } | null)?.from;
  if (typeof from !== "string" || !from.startsWith("/") || from.startsWith("//")) return "/";
  return AUTH_PAGES.some((p) => from.startsWith(p)) ? "/" : from;
}

export function isAbortError(e: unknown): boolean {
  return e instanceof DOMException ? e.name === "AbortError" : (e as { name?: string } | null)?.name === "AbortError";
}

export function errorMessage(e: unknown, fallback = "Something went wrong"): string {
  if (e instanceof ApiError) return e.detail;
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}

export async function readError(res: Response): Promise<ApiError> {
  let detail = "";
  try {
    const type = res.headers.get("content-type") ?? "";
    if (type.includes("json")) {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail != null) detail = JSON.stringify(body.detail);
    } else {
      const text = (await res.text()).trim();
      if (text && text.length < 240 && !text.startsWith("<")) detail = text;
    }
  } catch {
    /* body unreadable — fall through to a generic message */
  }
  if (!detail) {
    detail = res.status >= 500 ? NETWORK_MESSAGE : res.statusText || `Request failed (${res.status})`;
  }
  return new ApiError(res.status, detail);
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  /** Don't trigger the global 401 → /login redirect (auth endpoints). */
  skipAuthRedirect?: boolean;
  /** Accept header (defaults to JSON). */
  accept?: string;
}

/** The one place the app talks to `/api`: cookie auth, JSON/multipart bodies, 401 → /login, `{detail}` errors. */
async function send(path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: opts.accept ?? "application/json" };
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      method: opts.method ?? "GET",
      headers,
      body,
      credentials: "include",
      signal: opts.signal,
    });
  } catch (e) {
    if (isAbortError(e) || opts.signal?.aborted) throw e;
    throw new ApiError(0, NETWORK_MESSAGE);
  }

  if (res.status === 401 && !opts.skipAuthRedirect) handleUnauthorized();
  if (!res.ok) throw await readError(res);
  return res;
}

/** POST a JSON body to a Server-Sent Events endpoint and return the open response stream. */
export async function requestStream(path: string, body: unknown, signal: AbortSignal): Promise<ReadableStream<Uint8Array>> {
  const res = await send(path, { method: "POST", body, signal, accept: "text/event-stream" });
  if (!res.body) throw new ApiError(0, "This browser can't stream responses.");
  return res.body;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await send(path, opts);
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") ?? "";
  if (!type.includes("json")) return undefined as T;
  return (await res.json()) as T;
}

/** Binary responses (audio/wav from /voice/speak). Errors still arrive as `{detail}` JSON → ApiError. */
export async function requestBlob(path: string, opts: RequestOptions = {}): Promise<Blob> {
  const res = await send(path, { accept: "*/*", ...opts });
  return res.blob();
}

const qs = (params: Record<string, string | null | undefined>): string => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
};

/** `GET /api/auth/providers`: which third-party sign-ins the server offers (the Supabase anon key is public). */
export interface AuthProviders {
  google: { enabled: boolean; supabaseUrl: string | null; anonKey: string | null };
}

export const api = {
  me: () => request<User>("/auth/me", { skipAuthRedirect: true }),
  login: (body: { email: string; password: string }) =>
    request<User>("/auth/login", { method: "POST", body, skipAuthRedirect: true }),
  register: (body: { email: string; password: string; name: string }) =>
    request<User>("/auth/register", { method: "POST", body, skipAuthRedirect: true }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST", skipAuthRedirect: true }),
  authProviders: () => request<AuthProviders>("/auth/providers", { skipAuthRedirect: true }),
  /** Trade a Supabase access token (Google sign-in) for Sphura's own session cookie; answers like `login`. */
  oauthSupabase: (accessToken: string) =>
    request<User>("/auth/oauth/supabase", { method: "POST", body: { accessToken }, skipAuthRedirect: true }),

  health: () => request<Health>("/health"),
  models: () => request<ModelInfo[]>("/models"),

  conversations: (q?: string) => request<ConversationSummary[]>(`/conversations${qs({ q: q?.trim() })}`),
  conversation: (id: string) => request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`),
  updateConversation: (id: string, patch: { title?: string; pinned?: boolean }) =>
    request<ConversationSummary>(`/conversations/${encodeURIComponent(id)}`, { method: "PATCH", body: patch }),
  deleteConversation: (id: string) =>
    request<void>(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),

  documents: (conversationId?: string | null) =>
    request<DocumentInfo[]>(`/documents${qs({ conversationId })}`),
  document: (id: string) => request<DocumentInfo>(`/documents/${encodeURIComponent(id)}`),
  uploadDocument: (file: File, conversationId?: string | null) => {
    const form = new FormData();
    form.append("file", file, file.name);
    if (conversationId) form.append("conversationId", conversationId);
    return request<DocumentInfo>("/documents", { method: "POST", form });
  },
  deleteDocument: (id: string) => request<void>(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
