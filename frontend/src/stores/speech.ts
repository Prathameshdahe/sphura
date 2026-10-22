import { create } from "zustand";
import { spokenSummary } from "@/components/voice/spoken-summary";
import { browserTtsSupported, chunkText, pickVoice, speakableText, ttsSupported } from "@/components/voice/tts";
import { isAbortError } from "@/lib/api";
import { getVoiceStatus, serverTtsLikely, speakText } from "@/lib/feature-api/voice";

export type SpeakResult = "ended" | "stopped" | "error";
export type SpeechEngine = "server" | "browser";

/** Controls for an answer that is read aloud while it is still being written. */
export interface LiveSpeech {
  /** The answer so far (markdown). Finished sentences are queued for speech right away. */
  feed: (markdown: string) => void;
  /** No more text is coming: speak the rest; resolves when everything was said (or it was stopped). */
  finish: (finalMarkdown?: string) => Promise<SpeakResult>;
}

/**
 * One answer is read aloud at a time (Read-aloud buttons, spoken replies and voice mode share this).
 * Speech is pipelined: a short first chunk (≤ 200 chars) is requested from POST /api/voice/speak as soon as it
 * exists, the next chunk is fetched while the current one plays. If the server voice is unavailable (503), fails,
 * or takes longer than 2.5 s for the first chunk, the browser's speechSynthesis reads instead.
 */
interface SpeechStore {
  speakingId: string | null;
  paused: boolean;
  /** Which voice is playing right now (null while idle). */
  engine: SpeechEngine | null;
  /** Speak a finished markdown answer; resolves when it finishes, is stopped, or fails. */
  speak: (id: string, markdown: string) => Promise<SpeakResult>;
  /** Start speaking an answer that is still streaming (spoken-summary rules: first ~2 paragraphs). */
  speakLive: (id: string) => LiveSpeech;
  pause: () => void;
  resume: () => void;
  stop: () => void;
}

interface Session {
  gen: number;
  resolve: (r: SpeakResult) => void;
  controller: AbortController;
  audio: HTMLAudioElement | null;
  url: string | null;
  watchdog: ReturnType<typeof setInterval> | null;
  /** Wakes a live session's player when new text is queued (or when it is stopped). */
  wake: (() => void) | null;
}

/** Server chunks stay under 200 chars (Groq Orpheus' limit; longer text would route to the slower Gemini voice). */
const FIRST_CHUNK = 190;
const NEXT_CHUNK = 190;
const BROWSER_CHUNK = 220;
/** First server audio must arrive within this, else the browser voice takes over. */
const FIRST_AUDIO_MS = 2500;

let current: Session | null = null;
let generation = 0;
// Chrome garbage-collects queued utterances and then never fires `end`: keep references.
const keep: { utterances: SpeechSynthesisUtterance[] } = { utterances: [] };

function settle(gen: number, result: SpeakResult) {
  if (!current || current.gen !== gen) return;
  const c = current;
  current = null;
  c.controller.abort();
  if (c.watchdog) clearInterval(c.watchdog);
  if (c.audio) {
    c.audio.onended = null;
    c.audio.onerror = null;
    c.audio.pause();
    c.audio.removeAttribute("src");
  }
  if (c.url) URL.revokeObjectURL(c.url);
  keep.utterances = [];
  c.wake?.();
  useSpeech.setState({ speakingId: null, paused: false, engine: null });
  c.resolve(result);
}

const live = (gen: number) => !!current && current.gen === gen;

/** Short first chunk for a fast first sound, then larger ones (whole sentences where possible). */
function progressiveChunks(text: string, first = FIRST_CHUNK, next = NEXT_CHUNK): string[] {
  const small = chunkText(text, first);
  if (small.length <= 1) return small;
  const out = [small[0]];
  let cur = "";
  for (const piece of small.slice(1)) {
    if (cur && (cur + " " + piece).length > next) {
      out.push(cur);
      cur = piece;
    } else cur = cur ? `${cur} ${piece}` : piece;
  }
  if (cur) out.push(cur);
  return out;
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("timeout")), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e: unknown) => {
        clearTimeout(t);
        reject(e instanceof Error ? e : new Error("failed"));
      },
    );
  });
}

