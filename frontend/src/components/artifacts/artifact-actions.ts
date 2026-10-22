import { downloadFile, standalonePage, type Artifact } from "@/components/artifacts/artifact-utils";

export function downloadArtifact(a: Artifact): void {
  const file = downloadFile(a);
  const url = URL.createObjectURL(new Blob([file.body], { type: `${file.type};charset=utf-8` }));
  const link = document.createElement("a");
  link.href = url;
  link.download = file.name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/** Opens a standalone page whose only content is the same sandboxed iframe. */
export function openArtifactInTab(a: Artifact, dark: boolean): boolean {
  const url = URL.createObjectURL(new Blob([standalonePage(a, dark)], { type: "text/html;charset=utf-8" }));
  // No "noopener" feature: with it window.open() always returns null, so a blocked popup looked like success.
  // The page holds no script of its own (only the sandboxed iframe); the opener link is dropped anyway.
  const win = window.open(url, "_blank");
  if (win) win.opener = null;
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return !!win;
}
