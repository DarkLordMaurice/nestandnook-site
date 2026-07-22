"""Real Playwright capture tests (Commit 10). playwright + a real Chromium
binary are confirmed genuinely functional in this environment (a throwaway
script launched chromium and wrote a real screenshot before this module was
written) -- these tests exercise the real browser end to end via file://
URLs instead of mocking the browser boundary, unlike the network-dependent
HF/Anthropic adapter tests elsewhere in this suite."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from nookguard.preview import VIEWPORTS, capture_all_viewports, capture_page_screenshot


def _write_html(html: str) -> str:
    d = Path(tempfile.mkdtemp())
    p = d / "page.html"
    p.write_text(html, encoding="utf-8")
    return p.as_uri()


def test_capture_clean_page_has_no_broken_images_or_errors():
    url = _write_html("<html><body><h1>Hello Nest and Nook</h1></body></html>")
    out = Path(tempfile.mkdtemp()) / "shot.png"
    report = capture_page_screenshot(url, out, viewport_name="desktop")
    assert report.passed is True
    assert report.broken_images == []
    assert report.console_errors == []
    assert report.failed_requests == []
    assert Path(report.screenshot_path).exists()


def test_capture_detects_broken_image():
    url = _write_html('<html><body><img src="does-not-exist.png" width="50" height="50"></body></html>')
    out = Path(tempfile.mkdtemp()) / "shot.png"
    report = capture_page_screenshot(url, out, viewport_name="desktop")
    assert report.passed is False
    assert any("does-not-exist.png" in b for b in report.broken_images)


def test_capture_detects_console_error():
    url = _write_html("<html><body><script>console.error('boom, something broke');</script></body></html>")
    out = Path(tempfile.mkdtemp()) / "shot.png"
    report = capture_page_screenshot(url, out, viewport_name="desktop")
    assert report.passed is False
    assert any("boom" in e for e in report.console_errors)


def test_capture_rejects_unknown_viewport():
    with pytest.raises(ValueError):
        capture_page_screenshot("https://example.invalid/", "/tmp/x.png", viewport_name="tablet")


def test_capture_all_viewports_returns_one_report_per_viewport():
    url = _write_html("<html><body><h1>Hello</h1></body></html>")
    out_dir = tempfile.mkdtemp()
    reports = capture_all_viewports(url, out_dir, "myslug")
    assert set(reports.keys()) == set(VIEWPORTS.keys())
    for name, report in reports.items():
        assert report.viewport_name == name
        assert report.url == url
        assert Path(report.screenshot_path).exists()


def test_capture_all_viewports_honors_explicit_viewport_subset():
    url = _write_html("<html><body><h1>Hello</h1></body></html>")
    out_dir = tempfile.mkdtemp()
    reports = capture_all_viewports(url, out_dir, "myslug", viewports=["desktop"])
    assert set(reports.keys()) == {"desktop"}
