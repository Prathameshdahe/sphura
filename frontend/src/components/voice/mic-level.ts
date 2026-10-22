/** Microphone access + loudness (0..1) via a Web Audio analyser — drives the orb while listening and the recorder's silence detection. */

export type MicError = "denied" | "no-mic" | "insecure" | "failed";

export interface MicHandle {
  /** The raw microphone stream (shared with the MediaRecorder of the server-side transcriber). */
  stream: MediaStream;
  close: () => void;
}

export class MicOpenError extends Error {
  readonly code: MicError;
  constructor(code: MicError) {
    super(code);
    this.code = code;
  }
}

const AudioCtx: typeof AudioContext | undefined =
  typeof window === "undefined"
    ? undefined
    : (window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext);

/**
 * Smoothed RMS level of a stream, reported every animation frame (fast attack, slow decay).
 * Returns a stop function. Without Web Audio the callback is never called.
 */
export function meterStream(stream: MediaStream, onLevel: (level: number) => void): () => void {
  if (!AudioCtx) return () => undefined;
  const ctx = new AudioCtx();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.6;
  source.connect(analyser);
  const buf = new Uint8Array(analyser.fftSize);
  let level = 0;
  let raf = 0;
  let closed = false;

  const tick = () => {
    if (closed) return;
    analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / buf.length);
    const target = Math.min(1, Math.max(0, (rms - 0.01) * 5));
    level = target > level ? level + (target - level) * 0.5 : level * 0.88 + target * 0.12;
    onLevel(level);
    raf = requestAnimationFrame(tick);
  };
  void ctx.resume().catch(() => undefined);
  raf = requestAnimationFrame(tick);

  return () => {
    closed = true;
    cancelAnimationFrame(raf);
    try {
      source.disconnect();
    } catch {
      /* already disconnected */
    }
    void ctx.close().catch(() => undefined);
    onLevel(0);
  };
}

export async function openMic(onLevel: (level: number) => void): Promise<MicHandle> {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new MicOpenError("insecure");
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    const name = (e as { name?: string } | null)?.name ?? "";
    if (name === "NotAllowedError" || name === "SecurityError") throw new MicOpenError("denied");
    if (name === "NotFoundError" || name === "OverconstrainedError") throw new MicOpenError("no-mic");
    throw new MicOpenError("failed");
  }
  const stopMeter = meterStream(stream, onLevel);
  return {
    stream,
    close: () => {
      stopMeter();
      stream.getTracks().forEach((t) => t.stop());
    },
  };
}
