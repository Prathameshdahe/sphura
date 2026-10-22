# Sphura brand components — props contract

Owned by the **components** builder; consumed by the **app** builder. Both must follow this file.
All files live in `src/components/ui/` (shadcn convention) and are imported as `@/components/ui/<file>`.

## Design tokens (defined by the app builder in `src/index.css`)
- Fonts: `--font-sans` (Geist Variable, UI), `--font-serif` ("Source Serif 4 Variable", assistant answer prose), `--font-brand` ("Fraunces Variable", wordmark + greeting), `--font-mono` ("JetBrains Mono Variable").
  Fonts are loaded in `main.tsx` via `@fontsource-variable/{geist,source-serif-4,fraunces,jetbrains-mono}`.
- Brand gradient (violet on a grey Swiss grid): deep violet `#6D28D9` → violet `#7C3AED` → lilac `#A855F7`. CSS vars `--sphura-1`, `--sphura-2`, `--sphura-3` (the components read these; the legacy saffron/rose/violet literals they still carry are re-pointed through tokens in `index.css`).
- Theme: `.dark` class on `<html>` (next-themes). Components must look right in BOTH themes.

## `sphura-logo.tsx`
```ts
export type LogoState = "idle" | "thinking" | "answer" | "static";
export interface SphuraLogoProps {
  size?: number;            // px of the mark, default 32
  state?: LogoState;        // default "idle"
  withWordmark?: boolean;   // render "Sphura" next to the mark (Fraunces), default false
  className?: string;
}
export function SphuraLogo(props: SphuraLogoProps): JSX.Element;
export default SphuraLogo;
```
Mark = four-point spark ("sphur" = a flash of insight) with the brand gradient.
idle: slow breathe + shimmer · thinking: ripple rings + faster pulse · answer: one-shot burst of 8 rays, then settles to idle · static: no motion.
Respects `prefers-reduced-motion`. A static copy is exported to `public/sphura.svg` (favicon).

## `sphura-orb.tsx` (dotted sphere extracted from MorphOrb)
```ts
export type OrbProgram = 0 | 1 | 2 | 3;   // 0 thinking · 1 searching · 2 reading/analyzing · 3 composing (see PHASE_PROGRAM in lib/types.ts)
export interface SphuraOrbProps {
  program?: OrbProgram;     // default 0; changes cross-fade smoothly
  size?: number;            // rendered px, default 40
  active?: boolean;         // true = assembled + spinning; false = collapses/fades out. default true
  done?: boolean;           // play the "resolve" sweep (dots glow to the done colour), default false
  className?: string;
  "aria-label"?: string;
}
export function SphuraOrb(props: SphuraOrbProps): JSX.Element;
export default SphuraOrb;
```
Dot colour follows the theme (light dots on dark, dark dots on light). Pauses when off-screen or tab hidden.

## `ai-thiking-orb-and-input.tsx` (MorphOrb — the user's component, kept)
Default export `MorphOrb`. Existing props stay (`onSubmit`, `minThinkMs`, `speed`). Added optional props:
```ts
statusLabel?: string;           // when set, shown instead of the timer-cycled labels while thinking (real agent status)
statusProgram?: 0 | 1 | 2 | 3;  // when set, drives the orb light program instead of the timer
placeholder?: string;           // pill placeholder, default "Ask anything…"
```
Styles live in `src/styles/morph-orb.css` (+ `morph-orb-keyframes.css`), imported by the component itself.
It must be rendered inside a full-viewport container (`h-dvh w-full relative overflow-hidden`): its geometry uses the window size.

## `ai-mascot-input.tsx` (the user's composer, adapted — robot mascot kept)
```ts
export type Effort = "fast" | "balanced" | "deep";
export interface ComposerModel {
  id: string;               // ModelInfo.id
  name: string;             // ModelInfo.label
  provider: string;         // "Gemini" | "Groq" | "Ollama" | "LM Studio" | "Mock"
  description?: string;
  available: boolean;
  reason?: string | null;   // shown when unavailable (entry disabled)
  icon?: React.ComponentType<{ size?: number; className?: string }>; // default chosen from provider
}
export interface ComposerAttachment {
  id: string;               // client id (doc id once uploaded)
  name: string;
  isImage: boolean;
  status: "uploading" | "processing" | "ready" | "error";
  error?: string | null;
}
export interface ComposerSubmit { prompt: string; modelId: string; effort: Effort; webSearch: boolean }
export interface AiMascotInputProps {
  onSubmit: (data: ComposerSubmit) => void;     // text is cleared immediately on submit
  onCancel?: () => void;                         // stop button while isProcessing
  isProcessing?: boolean;
  models: ComposerModel[];
  modelId?: string;                              // controlled selected model
  onModelChange?: (id: string) => void;
  effort?: Effort; onEffortChange?: (e: Effort) => void;
  webSearch?: boolean; onWebSearchChange?: (on: boolean) => void;
  attachments?: ComposerAttachment[];
  onAttach?: (files: File[]) => void;            // multiple files, via picker, drag & drop, or paste
  onRemoveAttachment?: (id: string) => void;
  value?: string; onChange?: (v: string) => void; // optional controlled text
  disabled?: boolean;
  placeholder?: string;
  showWelcome?: boolean; title?: string; subtitle?: string;  // welcome banner with the robot (home screen)
  showMascot?: boolean;                          // default true
  enableVoice?: boolean; enableWebSearch?: boolean; enableAttachments?: boolean;
  autoFocus?: boolean;
  className?: string; containerClassName?: string;
}
export function AiMascotInput(props: AiMascotInputProps): JSX.Element;
export default AiMascotInput;
// also exported: RobotBeta, EyeLED, GeminiIcon, GroqIcon, LocalModelIcon
```
Send is disabled while any attachment is `uploading`. Enter = send, Shift+Enter = newline (IME-safe).
Voice uses the Web Speech API; if unsupported it shows an inline hint (no fake/simulated transcription).
