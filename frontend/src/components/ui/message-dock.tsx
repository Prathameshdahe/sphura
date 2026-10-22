import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ComponentType, type CSSProperties, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowUp, LayoutGrid, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

/* MessageDock — a pill that holds a "new" button, a row of round character buttons and a menu button.
   Picking a character springs the pill open into a one-line composer addressed to that character
   (the others drop away, the menu button morphs into send). Adapted from the 21st.dev MessageDock and
   themed with Sphura's tokens: lucide icons in tinted round buttons instead of emoji, no online dots. */

export interface DockCharacter {
  id: string;
  /** "Tax helper" */
  name: string;
  icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  /** Any CSS colour (a token is best, e.g. "var(--chart-2)"): tints the round button and the open pill. */
  tint: string;
  /** Overrides the default "Ask the tax helper…" placeholder. */
  placeholder?: string;
}

export interface MessageDockProps {
  characters: DockCharacter[];
  onMessageSend?: (message: string, character: DockCharacter, characterIndex: number) => void;
  onCharacterSelect?: (character: DockCharacter, characterIndex: number) => void;
  onDockToggle?: (isExpanded: boolean) => void;
  /** The leading button ("new"). */
  onSparkleClick?: () => void;
  sparkleLabel?: string;
  sparkleIcon?: ReactNode;
  /** Short text shown before the characters while the dock is closed (e.g. "Ask a specialist"). */
  label?: ReactNode;
  /** Content of the menu popover; gets a `close` callback. */
  renderMenu?: (close: () => void) => ReactNode;
  menuLabel?: string;
  menuIcon?: ReactNode;
  className?: string;
  /** Width of the open pill in px (clamped to the viewport). Default 380. */
  expandedWidth?: number;
  /** Which way characters drop away and the menu opens. Default "top" (dock sits in a top bar). */
  position?: "bottom" | "top";
  showSparkleButton?: boolean;
  showMenuButton?: boolean;
  enableAnimations?: boolean;
  placeholder?: (characterName: string) => string;
  autoFocus?: boolean;
  closeOnClickOutside?: boolean;
  closeOnEscape?: boolean;
  closeOnSend?: boolean;
}

const SPRING = { type: "spring", stiffness: 420, damping: 36, mass: 0.8 } as const;
const HOVER_SPRING = { type: "spring", stiffness: 400, damping: 25 } as const;

const tintBg = (tint: string, pct: number) => `color-mix(in oklch, ${tint} ${pct}%, transparent)`;

