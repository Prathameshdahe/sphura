import { File, FileCode, FileImage, FileSpreadsheet, FileText } from "lucide-react";
import { fileKind, type FileKind } from "@/lib/files";
import { cn } from "@/lib/utils";

/* Tints come from the theme tokens so both themes follow the palette:
   PDF danger · sheet success green · doc warning · image chart-5 · code brand. */
const FILE_STYLE: Record<FileKind, { icon: typeof File; cls: string; label: string }> = {
  pdf: { icon: FileText, cls: "bg-danger/12 text-danger", label: "PDF" },
  image: { icon: FileImage, cls: "bg-chart-5/14 text-chart-5", label: "Image" },
  sheet: { icon: FileSpreadsheet, cls: "bg-success/12 text-success", label: "Sheet" },
  code: { icon: FileCode, cls: "bg-brand/12 text-brand", label: "Code" },
  text: { icon: FileText, cls: "bg-warning/14 text-warning", label: "Doc" },
  other: { icon: File, cls: "bg-muted text-muted-foreground", label: "File" },
};

export function FileIcon({ name, mime, size = "md", className }: { name: string; mime?: string; size?: "sm" | "md" | "lg"; className?: string }) {
  const s = FILE_STYLE[fileKind(name, mime)];
  const Icon = s.icon;
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center rounded-lg",
        size === "sm" && "size-7 [&_svg]:size-3.5",
        size === "md" && "size-9 [&_svg]:size-4",
        size === "lg" && "size-11 [&_svg]:size-5",
        s.cls,
        className,
      )}
      aria-hidden
    >
      <Icon />
    </span>
  );
}
