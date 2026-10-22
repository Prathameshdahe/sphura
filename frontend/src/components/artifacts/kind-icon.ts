import { FileCode, Image as ImageIcon, Workflow } from "lucide-react";
import type { ArtifactKind } from "@/components/artifacts/artifact-utils";

export const KIND_ICON: Record<ArtifactKind, typeof FileCode> = { html: FileCode, svg: ImageIcon, mermaid: Workflow };
