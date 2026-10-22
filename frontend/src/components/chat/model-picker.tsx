import { useMemo, useRef, useState, type ComponentType } from "react";
import { Command as CommandPrimitive } from "cmdk";
import { Check, ChevronDown, Cpu } from "lucide-react";
import { Glyph } from "@/components/icons/glyphs";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { Effort } from "@/lib/types";
import { cn } from "@/lib/utils";

/* ───────────────────────────── contract ───────────────────────────── */
type IconComponent = ComponentType<{ size?: number; className?: string }>;

export interface ComposerModel {
  id: string;
  name: string;
  /** Display label of the provider ("Groq"). */
  provider: string;
  /** Raw provider key ("groq" | "gemini" | "ollama" | …) for grouping. */
  providerId?: string;
  description?: string;
  available: boolean;
  reason?: string | null;
  supportsTools?: boolean;
  supportsVision?: boolean;
  isDefault?: boolean;
  icon?: IconComponent;
}

/* ───────────────────────────── provider glyphs (trigger only) ───────────────────────────── */
/** Four-point star glyph for Gemini models. */
export const GeminiIcon = ({ size = 16, className = "" }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
    <path d="M12 1.5c.5 4.9 2.2 7.9 4.6 9.4 1.6 1 3.6 1.4 5.9 1.6-2.3.2-4.3.6-5.9 1.6-2.4 1.5-4.1 4.5-4.6 9.4-.5-4.9-2.2-7.9-4.6-9.4-1.6-1-3.6-1.4-5.9-1.6 2.3-.2 4.3-.6 5.9-1.6C9.8 9.4 11.5 6.4 12 1.5Z" />
  </svg>
);

/** Original glyph for Groq: a geometric "G" with speed lines (fast inference). */
export const GroqIcon = ({ size = 16, className = "" }: { size?: number; className?: string }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2.4}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    aria-hidden="true"
  >
    <path d="M19 8.2A7.5 7.5 0 1 0 20 13h-6.5" />
    <path d="M2 9.5h2.2M1.5 14.5h2.2" opacity={0.55} />
  </svg>
);

const LocalIcon: IconComponent = ({ size = 16, className }) => <Cpu size={size} className={className} strokeWidth={2} aria-hidden="true" />;

const EnsembleIcon: IconComponent = ({ size = 16, className }) => <Glyph name="merge" width={size} height={size} className={className} />;
const ChipIcon: IconComponent = ({ size = 16, className }) => <Glyph name="chip" width={size} height={size} className={className} />;

const GROUPS: Record<string, { label: string; icon: IconComponent; order: number }> = {
  ensemble: { label: "Ensemble", icon: EnsembleIcon, order: 0 },
  groq: { label: "Groq", icon: GroqIcon, order: 1 },
  nvidia: { label: "NVIDIA", icon: ChipIcon, order: 2 },
  gemini: { label: "Gemini", icon: GeminiIcon, order: 3 },
  ollama: { label: "On this laptop", icon: LocalIcon, order: 4 },
  lmstudio: { label: "On this laptop", icon: LocalIcon, order: 4 },
};

const groupOf = (m: ComposerModel | null) => {
  const key = (m?.providerId ?? m?.provider ?? "").toLowerCase().replace(/\s+/g, "");
  return GROUPS[key] ?? { label: m?.provider ?? "Other", icon: LocalIcon, order: 9 };
};

const EFFORTS: { id: Effort; label: string; desc: string }[] = [
  { id: "fast", label: "Fast", desc: "One quick tool pass" },
  { id: "balanced", label: "Balanced", desc: "Up to 3 tool rounds" },
  { id: "deep", label: "Deep", desc: "Up to 6 tool rounds" },
];

interface ModelPickerProps {
  models: ComposerModel[];
  current: ComposerModel | null;
  onSelect: (id: string) => void;
  effort: Effort;
  onEffortChange: (e: Effort) => void;
  disabled?: boolean;
}

