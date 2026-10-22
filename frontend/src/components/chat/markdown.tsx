import { createContext, lazy, memo, Suspense, useContext, useMemo, useRef, useState, type ComponentProps } from "react";
import ReactMarkdown, { type Components, type ExtraProps, type Options } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Check, Code, Copy, Eye, Image as ImageIcon, PanelRight } from "lucide-react";
import { ArtifactFrame } from "@/components/artifacts/artifact-frame";
import { artifactId, artifactKind, artifactTitle, normalizeCode, type ArtifactKind } from "@/components/artifacts/artifact-utils";
import { CitationChip } from "@/components/chat/sources";
import { Glyph, type GlyphName } from "@/components/icons/glyphs";
import { useCopy } from "@/hooks/use-copy";
import { useIsDesktop } from "@/hooks/use-media-query";
import { parseChartSpec } from "@/lib/chart-spec";
import { remarkEmojiGlyphs } from "@/lib/emoji";
import { prepareMarkdown, remarkCitations } from "@/lib/markdown";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useArtifactPanel } from "@/stores/artifacts";

interface MarkdownCtx {
  sources: Source[];
  /** Assistant message id (artifact ids); absent for text that isn't a saved answer. */
  messageId?: string;
  streaming: boolean;
  artifactActions: boolean;
}

const MarkdownContext = createContext<MarkdownCtx>({ sources: [], streaming: false, artifactActions: false });

const remarkPlugins: Options["remarkPlugins"] = [remarkGfm, [remarkMath, { singleDollarTextMath: true }], remarkCitations, remarkEmojiGlyphs];
const rehypePlugins: Options["rehypePlugins"] = [
  [rehypeKatex, { throwOnError: false, strict: "ignore", output: "htmlAndMathml" }],
  [rehypeHighlight, { detect: false }],
];

function withoutNode<T extends ExtraProps>(props: T): Omit<T, "node"> {
  const { node, ...rest } = props;
  void node;
  return rest;
}

function languageOf(node: ExtraProps["node"]): string {
  const code = node?.children.find((c) => c.type === "element" && c.tagName === "code");
  if (!code || code.type !== "element") return "";
  const cls = code.properties?.className;
  const list: string[] = Array.isArray(cls) ? cls.map(String) : String(cls ?? "").split(" ");
  const lang = list.find((c: string) => c.startsWith("language-"));
  return lang ? lang.slice("language-".length) : "";
}

type HastElement = NonNullable<ExtraProps["node"]>;
type HastChild = HastElement["children"][number];

/** Raw text of a hast subtree (rehype-highlight wraps tokens in spans). */
function hastText(node: HastElement | HastChild): string {
  if (node.type === "text") return node.value;
  if ("children" in node) return node.children.map((c) => hastText(c as HastChild)).join("");
  return "";
}

const headerButton =
  "inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground focus-visible:outline-2";

function CodeBlock(props: ComponentProps<"pre"> & ExtraProps) {
  const { node, children, className } = props;
  const ref = useRef<HTMLPreElement>(null);
  const { copied, copy } = useCopy();
  const ctx = useContext(MarkdownContext);
  const isDesktop = useIsDesktop();
  const [preview, setPreview] = useState(false);
  const lang = languageOf(node);
  const code = useMemo(() => (node ? normalizeCode(hastText(node)) : ""), [node]);
  const kind: ArtifactKind | null = ctx.artifactActions && code.trim() ? artifactKind(lang, code) : null;
  // While streaming the block may be half-written: actions appear once the answer is complete.
  const ready = !!kind && !ctx.streaming;
  const title = kind ? artifactTitle(kind, code) : "";

  const openInPanel = () => {
    if (!kind) return;
    const messageId = ctx.messageId ?? "draft";
    useArtifactPanel.getState().show({ id: artifactId(messageId, code), messageId, kind, code, title });
  };

  return (
    <div className="group/code mb-4 overflow-hidden rounded-xl border bg-code font-sans" data-sphura-skip="">
      <div className="flex h-9 items-center gap-1 border-b bg-(--code-header) pr-1.5 pl-3.5">
        <span className="mr-auto truncate font-mono text-[11px] tracking-wide text-muted-foreground lowercase">{lang || "text"}</span>
        {ready && (
          <>
            <div role="group" aria-label="Code view" className="flex items-center rounded-md bg-foreground/5 p-0.5">
              <button
                type="button"
                aria-pressed={!preview}
                onClick={() => setPreview(false)}
                className={cn(headerButton, "h-6", !preview && "bg-background text-foreground shadow-xs")}
              >
                <Code className="size-3.5" />
                <span className="hidden min-[400px]:inline">Code</span>
              </button>
              <button
                type="button"
                aria-pressed={preview}
                onClick={() => setPreview(true)}
                className={cn(headerButton, "h-6", preview && "bg-background text-foreground shadow-xs")}
              >
                <Eye className="size-3.5" />
                <span className="hidden min-[400px]:inline">Preview</span>
              </button>
            </div>
            <button type="button" onClick={openInPanel} aria-label="Open in panel" title="Open in panel" className={headerButton}>
              <PanelRight className="size-3.5" />
              <span className="hidden sm:inline">{isDesktop ? "Open in panel" : "Open"}</span>
            </button>
          </>
        )}
        <button
          type="button"
          onClick={() => void copy(code || ref.current?.textContent || "")}
          aria-label={copied ? "Copied" : "Copy code"}
          className={headerButton}
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          <span className={cn(ready && "hidden sm:inline")}>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      {ready && preview && kind ? (
        <div className="h-80 min-h-40 resize-y overflow-hidden bg-white sm:h-96">
          <ArtifactFrame artifact={{ kind, code, title }} />
        </div>
      ) : (
        <pre ref={ref} className={cn("scrollbar-thin", className)}>
          {children}
        </pre>
      )}
    </div>
  );
}

