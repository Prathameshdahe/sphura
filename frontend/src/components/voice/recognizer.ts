/** Hands-free speech-to-text over the Web Speech API: continuous recognition, committed after a pause. */

interface RecognitionAlternative {
  transcript: string;
}
interface RecognitionResult {
  isFinal: boolean;
  length: number;
  [index: number]: RecognitionAlternative;
}
interface RecognitionEvent {
  resultIndex: number;
  results: { length: number; [index: number]: RecognitionResult };
}
interface RecognitionErrorEvent {
  error: string;
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type RecognitionCtor = new () => Recognition;

export function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export type RecognizerError = "denied" | "no-mic" | "network" | "unsupported" | "failed";

export interface RecognizerHandlers {
  /** Live transcript (final + interim) of the current utterance. */
  onInterim: (text: string) => void;
  /** The utterance after `silenceMs` without new speech. Recognition is stopped; call listen() again. */
  onCommit: (text: string) => void;
  onError: (error: RecognizerError) => void;
}

export interface Recognizer {
  listen: () => void;
  /** Stop without committing. */
  cancel: () => void;
  /** Stop and commit the current text now ("" when nothing was heard). */
  commitNow: () => void;
}

export function createRecognizer(handlers: RecognizerHandlers, silenceMs = 900): Recognizer {
  const Ctor = recognitionCtor();
  let rec: Recognition | null = null;
  let active = false;
  let finalText = "";
  let interim = "";
  let timer: ReturnType<typeof setTimeout> | undefined;
  let restarts = 0;

  const text = () => `${finalText} ${interim}`.replace(/\s+/g, " ").trim();

  const teardown = () => {
    clearTimeout(timer);
    const r = rec;
    rec = null;
    if (r) {
      r.onresult = null;
      r.onerror = null;
      r.onend = null;
      try {
        r.abort();
      } catch {
        /* already stopped */
      }
    }
  };

  const commit = () => {
    const said = text();
    if (!active || !said) return;
    active = false;
    teardown();
    handlers.onCommit(said);
  };

  const begin = () => {
    if (!Ctor) {
      handlers.onError("unsupported");
      return;
    }
    const r = new Ctor();
    r.lang = navigator.language || "en-US";
    r.continuous = true;
    r.interimResults = true;
    r.maxAlternatives = 1;
    r.onresult = (e) => {
      let fin = "";
      let mid = "";
      for (let i = 0; i < e.results.length; i++) {
        const res = e.results[i];
        const t = res[0]?.transcript ?? "";
        if (res.isFinal) fin += `${t} `;
        else mid += t;
      }
      finalText = fin.trim();
      interim = mid.trim();
      restarts = 0;
      handlers.onInterim(text());
      clearTimeout(timer);
      if (text()) timer = setTimeout(commit, silenceMs);
    };
    r.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return; // onend restarts
      active = false;
      teardown();
      handlers.onError(
        e.error === "not-allowed" || e.error === "service-not-allowed"
          ? "denied"
          : e.error === "audio-capture"
            ? "no-mic"
            : e.error === "network"
              ? "network"
              : "failed",
      );
    };
    r.onend = () => {
      if (!active) return;
      // Engines end a session after silence or ~60 s: keep the utterance and continue listening.
      if (text()) {
        commit();
        return;
      }
      if (++restarts > 20) {
        active = false;
        handlers.onError("failed");
        return;
      }
      rec = null;
      setTimeout(() => active && begin(), 120);
    };
    rec = r;
    try {
      r.start();
    } catch {
      active = false;
      handlers.onError("failed");
    }
  };

  return {
    listen: () => {
      teardown();
      active = true;
      finalText = "";
      interim = "";
      restarts = 0;
      begin();
    },
    cancel: () => {
      active = false;
      teardown();
    },
    commitNow: () => {
      if (!active) return;
      const said = text();
      active = false;
      teardown();
      handlers.onCommit(said);
    },
  };
}
