/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin for split deploys, e.g. "https://sphura-api.onrender.com" (no trailing slash needed). Empty = same-origin /api. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
