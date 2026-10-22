"""OCR chain: local RapidOCR (if installed) → Gemini vision (OpenAI-compatible API) → Windows' built-in OCR → none.

RapidOCR has no wheels for Python 3.13, so on a keyless Windows machine the built-in Windows.Media.Ocr engine
(driven through Windows PowerShell, nothing to install) is what reads images and scanned pages.
Set SPHURA_WINDOWS_OCR=0 to turn it off.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from app.core.config import settings

log = logging.getLogger("sphura.rag.ocr")

GEMINI_OCR_MODEL = "gemini-3.8-flash"  # keep in sync with the Gemini flash entry in app/llm/catalog.py
OCR_PROMPT = (
    "Transcribe ALL text in this image faithfully and completely, in natural reading order. "
    "Preserve headings (as Markdown #), lists and tables (as Markdown tables). "
    "Do not summarise, translate, or add commentary. If the image contains no text, reply with nothing."
)
_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n(.*?)\n```$", re.S)

_rapid_lock = threading.Lock()
_rapid_engine: object | None = None
_rapid_checked = False


def _rapidocr():
    """Lazily import RapidOCR; returns None when it is not installed (e.g. Python 3.13)."""
    global _rapid_engine, _rapid_checked
    with _rapid_lock:
        if not _rapid_checked:
            _rapid_checked = True
            try:
                from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]

                _rapid_engine = RapidOCR()
                log.info("OCR engine: rapidocr_onnxruntime")
            except Exception as exc:  # noqa: BLE001 — optional dependency
                log.info("rapidocr unavailable (%s); falling back to Gemini vision / Windows OCR",
                         type(exc).__name__)
        return _rapid_engine


# ── Windows built-in OCR (Windows.Media.Ocr through Windows PowerShell 5.1) ──
WINDOWS_MAX_DIM = 10_000   # Windows.Media.Ocr.OcrEngine.MaxImageDimension
WINDOWS_MIN_DIM = 800      # small images are upscaled: the engine misses text under ~10 px high
WINDOWS_BATCH = 12         # images per PowerShell process
_PAGE_MARK = "<<<sphura-ocr-page>>>"
# `$paths` is prepended by _run_windows. Prints each image's lines, then _PAGE_MARK on its own line.
_WINDOWS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$out = New-Object System.IO.StreamWriter([Console]::OpenStandardOutput(), (New-Object System.Text.UTF8Encoding $false))
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $null = $task.Wait(-1)
    $task.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) {
    $lang = New-Object Windows.Globalization.Language 'en-US'
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
}
if ($null -eq $engine) { [Console]::Error.WriteLine('No OCR language is installed'); exit 3 }
foreach ($path in $paths) {
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        try {
            $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            foreach ($line in $result.Lines) { $out.WriteLine($line.Text) }
        } finally { $stream.Dispose() }
    } catch { [Console]::Error.WriteLine($_.Exception.Message) }
    $out.WriteLine('<<<sphura-ocr-page>>>')
}
$out.Flush()
"""

_win_lock = threading.Lock()
_win_ok: bool | None = None


def _windows_enabled() -> bool:
    flag = os.environ.get("SPHURA_WINDOWS_OCR", "1").strip().lower()
    return sys.platform == "win32" and flag not in ("0", "false", "no", "off")


def _powershell() -> str | None:
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    builtin = root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(builtin) if builtin.is_file() else shutil.which("powershell")


