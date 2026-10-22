// Display metadata for the finance intent router (FINANCE_PLAN §3) and the other trained classifiers.
import {
  Ban,
  BookOpenText,
  ChartCandlestick,
  FileText,
  Frown,
  Meh,
  Scale,
  Smile,
  Tag,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export interface LabelMeta {
  icon: LucideIcon;
  title: string;
  /** What the agent does when the router picks this label. */
  action: string;
}

const INTENTS: Record<string, LabelMeta> = {
  spending: { icon: Wallet, title: "Spending", action: "Runs the statement analytics and the transaction categoriser" },
  documents: { icon: FileText, title: "Documents", action: "Searches your uploaded documents with page citations" },
  market: { icon: ChartCandlestick, title: "Market", action: "Fetches quotes, history and finance news" },
  explain: { icon: BookOpenText, title: "Explain", action: "Explains the concept with calculator tools" },
  advice: { icon: Scale, title: "Advice", action: "Answers with education and a not-an-adviser note" },
  out_of_scope: { icon: Ban, title: "Out of scope", action: "Politely declines — no model call" },
  positive: { icon: Smile, title: "Positive", action: "Upbeat headline" },
  neutral: { icon: Meh, title: "Neutral", action: "Factual headline" },
  negative: { icon: Frown, title: "Negative", action: "Downbeat headline" },
};

const humanise = (label: string) => label.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function labelMeta(label: string): LabelMeta {
  return INTENTS[label] ?? { icon: Tag, title: humanise(label), action: "Predicted class" };
}

/** Confidence as "94%" (the router emits 0..1). */
export const confidencePct = (x: number) => `${Math.round(Math.max(0, Math.min(1, x)) * 100)}%`;
