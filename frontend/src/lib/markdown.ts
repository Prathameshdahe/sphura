import type { Parent, PhrasingContent, Root, RootContent, Text } from "mdast";

/* ── Pre-processing: LaTeX delimiters + currency, never inside code ── */

const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})/;

function transformProse(segment: string, fn: (s: string) => string): string {
  const codes: string[] = [];
  const masked = segment.replace(/(`+)[^`\n]*?\1/g, (m) => {
    codes.push(m);
    return `${codes.length - 1}`;
  });
  return fn(masked).replace(/(\d+)/g, (_m, i: string) => codes[Number(i)] ?? "");
}

/** Apply `fn` to every part of the markdown that is not a fenced block or inline code span. */
export function mapOutsideCode(md: string, fn: (s: string) => string): string {
  const out: string[] = [];
  let prose: string[] = [];
  let fence: string | null = null;
  const flush = () => {
    if (prose.length) out.push(transformProse(prose.join("\n"), fn));
    prose = [];
  };
  for (const line of md.split("\n")) {
    if (fence) {
      out.push(line);
      const close = /^ {0,3}(`{3,}|~{3,})\s*$/.exec(line);
      if (close && close[1][0] === fence[0] && close[1].length >= fence.length) fence = null;
      continue;
    }
    const open = FENCE_OPEN.exec(line);
    if (open) {
      flush();
      fence = open[1];
      out.push(line);
      continue;
    }
    prose.push(line);
  }
  flush();
  return out.join("\n");
}

/**
 * Normalise model output for remark-math: \[..\] → $$..$$, \(..\) → $..$,
 * and escape currency like "$5" so prices aren't parsed as inline math.
 */
export function prepareMarkdown(md: string): string {
  return mapOutsideCode(md, (s) =>
    s
      .replace(/\\\[([\s\S]+?)\\\]/g, (_m, body: string) => `\n$$\n${body.trim()}\n$$\n`)
      .replace(/\\\(([\s\S]+?)\\\)/g, (_m, body: string) => `$${body.trim()}$`)
      .replace(/(^|[^\\$\w])\$(?=\d)/g, (_m, pre: string) => `${pre}\\$`),
  );
}

/* ── remark plugin: [1], [1][2], [1, 2] → <cite data-n> chips ── */

const CITE_RE = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g;
const SKIP = new Set(["code", "inlineCode", "math", "inlineMath", "link", "definition", "html", "image"]);

function citeNode(n: number): PhrasingContent {
  return {
    type: "citation",
    data: {
      hName: "cite",
      hProperties: { dataN: String(n) },
      hChildren: [{ type: "text", value: String(n) }],
    },
  } as unknown as PhrasingContent;
}

function splitText(node: Text): PhrasingContent[] | null {
  const value = node.value;
  CITE_RE.lastIndex = 0;
  if (!CITE_RE.test(value)) return null;
  CITE_RE.lastIndex = 0;
  const out: PhrasingContent[] = [];
  let last = 0;
  for (let m = CITE_RE.exec(value); m; m = CITE_RE.exec(value)) {
    if (m.index > last) out.push({ type: "text", value: value.slice(last, m.index) });
    for (const n of m[1].split(",")) out.push(citeNode(Number(n.trim())));
    last = m.index + m[0].length;
  }
  if (last < value.length) out.push({ type: "text", value: value.slice(last) });
  return out;
}

function walk(node: Parent): void {
  let changed = false;
  const next: RootContent[] = [];
  for (const child of node.children) {
    if (child.type === "text") {
      const parts = splitText(child);
      if (parts) {
        next.push(...parts);
        changed = true;
        continue;
      }
    } else if (
      child.type === "linkReference" &&
      child.referenceType !== "full" &&
      /^\d{1,3}$/.test(child.identifier)
    ) {
      next.push(citeNode(Number(child.identifier)));
      changed = true;
      continue;
    } else if ("children" in child && !SKIP.has(child.type)) {
      walk(child as Parent);
    }
    next.push(child);
  }
  if (changed) node.children = next as Parent["children"];
}

export function remarkCitations() {
  return (tree: Root) => {
    walk(tree);
  };
}
