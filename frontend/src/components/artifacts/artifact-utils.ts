/**
 * Artifacts = renderable code blocks in assistant answers (```html / ```svg / ```mermaid).
 * Everything here is pure: extraction from markdown, titles, ids, and the sandboxed srcdoc documents.
 * Previews always run in <iframe sandbox="allow-scripts"> (opaque origin, never allow-same-origin).
 */

export type ArtifactKind = "html" | "svg" | "mermaid";

export interface Artifact {
  id: string;
  messageId: string;
  kind: ArtifactKind;
  code: string;
  title: string;
}

/** Pinned so a new Mermaid release can never change what a demo renders. */
export const MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js";

const LANGS: Record<string, ArtifactKind> = { html: "html", htm: "html", xhtml: "html", svg: "svg", mermaid: "mermaid", mmd: "mermaid" };

/** Artifact kind for a fenced code block, or null when it isn't previewable. */
export function artifactKind(lang: string, code: string): ArtifactKind | null {
  const l = lang.trim().toLowerCase();
  if (LANGS[l]) return LANGS[l];
  if (l === "xml" && /^\s*(<\?xml[^>]*>\s*)?<svg[\s>]/i.test(code)) return "svg";
  return null;
}

export const normalizeCode = (code: string) => code.replace(/\r\n?/g, "\n").replace(/\s+$/, "");

/** FNV-1a 32-bit, base36: stable short ids for code blocks. */
function hash(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(36);
}

export const artifactId = (messageId: string, code: string) => `${messageId}:${hash(normalizeCode(code))}`;

const decode = (s: string) =>
  s
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim();

const MERMAID_TYPES: [RegExp, string][] = [
  [/^(flowchart|graph)\b/, "Flowchart"],
  [/^sequenceDiagram\b/, "Sequence diagram"],
  [/^classDiagram\b/, "Class diagram"],
  [/^stateDiagram/, "State diagram"],
  [/^erDiagram\b/, "ER diagram"],
  [/^gantt\b/, "Gantt chart"],
  [/^pie\b/, "Pie chart"],
  [/^mindmap\b/, "Mind map"],
  [/^timeline\b/, "Timeline"],
  [/^journey\b/, "User journey"],
  [/^gitGraph\b/, "Git graph"],
  [/^quadrantChart\b/, "Quadrant chart"],
  [/^xychart/, "XY chart"],
  [/^sankey/, "Sankey diagram"],
  [/^block/, "Block diagram"],
  [/^architecture/, "Architecture diagram"],
  [/^requirementDiagram\b/, "Requirement diagram"],
  [/^C4/, "C4 diagram"],
];

