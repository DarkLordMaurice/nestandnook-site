"""Real Playwright page capture (Commit 10). Confirmed working in this
environment before writing this module -- `playwright` 1.60.0 is installed
AND its Chromium binary actually launches and screenshots real content
(verified directly, not assumed: a throwaway script launched chromium,
rendered inline HTML, and wrote a real PNG). This is a stronger footing than
Commit 5/7's adapters, where the real network call itself was unverifiable
in-session -- here the full mechanism is real and tested end to end, not
just up to a mocked boundary.

Section 28's 'Page integration' technical checks this module makes real:
broken image detection (an <img> whose naturalWidth is 0 after load never
actually resolved), console errors, and failed network requests (404s on
page assets) -- all deterministic, code-owned, no model judgment involved."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},  # iPhone 12/13-class viewport
}


@dataclass
class PageCaptureReport:
    url: str
    viewport_name: str
    screenshot_path: str
    broken_images: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)
    passed: bool = True


_BROKEN_IMAGE_JS = """
() => Array.from(document.querySelectorAll('img'))
    .filter(img => img.complete && img.naturalWidth === 0)
    .map(img => img.src)
"""


def capture_page_screenshot(
    url: str,
    output_path: str | Path,
    viewport_name: str = "desktop",
    timeout_ms: int = 15000,
) -> PageCaptureReport:
    if viewport_name not in VIEWPORTS:
        raise ValueError(f"Unknown viewport '{viewport_name}', expected one of {sorted(VIEWPORTS)}")

    from playwright.sync_api import sync_playwright

    console_errors: list[str] = []
    failed_requests: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport=VIEWPORTS[viewport_name])
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("requestfailed", lambda req: failed_requests.append(f"{req.url}: {req.failure}"))
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            broken_images = page.evaluate(_BROKEN_IMAGE_JS)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output_path), full_page=True)
        finally:
            browser.close()

    passed = not broken_images and not console_errors and not failed_requests
    return PageCaptureReport(
        url=url, viewport_name=viewport_name, screenshot_path=str(output_path),
        broken_images=broken_images, console_errors=console_errors,
        failed_requests=failed_requests, passed=passed,
    )


def capture_all_viewports(
    url: str, output_dir: str | Path, slug: str, viewports: Optional[list[str]] = None,
) -> dict[str, PageCaptureReport]:
    """Convenience wrapper: capture every requested viewport (default: all
    of them) for one page, with predictable output filenames."""
    viewports = viewports or list(VIEWPORTS.keys())
    reports = {}
    for name in viewports:
        output_path = Path(output_dir) / f"{slug}-{name}.png"
        reports[name] = capture_page_screenshot(url, output_path, viewport_name=name)
    return reports