/** Play one wav blob to the end (resolves false when stopped/paused-away or on a decode error). */
function playBlob(gen: number, blob: Blob): Promise<boolean> {
  return new Promise((resolve) => {
    const c = current;
    if (!c || c.gen !== gen) return resolve(false);
    const audio = new Audio();
    const url = URL.createObjectURL(blob);
    if (c.url) URL.revokeObjectURL(c.url);
    c.audio = audio;
    c.url = url;
    audio.src = url;
    audio.preload = "auto";
    audio.onended = () => resolve(true);
    audio.onerror = () => resolve(false);
    audio.play().catch(() => resolve(false));
    if (useSpeech.getState().paused) audio.pause();
  });
}

function speakViaBrowser(gen: number, text: string): Promise<"ended" | "stopped" | "unavailable"> {
  return new Promise((resolve) => {
    const c = current;
    if (!c || c.gen !== gen) return resolve("stopped");
    if (!browserTtsSupported()) return resolve("unavailable");
    const synth = window.speechSynthesis;
    const chunks = chunkText(text, BROWSER_CHUNK);
    if (!chunks.length) return resolve("ended");
    useSpeech.setState({ engine: "browser" });
    const busy = synth.speaking || synth.pending;
    if (busy) synth.cancel();
    let idle = 0;
    let settled = false;
    const done = (r: "ended" | "stopped" | "unavailable") => {
      if (settled) return;
      settled = true;
      if (c.watchdog) clearInterval(c.watchdog);
      c.watchdog = null;
      resolve(r);
    };
    if (c.watchdog) clearInterval(c.watchdog);
    // Some engines never fire `end` (hidden tab, voice change): finish when the queue is really empty.
    c.watchdog = setInterval(() => {
      if (!live(gen)) return done("stopped");
      if (useSpeech.getState().paused) return;
      idle = !synth.speaking && !synth.pending ? idle + 1 : 0;
      if (idle >= 4) done("ended");
    }, 500);
    const voice = pickVoice();
    const enqueue = () => {
      if (!live(gen)) return done("stopped");
      keep.utterances = chunks.map((t, i) => {
        const u = new SpeechSynthesisUtterance(t);
        if (voice) {
          u.voice = voice;
          u.lang = voice.lang;
        }
        u.rate = 1.05;
        u.pitch = 1;
        if (i === chunks.length - 1) u.onend = () => done("ended");
        u.onerror = (e) => {
          if (e.error === "interrupted" || e.error === "canceled") return;
          done("unavailable");
        };
        synth.speak(u);
        return u;
      });
    };
    // Chrome drops an utterance queued in the same tick as cancel().
    if (busy) setTimeout(enqueue, 60);
    else enqueue();
  });
}

/* ───────────── queue player shared by finished and live answers ───────────── */

interface Queue {
  items: { text: string; audio: Promise<Blob> | null }[];
  next: number;
  finished: boolean;
  engine: SpeechEngine;
  /** The voice status has been checked: until then nothing is POSTed to /voice/speak. */
  checked: boolean;
}

/** Start the server request for item `i` (if the server voice is in use and it hasn't started yet). */
function prefetch(gen: number, q: Queue, i: number) {
  const item = q.items[i];
  if (!item || item.audio || q.engine !== "server" || !q.checked || !live(gen)) return;
  item.audio = speakText(item.text, undefined, current?.controller.signal);
  item.audio.catch(() => undefined);
}

/** Plays queued chunks in order until the queue is finished; falls back to the browser voice on any server trouble. */
async function runQueue(gen: number, q: Queue): Promise<SpeakResult> {
  if (q.engine === "server" && !q.checked) {
    const status = await getVoiceStatus();
    if (!live(gen)) return "stopped";
    if (!status.tts && browserTtsSupported()) {
      q.engine = "browser";
      useSpeech.setState({ engine: "browser" });
    }
  }
  q.checked = true;
  for (;;) {
    if (!live(gen)) return "stopped";
    const item = q.items[q.next];
    if (!item) {
      if (q.finished) return "ended";
      await new Promise<void>((resolve) => {
        if (current && current.gen === gen) current.wake = resolve;
        else resolve();
      });
      continue;
    }
    const index = q.next;
    q.next += 1;
    if (q.engine === "server") {
      prefetch(gen, q, index);
      prefetch(gen, q, index + 1);
      let blob: Blob | null = null;
      try {
        blob = await (index === 0 ? withTimeout(item.audio as Promise<Blob>, FIRST_AUDIO_MS) : (item.audio as Promise<Blob>));
      } catch (e) {
        if (!live(gen) || isAbortError(e)) return "stopped";
        blob = null;
      }
      if (!live(gen)) return "stopped";
      if (blob) {
        const ok = await playBlob(gen, blob);
        if (!live(gen)) return "stopped";
        if (ok) continue;
      }
      // 503, slow first audio, network or decode trouble: the browser voice reads this and every later chunk.
      if (!browserTtsSupported()) return "error";
      q.engine = "browser";
      useSpeech.setState({ engine: "browser" });
    }
    const r = await speakViaBrowser(gen, item.text);
    if (r === "stopped" || !live(gen)) return "stopped";
    if (r === "unavailable") return "error";
  }
}