/** Composer model picker: a plain grouped list (name + one muted line + a check) and a quiet effort toggle. */
export function ModelPicker({ models, current, onSelect, effort, onEffortChange, disabled }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const effortInfo = EFFORTS.find((e) => e.id === effort) ?? EFFORTS[1];
  const CurrentIcon = current?.icon ?? groupOf(current).icon;

  const groups = useMemo(() => {
    const map = new Map<string, { label: string; order: number; items: ComposerModel[] }>();
    for (const m of models) {
      const g = groupOf(m);
      const entry = map.get(g.label) ?? { label: g.label, order: g.order, items: [] };
      entry.items.push(m);
      map.set(g.label, entry);
    }
    return [...map.values()].sort((a, b) => a.order - b.order);
  }, [models]);

  return (
    <Popover open={open && !disabled} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          aria-label={`Model: ${current?.name ?? "none"}, effort: ${effortInfo.label}`}
          className="flex min-w-0 max-w-full items-center gap-1.5 rounded-xl bg-zinc-100 px-2.5 py-1.5 text-xs font-semibold whitespace-nowrap text-zinc-900 transition-all hover:bg-zinc-200/70 disabled:cursor-not-allowed disabled:opacity-50 data-[state=open]:bg-zinc-200/70 dark:bg-white/5 dark:text-zinc-100 dark:hover:bg-white/10 dark:data-[state=open]:bg-white/10"
        >
          <CurrentIcon size={13} className="shrink-0 text-zinc-500 dark:text-zinc-400" />
          <span className="min-w-0 max-w-26 truncate sm:max-w-36">{current?.name ?? (models.length ? "Choose model" : "No models")}</span>
          {current && !current.available && <span className="size-1.5 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />}
          <span className="hidden shrink-0 font-medium text-zinc-500 min-[380px]:inline dark:text-zinc-400">· {effortInfo.label}</span>
          <ChevronDown className="size-3 shrink-0 text-zinc-500 dark:text-zinc-400" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        sideOffset={8}
        collisionPadding={12}
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          listRef.current?.focus();
        }}
        className="flex max-h-[min(30rem,var(--radix-popover-content-available-height))] w-[min(18.5rem,calc(100vw-1.5rem))] flex-col gap-0 overflow-hidden rounded-xl border-0 p-0 shadow-pop ring-1 ring-border"
      >
        <CommandPrimitive
          ref={listRef}
          tabIndex={0}
          loop
          defaultValue={current?.id}
          label="Choose a model"
          className="flex min-h-0 flex-1 flex-col outline-none"
        >
          <CommandPrimitive.List className="scrollbar-thin min-h-0 flex-1 overflow-y-auto overscroll-contain px-1 pt-1 pb-1">
            <CommandPrimitive.Empty className="px-3 py-5 text-center text-sm text-muted-foreground">
              No models yet. Check the backend connection.
            </CommandPrimitive.Empty>
            {groups.map((g) => (
              <CommandPrimitive.Group
                key={g.label}
                heading={g.label}
                className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pt-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[10.5px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:uppercase"
              >
                {g.items.map((m) => {
                  const selected = m.id === current?.id;
                  return (
                    <CommandPrimitive.Item
                      key={m.id}
                      value={m.id}
                      keywords={[m.name, g.label]}
                      disabled={!m.available}
                      onSelect={() => {
                        onSelect(m.id);
                        setOpen(false);
                      }}
                      className="flex cursor-pointer items-start gap-2 rounded-lg px-2.5 py-1.5 outline-none data-[disabled=true]:cursor-not-allowed data-[selected=true]:bg-muted"
                    >
                      <span className={cn("min-w-0 flex-1", !m.available && "opacity-50")}>
                        <span className="flex items-center gap-1.5">
                          <span className={cn("truncate text-[13px] text-foreground", selected ? "font-semibold" : "font-medium")}>{m.name}</span>
                          {m.isDefault && (
                            <span className="shrink-0 rounded px-1 text-[10px] leading-4 font-medium text-muted-foreground ring-1 ring-border ring-inset">
                              Default
                            </span>
                          )}
                        </span>
                        <span className="block truncate text-[11.5px] text-muted-foreground">
                          {!m.available ? m.reason || "Unavailable right now" : m.description}
                        </span>
                      </span>
                      <span className="mt-0.5 grid size-4 shrink-0 place-items-center" aria-hidden>
                        {selected && <Check className="size-3.5 text-brand" strokeWidth={2.6} />}
                      </span>
                    </CommandPrimitive.Item>
                  );
                })}
              </CommandPrimitive.Group>
            ))}
          </CommandPrimitive.List>
        </CommandPrimitive>

        <div className="flex shrink-0 items-center gap-2 border-t px-3 py-2 text-[11.5px]">
          <span className="text-muted-foreground">Effort</span>
          <div className="ml-auto flex items-center gap-0.5" role="radiogroup" aria-label="Effort">
            {EFFORTS.map((lvl) => {
              const on = lvl.id === effort;
              return (
                <button
                  key={lvl.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  title={lvl.desc}
                  onClick={() => onEffortChange(lvl.id)}
                  className={cn(
                    "rounded-md px-1.5 py-0.5 transition-colors focus-visible:outline-2",
                    on ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {lvl.label}
                </button>
              );
            })}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
