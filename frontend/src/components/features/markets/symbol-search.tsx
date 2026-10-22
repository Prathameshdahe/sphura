import { useEffect, useId, useRef, useState } from "react";
import { LoaderCircle, Search, X } from "lucide-react";
import { useDebounced } from "@/hooks/use-media-query";
import { useSymbolSearch } from "@/lib/feature-api/market";
import type { MarketMatch } from "@/lib/feature-types";
import { cn } from "@/lib/utils";

interface SymbolSearchProps {
  onPick: (match: MarketMatch) => void;
  autoFocus?: boolean;
  className?: string;
}

/** Symbol / company search with a keyboard-navigable result list (GET /api/market/search). Enter on free text uses it as a ticker. */
export function SymbolSearch({ onPick, autoFocus, className }: SymbolSearchProps) {
  const listId = useId();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [rawCursor, setCursor] = useState(0);
  const debounced = useDebounced(text, 220);
  const q = useSymbolSearch(debounced, open);
  const matches = open && debounced.trim().length >= 2 ? (q.data ?? []) : [];
  // Typing resets the cursor (onChange); a shorter result list clamps it, so no effect is needed.
  const cursor = Math.min(rawCursor, Math.max(0, matches.length - 1));
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Click outside closes the list.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("pointerdown", onDown);
    return () => window.removeEventListener("pointerdown", onDown);
  }, [open]);

  const pick = (m: MarketMatch) => {
    onPick(m);
    setText("");
    setOpen(false);
    inputRef.current?.blur();
  };

  const submitFree = () => {
    const raw = text.trim().toUpperCase();
    if (!raw) return;
    pick({ symbol: raw, name: raw, exchange: "" });
  };

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <input
        ref={inputRef}
        type="search"
        value={text}
        role="combobox"
        aria-expanded={open && matches.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && matches[cursor] ? `${listId}-${cursor}` : undefined}
        aria-label="Search a stock, fund or index"
        autoFocus={autoFocus}
        onChange={(e) => {
          setText(e.target.value);
          setCursor(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && matches.length) {
            e.preventDefault();
            setCursor((c) => (c + 1) % matches.length);
          } else if (e.key === "ArrowUp" && matches.length) {
            e.preventDefault();
            setCursor((c) => (c - 1 + matches.length) % matches.length);
          } else if (e.key === "Enter") {
            e.preventDefault();
            if (matches[cursor]) pick(matches[cursor]);
            else submitFree();
          } else if (e.key === "Escape") {
            setOpen(false);
            setText("");
            e.currentTarget.blur();
          }
        }}
        placeholder="Search a stock, fund or index — e.g. TCS, HDFC Bank, NIFTY, AAPL"
        className="h-11 w-full rounded-xl border bg-card pr-10 pl-10 text-sm shadow-xs outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-muted-foreground focus:border-ring/60 focus:ring-3 focus:ring-ring/20 [&::-webkit-search-cancel-button]:hidden"
      />
      <span className="absolute top-1/2 right-3 -translate-y-1/2 text-muted-foreground">
        {q.isFetching ? (
          <LoaderCircle className="size-4 animate-spin" aria-label="Searching" />
        ) : text ? (
          <button type="button" aria-label="Clear" onClick={() => setText("")} className="grid size-6 place-items-center rounded-md hover:text-foreground">
            <X className="size-3.5" />
          </button>
        ) : (
          <kbd className="hidden rounded border px-1 font-mono text-[10px] sm:inline">Enter</kbd>
        )}
      </span>
      {open && debounced.trim().length >= 2 && (matches.length > 0 || q.isError || (q.isFetched && !q.isFetching)) && (
        <ul
          id={listId}
          role="listbox"
          className="absolute inset-x-0 top-full z-30 mt-1.5 max-h-72 origin-top animate-in overflow-y-auto rounded-xl border bg-popover p-1 shadow-pop duration-150 fade-in-0 zoom-in-[0.98]"
        >
          {matches.length === 0 ? (
            <li className="px-3 py-2.5 text-sm text-muted-foreground">
              {q.isError ? "Search is unavailable right now — press Enter to try the text as a ticker." : `No matches for “${debounced.trim()}”. Press Enter to use it as a ticker.`}
            </li>
          ) : (
            matches.map((m, i) => (
              <li
                key={`${m.symbol}-${i}`}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === cursor}
                onMouseEnter={() => setCursor(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(m)}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-100",
                  i === cursor ? "bg-accent text-accent-foreground" : "text-foreground",
                )}
              >
                <span className="min-w-0 flex-1 truncate">{m.name || m.symbol}</span>
                <span className="shrink-0 font-mono text-xs text-muted-foreground">{m.symbol}</span>
                {m.exchange && <span className="hidden shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground sm:inline">{m.exchange}</span>}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
