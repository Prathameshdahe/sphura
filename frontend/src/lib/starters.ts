import type { ComponentType } from "react";
import { glyph } from "@/components/icons/glyphs";

export type StarterId = "statement" | "explain" | "stock" | "document";

export interface Starter {
  id: StarterId;
  icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  title: string;
  body: string;
  /** Sent as the first message (statement / document starters decide at click time). */
  prompt?: string;
}

/** The four symmetric Home starter cards (FINANCE_PLAN §4). */
export const STARTERS: Starter[] = [
  {
    id: "statement",
    icon: glyph("statement"),
    title: "Analyse my statement",
    body: "Where the money goes, recurring charges and what you could save — from a bank statement.",
    prompt: "Where did my money go last month? Flag any subscriptions or recurring charges, and tell me what I could cut.",
  },
  {
    id: "explain",
    icon: glyph("bulb"),
    title: "Explain a concept",
    body: "SIP vs lump sum, EMI maths, old vs new tax regime, what EBITDA means.",
    prompt: "Explain what a SIP is, and how a ₹5,000 monthly SIP at 12% grows over 10 years.",
  },
  {
    id: "stock",
    icon: glyph("candles"),
    title: "Check a stock",
    body: "A delayed quote, the trend and the latest news with sentiment — educational, never advice.",
    prompt: "What is TCS trading at today, and what is the latest news about it?",
  },
  {
    id: "document",
    icon: glyph("doc-search"),
    title: "Ask about a document",
    body: "Balance sheets, P&L, invoices and policies — answered with page citations.",
    prompt: "What are the key figures in this document, and is anything unusual?",
  },
];
