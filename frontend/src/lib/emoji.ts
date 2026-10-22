import type { Parent, PhrasingContent, Root, RootContent, Text } from "mdast";
import type { GlyphName } from "@/components/icons/glyphs";

/* Answers never show raw emoji: common ones become small Sphura glyphs, everything else is dropped. */

const MAP: [string[], GlyphName][] = [
  [["✅", "✔", "☑", "🆗", "👍", "🙌", "💯"], "check"],
  [["❌", "✖", "❎", "🚫", "⛔", "👎"], "cross"],
  [["⚠", "🚨", "❗", "❕", "🔥"], "warning"],
  [["ℹ", "📢", "📣", "🔔"], "info"],
  [["❓", "❔", "🤔"], "question"],
  [["💡", "🧠", "✏", "📝"], "bulb"],
  [["💰", "💵", "💸", "💲", "🪙", "💳", "💴", "💶", "💷", "🤑"], "coin"],
  [["🏦", "🏛"], "bank"],
  [["📈", "🚀", "⬆", "🔼", "🆙"], "trend-up"],
  [["📉", "⬇", "🔽"], "trend-down"],
  [["📊", "🧮"], "chart"],
  [["🎯", "🏁"], "target"],
  [["📅", "📆", "🗓", "⏰", "⏳", "⌛", "🕒", "⏱"], "calendar"],
  [["📄", "📋", "📑", "🧾", "📃", "📁", "📂", "🗂", "📎"], "document"],
  [["🏠", "🏡", "🏘"], "home"],
  [["⭐", "🌟", "✨", "🏆", "🥇"], "star"],
  [["📌", "📍"], "pin"],
  [["👉", "➡", "▶", "🔜"], "arrow"],
  [["🔒", "🔐", "🛡", "🔑"], "shield"],
];

const LOOKUP = new Map<string, GlyphName>();
for (const [list, name] of MAP) for (const e of list) LOOKUP.set(e, name);

/* A pictographic base (or a flag pair), with any variation selector / skin tone / ZWJ sequence after it. */
const EMOJI_RE =
  /(?:\p{Regional_Indicator}{2}|[\p{Extended_Pictographic}](?:️|︎)?(?:\p{Emoji_Modifier})?(?:‍[\p{Extended_Pictographic}](?:️)?(?:\p{Emoji_Modifier})?)*)(?:️|⃣)?/gu;

/** Pictographic characters that are ordinary typography in finance text: keep them. */
const KEEP = new Set(["©", "®", "™", "‼", "⁉", "↔", "↕", "↖", "↗", "↘", "↙", "↩", "↪"]);

function glyphFor(emoji: string): GlyphName | null {
  const base = emoji.replace(/[︎️⃣]/g, "").replace(/\p{Emoji_Modifier}/gu, "");
  return LOOKUP.get(base) ?? LOOKUP.get([...base][0] ?? "") ?? null;
}

function glyphNode(name: GlyphName): PhrasingContent {
  return {
    type: "emojiGlyph",
    data: { hName: "i", hProperties: { dataGlyph: name }, hChildren: [] },
  } as unknown as PhrasingContent;
}

/** Replace / drop emoji in one text node (null when it has none). */
function splitText(node: Text): PhrasingContent[] | null {
  const value = node.value;
  EMOJI_RE.lastIndex = 0;
  if (!EMOJI_RE.test(value)) return null;
  EMOJI_RE.lastIndex = 0;
  const out: PhrasingContent[] = [];
  let last = 0;
  let changed = false;
  for (let m = EMOJI_RE.exec(value); m; m = EMOJI_RE.exec(value)) {
    const hit = m[0];
    if (KEEP.has(hit.replace(/[︎️]/g, ""))) continue;
    changed = true;
    let before = value.slice(last, m.index);
    const name = glyphFor(hit);
    // A dropped emoji shouldn't leave a double space behind.
    if (!name && before.endsWith(" ") && value[m.index + hit.length] === " ") before = before.slice(0, -1);
    if (before) out.push({ type: "text", value: before });
    if (name) out.push(glyphNode(name));
    last = m.index + hit.length;
  }
  if (!changed) return null;
  const rest = value.slice(last);
  if (rest) out.push({ type: "text", value: out.length === 0 ? rest.trimStart() : rest });
  return out;
}

const SKIP = new Set(["code", "inlineCode", "math", "inlineMath", "html"]);

function walk(node: Parent): void {
  let changed = false;
  const next: RootContent[] = [];
  for (const child of node.children) {
    if (child.type === "text") {
      const parts = splitText(child);
      if (parts) {
        next.push(...(parts as RootContent[]));
        changed = true;
        continue;
      }
    } else if ("children" in child && !SKIP.has(child.type)) {
      walk(child as Parent);
    }
    next.push(child);
  }
  if (changed) node.children = next as Parent["children"];
}

/** remark plugin: emoji → `<i data-glyph="…">` (rendered as a Sphura glyph), unknown emoji removed. */
export function remarkEmojiGlyphs() {
  return (tree: Root) => {
    walk(tree);
  };
}

/** Plain-text version (toasts, titles, speech): swap nothing, just remove emoji. */
export function stripEmoji(text: string): string {
  return text.replace(EMOJI_RE, (m) => (KEEP.has(m.replace(/[︎️]/g, "")) ? m : "")).replace(/ {2,}/g, " ");
}
