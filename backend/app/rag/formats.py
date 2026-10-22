"""Supported upload types: extension → MIME type, plus a light magic-byte sniff."""
from __future__ import annotations

import zipfile
from pathlib import Path

MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".json": "application/json",
    ".html": "text/html",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
SUPPORTED_EXTENSIONS = tuple(MIME_TYPES)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
TEXT_EXTENSIONS = (".txt", ".md", ".csv", ".json", ".html")

_ZIP = b"PK\x03\x04"
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")

# .docx/.xlsx are zip packages that python-docx/openpyxl inflate fully into memory: a few-MB "zip bomb" upload
# could otherwise expand to many GB and take the whole backend down. Python's zipfile never yields more than an
# entry's declared size, so checking the declared sizes up front is enough.
MAX_ZIP_EXPANDED_BYTES = 300 * 1024 * 1024
MAX_ZIP_ENTRIES = 20_000
ZIP_BOMB_MESSAGE = "This file expands to far more data than a real document would, so it was not opened"


def mime_for(ext: str) -> str:
    return MIME_TYPES.get(ext.lower(), "application/octet-stream")


def zip_too_large(path: Path) -> bool:
    """True when a zip package (docx/xlsx) declares more entries or uncompressed bytes than the limits allow.

    Files that aren't valid zips return False: the format's own parser reports them as unreadable."""
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
    return len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_ZIP_EXPANDED_BYTES


def sniff_ok(ext: str, head: bytes) -> bool:
    """True when the first bytes of the file plausibly match its extension."""
    ext = ext.lower()
    if ext == ".pdf":
        return b"%PDF-" in head[:1024]
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext in (".docx", ".xlsx"):
        return head.startswith(_ZIP)
    if ext == ".xls":  # legacy BIFF (OLE) — some exporters write HTML/XML with an .xls name
        return head.startswith(_OLE) or head.lstrip()[:1] == b"<"
    if ext in TEXT_EXTENSIONS:
        return head.startswith(_UTF16_BOMS) or b"\x00" not in head
    return False
