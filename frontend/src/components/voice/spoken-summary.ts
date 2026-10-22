/**
 * What to say out loud for an answer: the opening of the prose, without tables, code, citations or links.
 * Long answers are cut to their first two paragraphs (about 700 characters); the full text stays on screen.
 */
export function spokenSummary(markdown: string, maxChars = 700): string {
  const cleaned = markdown
    .replace(/```[\s\S]*?(?:```|$)/g, "\n\n")
    .replace(/^\s*\|.*\|\s*$/gm, "") // table rows
    .replace(/\[\^?\d+(?:\s*[,–-]\s*\d+)*\]/g, "") // [1], [1, 2], [^3]
    .replace(/\(\s*sources?\s*\d+(?:\s*,\s*\d+)*\s*\)/gi, "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "") // images
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1"); // links → their text

  const paragraphs = cleaned
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter((p) => p && !/^[-*_]{3,}$/.test(p) && !/^#{1,6}\s/.test(p) && /[\p{L}\p{N}]/u.test(p));

  const out: string[] = [];
  let length = 0;
  for (const p of paragraphs) {
    if (out.length >= 2 || (out.length > 0 && length + p.length > maxChars)) break;
    out.push(p);
    length += p.length;
  }
  let text = out.join("\n\n");
  if (text.length > maxChars * 1.4) {
    const cut = text.slice(0, maxChars);
    const end = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("? "), cut.lastIndexOf("! "));
    text = end > maxChars * 0.4 ? cut.slice(0, end + 1) : cut;
  }
  return text;
}
