import { toPlainText } from "@/lib/format";

/** Text-to-speech helpers: the server voice (POST /api/voice/speak → wav) plays through <audio>; speechSynthesis is the fallback. */

export const browserTtsSupported = (): boolean =>
  typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";

/** Something can read aloud here: the server voice needs only <audio>, otherwise the browser's own voices. */
export const ttsSupported = (): boolean => (typeof window !== "undefined" && typeof Audio !== "undefined") || browserTtsSupported();

/** Markdown answer → what should be spoken (no code, citations, URLs, table pipes or emoji). */
export function speakableText(md: string): string {
  const withoutCode = md.replace(/```[\s\S]*?(?:```|$)/g, "\n(Code omitted.)\n");
  return toPlainText(withoutCode)
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\p{Extended_Pictographic}/gu, "")
    .replace(/^\s*•\s*/gm, "")
    .replace(/[|*_#>`~]/g, " ")
    .replace(/([.!?:;,])\s*\n+\s*/g, "$1 ")
    .replace(/\s*\n+\s*/g, ". ")
    .replace(/\.\s*\./g, ".")
    .replace(/:\./g, ":")
    .replace(/\s+/g, " ")
    .replace(/^[.\s]+/, "")
    .trim();
}

/**
 * Split into utterances of at most `max` chars on sentence boundaries. Browser voices: ~220 (Chrome cuts long
 * utterances off after ~15 s); the server voice: ~1800 (the API takes ≤ 2000 chars per request).
 */
export function chunkText(text: string, max = 220): string[] {
  const sentences = text.match(/[^.!?]+[.!?]+["')\]]*\s*|[^.!?]+$/g) ?? [text];
  const out: string[] = [];
  let cur = "";
  for (const s of sentences) {
    if ((cur + s).length <= max) {
      cur += s;
      continue;
    }
    if (cur.trim()) out.push(cur.trim());
    let rest = s;
    while (rest.length > max) {
      let cut = rest.lastIndexOf(", ", max);
      if (cut < max * 0.4) cut = rest.lastIndexOf(" ", max);
      if (cut <= 0) cut = max;
      out.push(rest.slice(0, cut + 1).trim());
      rest = rest.slice(cut + 1);
    }
    cur = rest;
  }
  if (cur.trim()) out.push(cur.trim());
  return out.filter((c) => /[\p{L}\p{N}]/u.test(c));
}

let cachedVoice: SpeechSynthesisVoice | null | undefined;
if (browserTtsSupported()) {
  window.speechSynthesis.addEventListener?.("voiceschanged", () => {
    cachedVoice = undefined;
  });
}

/** The most natural-sounding browser voice for the user's language (Edge "Natural", Google, Apple premium voices). */
export function pickVoice(): SpeechSynthesisVoice | null {
  if (cachedVoice !== undefined) return cachedVoice;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null; // not loaded yet — don't cache
  const want = (navigator.language || "en-US").toLowerCase();
  const base = want.split("-")[0];
  let pool = voices.filter((v) => v.lang.toLowerCase().startsWith(base));
  if (!pool.length) pool = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  if (!pool.length) pool = voices;
  const score = (v: SpeechSynthesisVoice) => {
    const name = v.name.toLowerCase();
    let s = 0;
    if (/natural|neural|premium|enhanced/.test(name)) s += 6;
    if (/online/.test(name)) s += 2;
    if (/google/.test(name)) s += 4;
    if (/aria|jenny|guy|sonia|neerja|samantha|ava|allison|daniel|karen|serena/.test(name)) s += 2;
    if (v.lang.toLowerCase() === want) s += 2;
    if (v.default) s += 1;
    if (/espeak|robot|novelty|bad news|whisper|zarvox|trinoids|albert|bells|boing|bubbles|cellos|jester|organ|superstar/.test(name)) s -= 10;
    return s;
  };
  cachedVoice = [...pool].sort((a, b) => score(b) - score(a))[0] ?? null;
  return cachedVoice;
}