def _run_windows(paths: list[str], timeout: float) -> list[str] | None:
    """Text per image file, or None when PowerShell / the WinRT OCR engine is unusable."""
    exe = _powershell()
    if exe is None:
        return None
    literal = ", ".join("'" + p.replace("'", "''") + "'" for p in paths)
    script = f"$paths = @({literal})\n{_WINDOWS_SCRIPT}"
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")  # not subject to execution policy
    try:
        proc = subprocess.run(  # noqa: S603 — fixed executable and script; the paths are our own temp files
            [exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("Windows OCR did not run: %s", type(exc).__name__)
        return None
    if proc.returncode != 0:
        log.warning("Windows OCR unavailable (exit %s): %s", proc.returncode,
                    proc.stderr.decode("utf-8", "replace").strip()[:300])
        return None
    pages = proc.stdout.decode("utf-8-sig", "replace").replace("\r\n", "\n").split(_PAGE_MARK + "\n")
    return [(pages[i] if i < len(pages) else "").strip() for i in range(len(paths))]


def _windows_available() -> bool:
    """Windows OCR is enabled and works on this machine (probed once, ~0.5 s)."""
    global _win_ok
    if not _windows_enabled():
        return False
    with _win_lock:
        if _win_ok is None:
            _win_ok = _run_windows([], timeout=30.0) is not None
            log.info("OCR engine: Windows.Media.Ocr %s", "available" if _win_ok else "unavailable")
        return _win_ok


def _png_for_windows(image: bytes) -> bytes:
    """A PNG the WinRT decoder accepts, within the engine's size limits."""
    from PIL import Image

    with Image.open(io.BytesIO(image)) as img:
        rgb = img.convert("RGB")
    longest = max(rgb.size)
    if longest > WINDOWS_MAX_DIM:
        scale = WINDOWS_MAX_DIM / longest
    elif longest < WINDOWS_MIN_DIM:
        scale = min(3.0, WINDOWS_MIN_DIM / max(longest, 1))
    else:
        scale = 1.0
    if scale != 1.0:
        size = (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale)))
        rgb = rgb.resize(size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    rgb.save(buf, "PNG")
    return buf.getvalue()


def _windows_transcribe_many(images: list[bytes]) -> list[str]:
    texts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="sphura-ocr-") as tmp:
        for start in range(0, len(images), WINDOWS_BATCH):
            batch = images[start:start + WINDOWS_BATCH]
            paths: list[str] = []
            for i, image in enumerate(batch):
                path = Path(tmp) / f"page-{start + i}.png"
                try:
                    path.write_bytes(_png_for_windows(image))
                except Exception as exc:  # noqa: BLE001 — an undecodable image just yields no text
                    log.warning("OCR could not decode an image: %s", exc)
                    path.write_bytes(b"")
                paths.append(str(path))
            texts.extend(_run_windows(paths, timeout=30.0 + 5.0 * len(paths)) or [""] * len(paths))
    return texts


# ── chain ────────────────────────────────────────────────────────────────────
def engine_name() -> str | None:
    if _rapidocr() is not None:
        return "rapidocr"
    if settings.gemini_api_key:
        return "gemini"
    if _windows_available():
        return "windows"
    return None


def available() -> bool:
    return engine_name() is not None


def _rapid_transcribe(image: bytes) -> str:
    result, _elapsed = _rapidocr()(image)  # type: ignore[misc]
    return "\n".join(str(item[1]) for item in (result or []) if len(item) > 1)


def _gemini_transcribe(image: bytes, mime: str) -> str:
    data_url = f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"
    body = {
        "model": GEMINI_OCR_MODEL,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": OCR_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
    }
    url = settings.gemini_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.gemini_api_key}"}
    for attempt in range(3):
        resp = httpx.post(url, json=body, headers=headers, timeout=90)
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(2 * (attempt + 1))
            continue
        resp.raise_for_status()
        text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
        match = _FENCE_RE.match(text)
        return match.group(1).strip() if match else text
    return ""


def transcribe(image: bytes, mime: str = "image/png") -> str:
    """OCR one image. Returns "" when no engine is available or the call fails."""
    try:
        if _rapidocr() is not None:
            return _rapid_transcribe(image)
        if settings.gemini_api_key:
            try:
                return _gemini_transcribe(image, mime)
            except Exception as exc:  # noqa: BLE001 — quota / network: fall back to the local engine
                if not _windows_available():
                    raise
                log.warning("Gemini OCR failed (%s); using Windows OCR", exc)
        if _windows_available():
            return _windows_transcribe_many([image])[0]
    except Exception as exc:  # noqa: BLE001 — OCR must never crash ingestion
        log.warning("OCR failed: %s", exc)
    return ""


def transcribe_many(images: list[bytes], mime: str = "image/png", workers: int = 4) -> list[str]:
    """OCR several images; remote calls run in parallel, local OCR stays sequential."""
    if not images:
        return []
    if _rapidocr() is None and not settings.gemini_api_key and _windows_available():
        try:
            return _windows_transcribe_many(images)  # one PowerShell process per batch, not per page
        except Exception as exc:  # noqa: BLE001 — OCR must never crash ingestion
            log.warning("OCR failed: %s", exc)
            return [""] * len(images)
    if _rapidocr() is not None or len(images) == 1:
        return [transcribe(img, mime) for img in images]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sphura-ocr") as pool:
        return list(pool.map(lambda img: transcribe(img, mime), images))
