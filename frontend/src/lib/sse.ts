import { ApiError, requestStream } from "./api";
import type { ChatEvent, ChatRequest } from "./types";

export interface RawSseEvent {
  event: string;
  data: string;
}

/**
 * Incremental text/event-stream parser (WHATWG rules): LF / CRLF / CR line endings split
 * anywhere across chunks, multi-line `data:`, `:` comments (heartbeats), unknown fields ignored.
 */
export class SseParser {
  private buffer = "";
  private eventName = "";
  private dataLines: string[] = [];

  push(chunk: string): RawSseEvent[] {
    this.buffer += chunk;
    return this.drain(false);
  }

  /** Flush at end of stream (a trailing event without a blank line is still delivered). */
  end(): RawSseEvent[] {
    const events = this.drain(true);
    if (this.buffer) {
      this.line(this.buffer, events);
      this.buffer = "";
    }
    this.dispatch(events);
    return events;
  }

  private drain(final: boolean): RawSseEvent[] {
    const events: RawSseEvent[] = [];
    for (;;) {
      const m = /\r\n|\r|\n/.exec(this.buffer);
      if (!m) break;
      // A lone trailing "\r" may be the first half of a "\r\n" split across chunks.
      if (m[0] === "\r" && m.index === this.buffer.length - 1 && !final) break;
      const line = this.buffer.slice(0, m.index);
      this.buffer = this.buffer.slice(m.index + m[0].length);
      this.line(line, events);
    }
    return events;
  }

  private line(line: string, events: RawSseEvent[]): void {
    if (line === "") {
      this.dispatch(events);
      return;
    }
    if (line.startsWith(":")) return; // comment / ": ping"
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.eventName = value;
    else if (field === "data") this.dataLines.push(value);
  }

  private dispatch(events: RawSseEvent[]): void {
    if (this.dataLines.length > 0) {
      events.push({ event: this.eventName || "message", data: this.dataLines.join("\n") });
    }
    this.eventName = "";
    this.dataLines = [];
  }
}

const CHAT_EVENTS = new Set<string>([
  "start",
  "status",
  "step",
  "sources",
  "delta",
  "title",
  "verification",
  "done",
  "error",
]);

export function toChatEvent(raw: RawSseEvent): ChatEvent | null {
  if (!CHAT_EVENTS.has(raw.event)) return null;
  try {
    return { event: raw.event, data: JSON.parse(raw.data) } as ChatEvent;
  } catch {
    return null;
  }
}

/** POST /api/chat and yield typed events until the server closes the stream. Abort via `signal`. */
export async function* streamChat(req: ChatRequest, signal: AbortSignal): AsyncGenerator<ChatEvent, void, undefined> {
  const body = await requestStream("/chat", req, signal);
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  try {
    for (;;) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (e) {
        if (signal.aborted) throw e;
        throw new ApiError(0, "The connection to Sphura was interrupted.");
      }
      if (chunk.done) break;
      for (const raw of parser.push(decoder.decode(chunk.value, { stream: true }))) {
        const ev = toChatEvent(raw);
        if (ev) yield ev;
      }
    }
    const tail = [...parser.push(decoder.decode()), ...parser.end()];
    for (const raw of tail) {
      const ev = toChatEvent(raw);
      if (ev) yield ev;
    }
  } finally {
    reader.cancel().catch(() => undefined);
  }
}