export function artifactTitle(kind: ArtifactKind, code: string): string {
  if (kind === "mermaid") {
    const front = /^\s*---\s*\n[\s\S]*?^\s*title:\s*(.+)$[\s\S]*?^\s*---\s*$/m.exec(code);
    const body = code.replace(/^\s*---[\s\S]*?---\s*/, "").replace(/^\s*%%.*$/gm, "").trim();
    const first = body.split("\n")[0]?.trim() ?? "";
    const type = MERMAID_TYPES.find(([re]) => re.test(first))?.[1] ?? "Diagram";
    const inline = /^\s*(?:title|pie\s+title)\s+(.+)$/m.exec(body);
    const title = (front?.[1] ?? inline?.[1] ?? "").trim().replace(/^["']|["']$/g, "");
    return title ? `${title}` : type;
  }
  const title = /<title[^>]*>([\s\S]*?)<\/title>/i.exec(code)?.[1];
  if (title && decode(title)) return decode(title).slice(0, 80);
  if (kind === "html") {
    const h = /<h1[^>]*>([\s\S]*?)<\/h1>/i.exec(code)?.[1] ?? /<h2[^>]*>([\s\S]*?)<\/h2>/i.exec(code)?.[1];
    if (h && decode(h)) return decode(h).slice(0, 80);
    return "HTML page";
  }
  const label = /<svg[^>]*\saria-label=["']([^"']+)["']/i.exec(code)?.[1];
  return label ? decode(label).slice(0, 80) : "SVG graphic";
}

export const KIND_LABEL: Record<ArtifactKind, string> = { html: "HTML", svg: "SVG", mermaid: "Mermaid" };

const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)[^`]*$/;

/** All previewable code blocks of one answer, in order (an unclosed final fence counts once saved). */
export function extractArtifacts(messageId: string, markdown: string, includeUnclosed = true): Artifact[] {
  const out: Artifact[] = [];
  const lines = markdown.split(/\r?\n/);
  let fence: { mark: string; lang: string; body: string[] } | null = null;
  const push = (lang: string, body: string[]) => {
    const code = normalizeCode(body.join("\n"));
    const kind = code.trim() ? artifactKind(lang, code) : null;
    if (!kind) return;
    const id = artifactId(messageId, code);
    if (out.some((a) => a.id === id)) return;
    out.push({ id, messageId, kind, code, title: artifactTitle(kind, code) });
  };
  for (const line of lines) {
    if (fence) {
      const close = /^ {0,3}(`{3,}|~{3,})\s*$/.exec(line);
      if (close && close[1][0] === fence.mark[0] && close[1].length >= fence.mark.length) {
        push(fence.lang, fence.body);
        fence = null;
      } else {
        fence.body.push(line);
      }
      continue;
    }
    const open = FENCE_OPEN.exec(line);
    if (open) fence = { mark: open[1], lang: open[2] ?? "", body: [] };
  }
  if (fence && includeUnclosed) push(fence.lang, fence.body);
  return out;
}

/* ── sandboxed documents ── */

/** JSON for embedding inside an inline <script> (no "</script>", no line separators). */
const scriptJson = (v: unknown) =>
  JSON.stringify(v).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");

export const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

const BASE_FONT = `font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;`;

