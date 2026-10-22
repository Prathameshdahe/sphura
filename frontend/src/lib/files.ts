export type FileKind = "pdf" | "image" | "sheet" | "code" | "text" | "other";

export function fileKind(name: string, mime = ""): FileKind {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  if (mime.startsWith("image/") || ["png", "jpg", "jpeg", "webp", "gif"].includes(ext)) return "image";
  if (ext === "pdf" || mime === "application/pdf") return "pdf";
  if (["csv", "xlsx", "xls"].includes(ext)) return "sheet";
  if (["json", "html", "htm"].includes(ext)) return "code";
  if (["txt", "md", "docx", "doc"].includes(ext)) return "text";
  return "other";
}

const KIND_LABEL: Record<FileKind, string> = { pdf: "PDF", image: "Image", sheet: "Sheet", code: "Code", text: "Doc", other: "File" };

export function fileTypeLabel(name: string, mime?: string): string {
  const ext = name.split(".").pop();
  return ext && ext !== name ? ext.toUpperCase() : KIND_LABEL[fileKind(name, mime)];
}
