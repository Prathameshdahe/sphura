import { useMemo } from "react";
import { MERMAID_CANVAS, buildSrcDoc, type Artifact } from "@/components/artifacts/artifact-utils";
import { useIsDark } from "@/hooks/use-is-dark";
import { cn } from "@/lib/utils";

/** Sandboxed live preview: scripts run in an opaque origin (no cookies, no access to Sphura). */
export function ArtifactFrame({ artifact, className }: { artifact: Pick<Artifact, "kind" | "code" | "title">; className?: string }) {
  const dark = useIsDark();
  const { kind, code } = artifact;
  const srcDoc = useMemo(() => buildSrcDoc({ kind, code }, dark), [kind, code, dark]);
  const canvas = kind === "mermaid" ? (dark ? MERMAID_CANVAS.dark : MERMAID_CANVAS.light) : "#ffffff";
  return (
    <iframe
      title={`${artifact.title} preview`}
      sandbox="allow-scripts"
      srcDoc={srcDoc}
      referrerPolicy="no-referrer"
      className={cn("block h-full w-full border-0", className)}
      style={{ background: canvas, colorScheme: kind === "mermaid" && dark ? "dark" : "light" }}
    />
  );
}
