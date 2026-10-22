"""Regressions from the end-to-end demo run: flaky DuckDuckGo answers, bot-challenge pages and image OCR on
Python 3.13 without a Gemini key."""
from __future__ import annotations

import asyncio
import base64
import subprocess
import sys
from pathlib import Path

import pytest

from app.rag import ocr
from app.rag.parsers import parse_file
from app.tools import web
from tests.test_rag_api import _upload, _wait
from tests.test_rag_fixtures import make_png, make_scanned_pdf



# ── web search: every flaky ddgs outcome is retried ──────────────────────────
@pytest.fixture
def ddg(monkeypatch):
    monkeypatch.setattr(web, "DDG_RETRY_DELAY_S", 0)
    monkeypatch.setattr(web.settings, "tavily_api_key", "")
    calls: list[str] = []

    def install(outcomes):
        def fake(query, max_results):
            calls.append(query)
            outcome = outcomes[min(len(calls), len(outcomes)) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(web, "_ddg_sync", fake)
        return calls

    return install


HIT = [{"title": "T", "href": "https://example.org/a", "body": "snippet"}]


def test_engine_errors_are_retried_not_reported_at_once(ddg):
    # ddgs re-raises the last engine's error (e.g. a refused connection) when no engine answered
    calls = ddg([RuntimeError("ConnectError: tcp connect error (os error 10061)"), HIT])
    results = asyncio.run(web.web_search("population of Pune"))
    assert len(calls) == 2 and [r.url for r in results] == ["https://example.org/a"] and results.error is None


def test_three_attempts_before_giving_up(ddg):
    calls = ddg([RuntimeError("No results found."), RuntimeError("No results found."), HIT])
    assert web.DDG_ATTEMPTS >= 3
    assert len(asyncio.run(web.web_search("quantum error correction"))) == 1 and len(calls) == 3

    calls = ddg([RuntimeError("ConnectError: refused")])
    calls.clear()
    results = asyncio.run(web.web_search("anything"))
    assert len(calls) == web.DDG_ATTEMPTS and results.error == "Web search is unavailable right now"


def test_empty_list_is_retried(ddg):
    calls = ddg([[], [{"title": "x", "href": "ftp://not-http"}], HIT])
    results = asyncio.run(web.web_search("protein folding"))
    assert len(calls) == 3 and len(results) == 1


# ── bot-challenge pages are not content ──────────────────────────────────────


def test_bot_challenge_pages_are_not_content():
    assert web.is_bot_challenge("Checking your browser", "Checking your browser before accessing "
                                "pmc.ncbi.nlm.nih.gov ... Click here if you are not automatically redirected.")
    assert web.is_bot_challenge("Just a moment...", "Enable JavaScript and cookies to continue")
    article = "Access denied errors happen when a server refuses a request. " * 20
    assert not web.is_bot_challenge("HTTP 403 explained", article)  # a real page about the topic


def test_read_page_reports_a_challenge_as_an_error(monkeypatch):
    async def fake_fetch(url):
        return url, b"<html><title>Just a moment...</title><body>Checking your browser</body></html>", "text/html"

    monkeypatch.setattr(web, "_fetch", fake_fetch)
    monkeypatch.setattr(web, "_extract", lambda body, url, ctype: ("Just a moment...", "Checking your browser"))
    page = asyncio.run(web.read_page("https://pmc.ncbi.nlm.nih.gov/articles/PMC1/"))
    assert not page.ok and page.error == "The site blocked automated reading"




# ── OCR without RapidOCR (Python 3.13) or a Gemini key: Windows' built-in engine ──
@pytest.fixture
def fake_windows_ocr(monkeypatch):
    """Windows OCR as seen from Python: a PowerShell process that prints each image's lines + a page mark."""
    scripts: list[str] = []

    def fake_run(args, capture_output, timeout, creationflags=0):
        script = base64.b64decode(args[args.index("-EncodedCommand") + 1]).decode("utf-16-le")
        scripts.append(script)
        pages = script.split("\n", 1)[0].count(".png")
        out = "".join("Invoice total: 4,250 rupees\r\n<<<sphura-ocr-page>>>\r\n" for _ in range(pages))
        return subprocess.CompletedProcess(args, 0, stdout=out.encode("utf-8"), stderr=b"")

    monkeypatch.setattr(ocr, "_rapidocr", lambda: None)
    monkeypatch.setattr(ocr, "_windows_enabled", lambda: True)
    monkeypatch.setattr(ocr, "_powershell", lambda: "powershell.exe")
    monkeypatch.setattr(ocr, "_win_ok", None)
    monkeypatch.setattr(ocr.subprocess, "run", fake_run)
    return scripts


def test_images_and_scans_use_windows_ocr_without_gemini(tmp_path: Path, fake_windows_ocr) -> None:
    assert ocr.engine_name() == "windows"
    image = parse_file(make_png(tmp_path / "photo.png"), "photo.png")
    assert image.ocr_used and not image.ocr_needed and "4,250 rupees" in image.blocks[0].text
    scan = parse_file(make_scanned_pdf(tmp_path / "scan.pdf"), "scan.pdf")
    assert scan.ocr_used and not scan.ocr_needed
    assert [(b.text, b.page) for b in scan.blocks] == [("Invoice total: 4,250 rupees", 1)]
    assert len(fake_windows_ocr) == 3  # probe + one process per document


def test_windows_ocr_off_means_no_engine(monkeypatch) -> None:
    monkeypatch.setattr(ocr, "_rapidocr", lambda: None)
    monkeypatch.setenv("SPHURA_WINDOWS_OCR", "0")
    assert not ocr.available() and ocr.transcribe(b"png") == ""


@pytest.mark.skipif(sys.platform != "win32", reason="Windows.Media.Ocr only exists on Windows")
def test_real_windows_ocr_reads_an_uploaded_image(client, user, tmp_path: Path, monkeypatch) -> None:
    """The tester's repro: a PNG with 'Invoice total: 4,250 rupees' must become a ready, OCR'd document."""
    from PIL import Image, ImageDraw, ImageFont

    font_path = Path(r"C:\Windows\Fonts\arial.ttf")
    if not font_path.is_file():
        pytest.skip("Arial is not installed")
    monkeypatch.setenv("SPHURA_WINDOWS_OCR", "1")
    monkeypatch.setattr(ocr, "_win_ok", None)
    if not ocr.available() or ocr.engine_name() != "windows":
        pytest.skip("Windows OCR is not available on this machine")
    img = Image.new("RGB", (900, 200), "white")
    ImageDraw.Draw(img).text((30, 60), "Invoice total: 4,250 rupees", fill="black",
                             font=ImageFont.truetype(str(font_path), 40))
    img.save(tmp_path / "invoice.png")
    r = _upload(client, user, tmp_path / "invoice.png")
    assert r.status_code == 200, r.text
    info = _wait(client, user, r.json()["id"])
    assert info["status"] == "ready" and info["ocrUsed"] is True and info["chunkCount"] >= 1, info
