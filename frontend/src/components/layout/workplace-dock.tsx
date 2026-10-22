import { useNavigate } from "react-router-dom";
import { glyph } from "@/components/icons/glyphs";
import { MessageDock, type DockCharacter } from "@/components/ui/message-dock";
import type { NewChatState } from "@/lib/feature-types";

/** Finance specialists: each opens a new chat with your question (the agent routes it to the right tools). */
const SPECIALISTS: DockCharacter[] = [
  { id: "budget", name: "Budget coach", icon: glyph("piggy"), tint: "var(--success)", placeholder: "Ask the budget coach…" },
  { id: "tax", name: "Tax helper", icon: glyph("receipt"), tint: "var(--accent-ink)", placeholder: "Ask the tax helper…" },
  { id: "loans", name: "Loans & EMI", icon: glyph("house-coin"), tint: "var(--chart-3)", placeholder: "Ask about a loan or EMI…" },
  { id: "markets", name: "Markets", icon: glyph("markets"), tint: "var(--chart-5)", placeholder: "Ask about a stock or index…" },
  { id: "documents", name: "Documents", icon: glyph("doc-search"), tint: "var(--chart-4)", placeholder: "Ask about your documents…" },
];

/**
 * The specialist dock on the chat home screen (a MessageDock): pick a specialist, type the question in the pill
 * that opens, and it starts a new chat with that question already asked.
 */
export function SpecialistDock({ className }: { className?: string }) {
  const navigate = useNavigate();
  return (
    <MessageDock
      className={className}
      characters={SPECIALISTS}
      label="Ask a specialist"
      showSparkleButton={false}
      showMenuButton={false}
      position="bottom"
      expandedWidth={440}
      onMessageSend={(text, c) =>
        navigate("/", {
          state: {
            fresh: true,
            prompt: text,
            autoSend: true,
            ...(c.id === "markets" ? { webSearch: true } : {}),
          } satisfies NewChatState,
        })
      }
    />
  );
}