/** Tone per glyph so a model's "✅ / ⚠️ / 📈" reads as a small, coloured Sphura icon. */
const GLYPH_TONE: Partial<Record<GlyphName, string>> = {
  check: "text-success",
  cross: "text-destructive",
  warning: "text-warning",
  "trend-down": "text-destructive",
  "trend-up": "text-success",
};

/** `<i data-glyph>` from remarkEmojiGlyphs → an inline glyph; any other <i> renders as usual. */
function InlineGlyph(props: ComponentProps<"i"> & ExtraProps) {
  const name = props.node?.properties?.dataGlyph;
  if (typeof name !== "string") return <i {...withoutNode(props)} />;
  const glyphName = name as GlyphName;
  return (
    <Glyph
      name={glyphName}
      className={cn("mx-[0.08em] inline-block size-[1.05em] -translate-y-[0.08em] align-middle", GLYPH_TONE[glyphName] ?? "text-accent-ink")}
      strokeWidth={2.1}
    />
  );
}

const ChartBlock = lazy(() => import("@/components/chat/chart-block"));

function ChartSkeleton({ label }: { label: string }) {
  return (
    <div className="my-4 grid h-64 place-items-center rounded-2xl border bg-card font-sans text-sm text-muted-foreground sm:h-72" role="status">
      <span className="shimmer-text">{label}</span>
    </div>
  );
}

/** ```chart fences → a themed chart; while streaming a placeholder; invalid or too large → the ordinary code block. */
function PreBlock(props: ComponentProps<"pre"> & ExtraProps) {
  const { node } = props;
  const ctx = useContext(MarkdownContext);
  const lang = languageOf(node);
  const code = useMemo(() => (lang === "chart" && node ? hastText(node) : ""), [lang, node]);
  const spec = useMemo(() => (code ? parseChartSpec(code) : null), [code]);
  if (lang !== "chart") return <CodeBlock {...props} />;
  if (spec) {
    return (
      <Suspense fallback={<ChartSkeleton label="Drawing chart…" />}>
        <ChartBlock spec={spec} />
      </Suspense>
    );
  }
  if (ctx.streaming) return <ChartSkeleton label="Drawing chart…" />;
  return <CodeBlock {...props} />;
}

function Cite({ node }: ComponentProps<"cite"> & ExtraProps) {
  const { sources } = useContext(MarkdownContext);
  const n = Number(node?.properties?.dataN);
  const source = sources.find((s) => s.index === n);
  if (!source) {
    return (
      <span data-sphura-cite="" className="text-[0.8em] text-muted-foreground">
        [{n}]
      </span>
    );
  }
  return <CitationChip source={source} />;
}

const components: Components = {
  pre: PreBlock,
  cite: Cite,
  i: InlineGlyph,
  a: (props) => {
    const rest = withoutNode(props);
    return <a {...rest} target="_blank" rel="noopener noreferrer" />;
  },
  table: (props) => (
    <div className="sphura-table scrollbar-thin">
      <table {...withoutNode(props)} />
    </div>
  ),
  // Never auto-load model-chosen image URLs: a prompt-injected page could exfiltrate the chat through
  // the query string. Show a link the reader can choose to open instead.
  img: ({ src, alt }) => {
    const href = typeof src === "string" ? src : "";
    const label = alt?.trim() || "Image";
    return href ? (
      <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1">
        <ImageIcon className="inline size-[0.95em] shrink-0" aria-hidden />
        {label}
      </a>
    ) : (
      <span>{label}</span>
    );
  },
};

interface MarkdownProps {
  text: string;
  sources?: Source[];
  streaming?: boolean;
  className?: string;
  /** Assistant message id: keys the artifacts of html / svg / mermaid blocks. */
  messageId?: string;
  /** Preview + open-in-panel actions on html / svg / mermaid code blocks (default true). */
  artifactActions?: boolean;
}

const NO_SOURCES: Source[] = [];

/** Assistant answer renderer: GFM, math, highlighted code with copy + artifact previews, and [n] citation chips. */
export const Markdown = memo(function Markdown({
  text,
  sources = NO_SOURCES,
  streaming = false,
  className,
  messageId,
  artifactActions = true,
}: MarkdownProps) {
  const prepared = useMemo(() => prepareMarkdown(text), [text]);
  const ctx = useMemo<MarkdownCtx>(
    () => ({ sources, messageId, streaming, artifactActions }),
    [sources, messageId, streaming, artifactActions],
  );
  return (
    <MarkdownContext.Provider value={ctx}>
      <div className={cn("sphura-prose", streaming && "is-streaming", className)}>
        <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>
          {prepared}
        </ReactMarkdown>
      </div>
    </MarkdownContext.Provider>
  );
});