function htmlDoc(code: string): string {
  if (/<!doctype|<html[\s>]/i.test(code)) return code;
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>html{color-scheme:light}body{margin:16px;${BASE_FONT}line-height:1.5;color:#1f2330;background:#fff}</style></head>
<body>${code}</body></html>`;
}

function svgDoc(code: string): string {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
html,body{height:100%;margin:0;color-scheme:light}
body{display:grid;place-items:center;background:#fff;padding:16px;box-sizing:border-box}
svg{max-width:100%;max-height:calc(100vh - 32px);height:auto}
</style></head><body>${code}</body></html>`;
}

/** Mermaid canvas colours per theme (the iframe can't read the app's CSS variables): warm-paper card / ink. */
export const MERMAID_CANVAS = { light: "#ffffff", dark: "#17171c" } as const;

/** Mermaid "base" theme variables matching the grey + violet palette (lavender nodes, violet accents). */
function mermaidTheme(dark: boolean) {
  return dark
    ? {
        background: MERMAID_CANVAS.dark,
        primaryColor: "#1f1a33",
        primaryTextColor: "#fafafa",
        primaryBorderColor: "#a78bfa",
        secondaryColor: "#221b38",
        secondaryTextColor: "#fafafa",
        tertiaryColor: "#141418",
        tertiaryTextColor: "#fafafa",
        lineColor: "#a1a1aa",
        textColor: "#fafafa",
        fontSize: "14px",
        nodeBorder: "#a78bfa",
        clusterBkg: "#141418",
        clusterBorder: "#27272f",
        edgeLabelBackground: "#17171c",
        mainBkg: "#1f1a33",
      }
    : {
        background: MERMAID_CANVAS.light,
        primaryColor: "#ede9fe",
        primaryTextColor: "#18181b",
        primaryBorderColor: "#7c3aed",
        secondaryColor: "#fafafa",
        secondaryTextColor: "#18181b",
        tertiaryColor: "#f4f4f5",
        tertiaryTextColor: "#18181b",
        lineColor: "#6b6b74",
        textColor: "#18181b",
        fontSize: "14px",
        nodeBorder: "#7c3aed",
        clusterBkg: "#f4f4f5",
        clusterBorder: "#e4e4e7",
        edgeLabelBackground: "#ffffff",
        mainBkg: "#ede9fe",
      };
}

function mermaidDoc(code: string, dark: boolean): string {
  const bg = dark ? MERMAID_CANVAS.dark : MERMAID_CANVAS.light;
  const fg = dark ? "#ece9e2" : "#2a2724";
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
html,body{margin:0;min-height:100%;color-scheme:${dark ? "dark" : "light"}}
body{background:${bg};color:${fg};${BASE_FONT}display:flex;justify-content:center;align-items:flex-start;padding:20px;box-sizing:border-box}
#out{width:100%;display:flex;justify-content:center}
#out svg{max-width:100%;max-height:calc(100vh - 40px);height:auto}
.msg{font-size:13px;opacity:.75;padding:24px;text-align:center}
.err{font-size:13px;color:${dark ? "#ffb3b3" : "#9a3a3c"};white-space:pre-wrap;font-family:ui-monospace,Consolas,monospace;
  border:1px solid currentColor;border-radius:10px;padding:12px 14px;max-width:640px;opacity:.9}
</style></head><body><div id="out"><div class="msg">Rendering diagram…</div></div>
<script src="${MERMAID_URL}"></script>
<script>
(function () {
  var src = ${scriptJson(code)};
  var out = document.getElementById("out");
  function fail(msg) { out.innerHTML = ""; var d = document.createElement("div"); d.className = "err"; d.textContent = msg; out.appendChild(d); }
  if (!window.mermaid) { fail("Couldn't load the Mermaid renderer — check your internet connection."); return; }
  try {
    window.mermaid.initialize({ startOnLoad: false, theme: "base", themeVariables: ${scriptJson(mermaidTheme(dark))}, securityLevel: "strict",
      fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif" });
    window.mermaid.render("sphura-mmd", src).then(function (r) { out.innerHTML = r.svg; })
      .catch(function (e) { fail("Diagram error: " + ((e && e.message) || e)); });
  } catch (e) { fail("Diagram error: " + ((e && e.message) || e)); }
})();
</script></body></html>`;
}

/** The document rendered inside the sandboxed preview iframe. */
export function buildSrcDoc(a: Pick<Artifact, "kind" | "code">, dark: boolean): string {
  if (a.kind === "svg") return svgDoc(a.code);
  if (a.kind === "mermaid") return mermaidDoc(a.code, dark);
  return htmlDoc(a.code);
}

/** A standalone page for "open in new tab": the artifact still runs in a sandboxed, opaque-origin iframe. */
export function standalonePage(a: Artifact, dark: boolean): string {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(a.title)} · Sphura artifact</title>
<style>html,body{margin:0;height:100%;background:${a.kind === "mermaid" ? (dark ? MERMAID_CANVAS.dark : MERMAID_CANVAS.light) : "#fff"}}iframe{display:block;border:0;width:100%;height:100%}</style>
</head><body><iframe sandbox="allow-scripts" title="${escapeHtml(a.title)}" srcdoc="${escapeHtml(buildSrcDoc(a, dark))}"></iframe></body></html>`;
}

const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "artifact";

export function downloadFile(a: Artifact): { name: string; type: string; body: string } {
  if (a.kind === "svg") return { name: `${slug(a.title)}.svg`, type: "image/svg+xml", body: a.code };
  if (a.kind === "mermaid") return { name: `${slug(a.title)}.mmd`, type: "text/plain", body: a.code };
  return { name: `${slug(a.title)}.html`, type: "text/html", body: htmlDoc(a.code) };
}
