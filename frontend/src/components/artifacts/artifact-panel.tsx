import { useMemo, useState } from "react";
import { Check, ChevronDown, Code, Copy, Download, ExternalLink, Eye, RotateCw, X } from "lucide-react";
import { toast } from "sonner";
import { downloadArtifact, openArtifactInTab } from "@/components/artifacts/artifact-actions";
import { ArtifactFrame } from "@/components/artifacts/artifact-frame";
import { KIND_LABEL, type Artifact } from "@/components/artifacts/artifact-utils";
import { KIND_ICON } from "@/components/artifacts/kind-icon";
import { Markdown } from "@/components/chat/markdown";
import { IconButton } from "@/components/icon-button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCopy } from "@/hooks/use-copy";
import { useIsDark } from "@/hooks/use-is-dark";
import { cn } from "@/lib/utils";
import type { ArtifactTab } from "@/stores/artifacts";

const fenceFor = (code: string) => "`".repeat(Math.max(3, ...[...code.matchAll(/`+/g)].map((m) => m[0].length + 1)));

interface ArtifactPanelProps {
  /** Every artifact in this conversation, oldest first (for the switcher). */
  artifacts: Artifact[];
  active: Artifact;
  tab: ArtifactTab;
  onTabChange: (tab: ArtifactTab) => void;
  onSelect: (artifact: Artifact) => void;
  onClose: () => void;
  className?: string;
}

/** Artifact viewer: Preview | Code, with copy / download / open-in-tab / refresh and a per-chat switcher. */
export function ArtifactPanel({ artifacts, active, tab, onTabChange, onSelect, onClose, className }: ArtifactPanelProps) {
  const [reload, setReload] = useState(0);
  const { copied, copy } = useCopy();
  const dark = useIsDark();
  const Icon = KIND_ICON[active.kind];
  const position = artifacts.findIndex((a) => a.id === active.id);
  const fenced = useMemo(() => {
    const fence = fenceFor(active.code);
    return `${fence}${active.kind === "mermaid" ? "mermaid" : active.kind === "svg" ? "xml" : "html"}\n${active.code}\n${fence}`;
  }, [active.code, active.kind]);

  const title = (
    <span className="flex min-w-0 items-center gap-2">
      <span className="grid size-7 shrink-0 place-items-center rounded-lg border bg-muted/60 text-muted-foreground">
        <Icon className="size-4" />
      </span>
      <span className="min-w-0 text-left">
        <span className="block truncate text-sm font-semibold">{active.title}</span>
        <span className="block truncate text-[11px] text-muted-foreground">
          {KIND_LABEL[active.kind]}
          {artifacts.length > 1 && position !== -1 ? ` · ${position + 1} of ${artifacts.length}` : ""}
        </span>
      </span>
    </span>
  );

  return (
    <section aria-label="Artifact" className={cn("flex h-full min-h-0 flex-col bg-background", className)}>
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3">
        {artifacts.length > 1 ? (
          <DropdownMenu>
            <DropdownMenuTrigger
              className="-ml-1 flex min-w-0 flex-1 items-center gap-1.5 rounded-lg px-1 py-1 transition-colors hover:bg-muted focus-visible:outline-2"
              aria-label="Switch artifact"
            >
              {title}
              <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" collisionPadding={12} className="max-h-80 w-[min(18rem,calc(100vw-1.5rem))] overflow-y-auto">
              <DropdownMenuLabel>Artifacts in this chat</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {artifacts.map((a, i) => {
                const ItemIcon = KIND_ICON[a.kind];
                return (
                  <DropdownMenuItem key={a.id} onSelect={() => onSelect(a)} className={cn(a.id === active.id && "bg-muted")}>
                    <ItemIcon className="text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate">{a.title}</span>
                    <span className="text-[11px] text-muted-foreground tabular-nums">
                      {KIND_LABEL[a.kind]} · {i + 1}
                    </span>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <div className="flex min-w-0 flex-1">{title}</div>
        )}
        <IconButton label="Close panel" side="bottom" onClick={onClose}>
          <X />
        </IconButton>
      </header>

      <Tabs value={tab} onValueChange={(v) => onTabChange(v as ArtifactTab)} className="min-h-0 flex-1 gap-0">
        <div className="flex shrink-0 items-center gap-1 border-b px-3 py-2">
          <TabsList className="h-8">
            <TabsTrigger value="preview" className="px-2.5">
              <Eye /> <span className="sr-only min-[400px]:not-sr-only">Preview</span>
            </TabsTrigger>
            <TabsTrigger value="code" className="px-2.5">
              <Code /> <span className="sr-only min-[400px]:not-sr-only">Code</span>
            </TabsTrigger>
          </TabsList>
          <div className="ml-auto flex items-center gap-0.5">
            <IconButton label="Refresh preview" side="bottom" onClick={() => { setReload((n) => n + 1); onTabChange("preview"); }}>
              <RotateCw />
            </IconButton>
            <IconButton label={copied ? "Copied" : "Copy code"} side="bottom" onClick={() => void copy(active.code)}>
              {copied ? <Check /> : <Copy />}
            </IconButton>
            <IconButton label="Download" side="bottom" onClick={() => downloadArtifact(active)}>
              <Download />
            </IconButton>
            <IconButton
              label="Open in new tab"
              side="bottom"
              onClick={() => {
                if (!openArtifactInTab(active, dark)) toast.error("Your browser blocked the new tab.");
              }}
            >
              <ExternalLink />
            </IconButton>
          </div>
        </div>
        <TabsContent value="preview" className="relative min-h-0 bg-muted/40">
          <ArtifactFrame key={`${active.id}:${reload}`} artifact={active} className="absolute inset-0" />
        </TabsContent>
        <TabsContent value="code" className="scrollbar-thin min-h-0 overflow-auto p-3">
          <Markdown text={fenced} artifactActions={false} className="text-base" />
        </TabsContent>
      </Tabs>
    </section>
  );
}