export function MessageDock({
  characters,
  onMessageSend,
  onCharacterSelect,
  onDockToggle,
  onSparkleClick,
  sparkleLabel = "New",
  sparkleIcon,
  label,
  renderMenu,
  menuLabel = "Menu",
  menuIcon,
  className,
  expandedWidth = 380,
  position = "top",
  showSparkleButton = true,
  showMenuButton = true,
  enableAnimations = true,
  placeholder = (name) => `Ask the ${name.toLowerCase()}…`,
  autoFocus = true,
  closeOnClickOutside = true,
  closeOnEscape = true,
  closeOnSend = true,
}: MessageDockProps) {
  const reduced = useReducedMotion() ?? false;
  const animate = enableAnimations && !reduced;
  const [selected, setSelected] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsedWidth, setCollapsedWidth] = useState<number | null>(null);
  const [openWidth, setOpenWidth] = useState(expandedWidth);
  const rootRef = useRef<HTMLDivElement>(null);
  const rowRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const expanded = selected !== null;
  const character = selected !== null ? characters[selected] : null;
  const dropY = position === "top" ? -14 : 14;

  // Measure the resting pill (on mount and when its contents change, never mid-animation) so the spring has a
  // start and an end width. Exiting children are still mounted right after a collapse, so `expanded` isn't a dep.
  const expandedRef = useRef(expanded);
  useLayoutEffect(() => {
    expandedRef.current = expanded;
  });
  useLayoutEffect(() => {
    if (expandedRef.current || !rowRef.current) return;
    setCollapsedWidth(Math.ceil(rowRef.current.scrollWidth) + 2);
  }, [characters.length, showSparkleButton, showMenuButton, label]);

  const collapse = useCallback(() => {
    setSelected(null);
    setMessage("");
    onDockToggle?.(false);
  }, [onDockToggle]);

  const select = (i: number) => {
    if (selected === i) {
      collapse();
      return;
    }
    setMenuOpen(false);
    setOpenWidth(Math.min(expandedWidth, document.documentElement.clientWidth - 24));
    setSelected(i);
    onCharacterSelect?.(characters[i], i);
    if (selected === null) onDockToggle?.(true);
  };

  useEffect(() => {
    if (expanded && autoFocus) {
      const t = setTimeout(() => inputRef.current?.focus(), 120);
      return () => clearTimeout(t);
    }
  }, [expanded, autoFocus, selected]);

  // Escape / click outside close whatever is open.
  useEffect(() => {
    if (!expanded && !menuOpen) return;
    const onDown = (e: PointerEvent) => {
      if (!closeOnClickOutside) return;
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        if (expanded) collapse();
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || !closeOnEscape) return;
      e.stopPropagation();
      if (menuOpen) {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      } else if (expanded) collapse();
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [expanded, menuOpen, collapse, closeOnClickOutside, closeOnEscape]);

  const send = () => {
    const text = message.trim();
    if (!text || selected === null) return;
    onMessageSend?.(text, characters[selected], selected);
    setMessage("");
    if (closeOnSend) collapse();
  };

  const width = expanded ? openWidth : (collapsedWidth ?? "auto");

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <motion.div
        className="relative overflow-hidden rounded-full border bg-card shadow-soft"
        initial={false}
        animate={{
          width,
          backgroundColor: character ? `color-mix(in oklch, ${character.tint} 9%, var(--card))` : "var(--card)",
          borderColor: character ? `color-mix(in oklch, ${character.tint} 35%, var(--border))` : "var(--border)",
        }}
        transition={animate ? SPRING : { duration: 0 }}
      >
        <div ref={rowRef} className="flex h-12 w-max min-w-full items-center gap-1 px-1.5">
          {/* leading "new" button */}
          <AnimatePresence initial={false}>
            {showSparkleButton && !expanded && (
              <motion.div
                key="sparkle"
                className="flex items-center"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: "auto" }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: animate ? 0.18 : 0 }}
              >
                <motion.button
                  type="button"
                  onClick={onSparkleClick}
                  aria-label={sparkleLabel}
                  title={sparkleLabel}
                  whileHover={animate ? { scale: 1.06 } : undefined}
                  whileTap={{ scale: 0.92 }}
                  transition={HOVER_SPRING}
                  className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground shadow-xs focus-visible:outline-2"
                >
                  {sparkleIcon ?? <Plus className="size-4" strokeWidth={2.4} />}
                </motion.button>
                <span className="mx-1.5 h-5 w-px shrink-0 bg-border" aria-hidden />
              </motion.div>
            )}
          </AnimatePresence>

          {/* leading label */}
          <AnimatePresence initial={false}>
            {label && !expanded && (
              <motion.span
                key="label"
                className="flex items-center overflow-hidden whitespace-nowrap"
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: "auto" }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: animate ? 0.18 : 0 }}
              >
                <span className="pr-2 pl-2 text-[13px] font-medium text-muted-foreground">{label}</span>
              </motion.span>
            )}
          </AnimatePresence>

          {/* characters */}
          <div className="flex items-center gap-0.5" role="group" aria-label="Specialists">
            {characters.map((c, i) => {
              const isSel = selected === i;
              const hidden = expanded && !isSel;
              const Icon = c.icon;
              return (
                <AnimatePresence key={c.id} initial={false}>
                  {!hidden && (
                    <motion.button
                      layout={animate ? "position" : false}
                      type="button"
                      onClick={() => select(i)}
                      aria-pressed={isSel}
                      aria-label={isSel ? `Close ${c.name}` : (c.placeholder?.replace(/[.…]+$/, "") ?? `Ask the ${c.name.toLowerCase()}`)}
                      title={c.name}
                      initial={{ opacity: 0, y: dropY, scale: 0.8 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: dropY * 4, scale: 0.8, transition: { duration: animate ? 0.2 : 0, delay: animate ? i * 0.03 : 0 } }}
                      whileHover={animate && !isSel ? { y: -2, scale: 1.08 } : undefined}
                      whileTap={{ scale: 0.92 }}
                      transition={animate ? HOVER_SPRING : { duration: 0 }}
                      className="grid size-9 shrink-0 place-items-center rounded-full ring-1 ring-inset focus-visible:outline-2"
                      style={{ background: tintBg(c.tint, isSel ? 24 : 12), color: c.tint, "--tw-ring-color": tintBg(c.tint, 30) } as CSSProperties}
                    >
                      <Icon className="size-[18px]" strokeWidth={1.9} />
                    </motion.button>
                  )}
                </AnimatePresence>
              );
            })}
          </div>

          {/* input */}
          <AnimatePresence initial={false}>
            {character && (
              <motion.div
                key="input"
                className="min-w-0 flex-1"
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 16, transition: { duration: 0.12 } }}
                transition={animate ? { ...SPRING, delay: 0.05 } : { duration: 0 }}
              >
                <input
                  ref={inputRef}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  placeholder={character.placeholder ?? placeholder(character.name)}
                  aria-label={character.placeholder ?? placeholder(character.name)}
                  maxLength={2000}
                  className="h-9 w-full bg-transparent px-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground"
                />
              </motion.div>
            )}
          </AnimatePresence>

          {/* menu ↔ send */}
          {(showMenuButton || expanded) && (
            <>
              {!expanded && <span className="mx-1.5 h-5 w-px shrink-0 bg-border" aria-hidden />}
              <motion.button
                ref={menuButtonRef}
                type="button"
                layout={animate ? "position" : false}
                onClick={() => (expanded ? send() : setMenuOpen((o) => !o))}
                disabled={expanded && !message.trim()}
                aria-label={expanded ? "Send" : menuLabel}
                aria-haspopup={expanded ? undefined : "menu"}
                aria-expanded={expanded ? undefined : menuOpen}
                title={expanded ? "Send" : menuLabel}
                whileTap={{ scale: 0.9 }}
                transition={HOVER_SPRING}
                className={cn(
                  "grid size-8 shrink-0 place-items-center rounded-full transition-colors focus-visible:outline-2 disabled:cursor-not-allowed",
                  expanded
                    ? "bg-primary text-primary-foreground disabled:opacity-40"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground",
                )}
              >
                <AnimatePresence mode="popLayout" initial={false}>
                  <motion.span
                    key={expanded ? "send" : "menu"}
                    initial={{ rotate: expanded ? -90 : 90, scale: 0.5, opacity: 0 }}
                    animate={{ rotate: 0, scale: 1, opacity: 1 }}
                    exit={{ rotate: expanded ? 90 : -90, scale: 0.5, opacity: 0 }}
                    transition={animate ? HOVER_SPRING : { duration: 0 }}
                    className="grid place-items-center"
                  >
                    {expanded ? <ArrowUp className="size-4" strokeWidth={2.4} /> : (menuIcon ?? <LayoutGrid className="size-4" />)}
                  </motion.span>
                </AnimatePresence>
              </motion.button>
            </>
          )}
        </div>
      </motion.div>

      {/* menu popover */}
      <AnimatePresence>
        {menuOpen && renderMenu && !expanded && (
          <motion.div
            role="menu"
            aria-label={menuLabel}
            initial={{ opacity: 0, scale: 0.96, y: position === "top" ? -6 : 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: position === "top" ? -4 : 4 }}
            transition={{ duration: animate ? 0.16 : 0, ease: [0.22, 1, 0.36, 1] }}
            className={cn(
              "absolute right-0 z-50 w-60 rounded-2xl border bg-popover p-1.5 text-popover-foreground shadow-pop",
              position === "top" ? "top-full mt-2 origin-top-right" : "bottom-full mb-2 origin-bottom-right",
            )}
          >
            {renderMenu(() => setMenuOpen(false))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default MessageDock;