function startSession(): { gen: number; done: Promise<SpeakResult> } {
  if (current) settle(current.gen, "stopped");
  if (browserTtsSupported()) window.speechSynthesis.cancel();
  const gen = ++generation;
  let resolve: (r: SpeakResult) => void = () => undefined;
  const done = new Promise<SpeakResult>((r) => {
    resolve = r;
  });
  current = { gen, resolve, controller: new AbortController(), audio: null, url: null, watchdog: null, wake: null };
  return { gen, done };
}

const initialEngine = (): SpeechEngine => (serverTtsLikely() && typeof Audio !== "undefined" ? "server" : "browser");

/** Index just past the last finished sentence ("." / "!" / "?" / ":" followed by whitespace). */
function lastBoundary(text: string): number {
  let at = 0;
  const re = /[.!?:;](?=\s)/g;
  for (let m = re.exec(text); m; m = re.exec(text)) at = m.index + 1;
  return at;
}

export const useSpeech = create<SpeechStore>()((set, get) => ({
  speakingId: null,
  paused: false,
  engine: null,
  speak: (id, markdown) => {
    if (!ttsSupported()) return Promise.resolve("error" as const);
    const text = speakableText(markdown);
    if (!text) return Promise.resolve("ended" as const);
    const { gen, done } = startSession();
    const q: Queue = {
      items: progressiveChunks(text).map((t) => ({ text: t, audio: null })),
      next: 0,
      finished: true,
      engine: initialEngine(),
      checked: false,
    };
    set({ speakingId: id, paused: false, engine: q.engine });
    void runQueue(gen, q).then((r) => settle(gen, r));
    return done;
  },
  speakLive: (id) => {
    const dead: LiveSpeech = { feed: () => undefined, finish: () => Promise.resolve("error" as const) };
    if (!ttsSupported()) return dead;
    const { gen, done } = startSession();
    const q: Queue = { items: [], next: 0, finished: false, engine: initialEngine(), checked: false };
    set({ speakingId: id, paused: false, engine: q.engine });
    let consumed = 0;
    let running = false;

    const enqueue = (markdown: string, final: boolean) => {
      if (!live(gen) || q.finished) return;
      const plain = speakableText(spokenSummary(markdown));
      const avail = final ? plain.length : lastBoundary(plain);
      if (avail <= consumed) return;
      const fresh = plain.slice(consumed, avail).trim();
      consumed = avail;
      if (!fresh) return;
      const chunks = q.items.length === 0 ? progressiveChunks(fresh) : chunkText(fresh, NEXT_CHUNK);
      for (const t of chunks) q.items.push({ text: t, audio: null });
      prefetch(gen, q, q.next);
      if (!running) {
        running = true;
        void runQueue(gen, q).then((r) => settle(gen, r));
      }
      current?.wake?.();
    };

    return {
      feed: (markdown) => enqueue(markdown, false),
      finish: (finalMarkdown) => {
        if (finalMarkdown) enqueue(finalMarkdown, true);
        q.finished = true;
        if (!running) settle(gen, "ended");
        else if (live(gen)) current?.wake?.();
        return done;
      },
    };
  },
  pause: () => {
    if (!get().speakingId) return;
    if (current?.audio) current.audio.pause();
    else if (browserTtsSupported()) window.speechSynthesis.pause();
    set({ paused: true });
  },
  resume: () => {
    if (!get().speakingId) return;
    if (current?.audio) current.audio.play().catch(() => undefined);
    else if (browserTtsSupported()) window.speechSynthesis.resume();
    set({ paused: false });
  },
  stop: () => {
    if (current) settle(current.gen, "stopped");
    if (browserTtsSupported()) window.speechSynthesis.cancel();
    set({ speakingId: null, paused: false, engine: null });
  },
}));
