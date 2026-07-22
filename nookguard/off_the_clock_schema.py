"""Off the Clock content schema + legacy-component ban (Commit 9). The real,
approved structure of this section's page bodies -- confirmed by reading all
10 real production files in site/src/content/blog/ before writing this
schema, not assumed: every `photo-single` block contains exactly 1 image,
every `photo-strip` block contains exactly 3 images, with zero exceptions
across all 10 files, and (per the 2026-07-18 layout retool documented in the
main project's CLAUDE.md) no page uses the retired `polaroid inset`/
`float-left` markup anymore -- also confirmed absent in all 10 files, not
assumed. Hook H009: 'Page adds legacy raw media component -> Fail content
lint' is this module's ban check, made real rather than left as a prose
rule. Regression fixture (docs/nookguard/SPEC.md Appendix I): 'Off the Clock
page with 1, 4, or 5 photo strips instead of approved structure -> FAIL'."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

OFF_THE_CLOCK_CATEGORIES = {"Life outside the nook", "Behind the nook"}

PHOTO_SINGLE_EXPECTED_COUNT = 1
PHOTO_STRIP_EXPECTED_COUNT = 3

# The retired layout this section moved away from 2026-07-18 (main project
# CLAUDE.md's "Off the Clock: layout retool..." entry) -- a page still using
# either pattern is running the OLD component, banned by hook H009.
LEGACY_PATTERNS = [
    "polaroid inset",
    "polaroid.inset",
    "float-left",
]

_BLOCK_RE = re.compile(r'<div class="(photo-single|photo-strip)">(.*?)</div>', re.DOTALL)
_FIGURE_RE = re.compile(r"<figure\b")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_CATEGORY_FIELD_RE = re.compile(r'^category:\s*"([^"]*)"', re.MULTILINE)


@dataclass
class BlockReport:
    block_type: str
    image_count: int
    expected_count: int
    passed: bool


@dataclass
class ContentLintReport:
    passed: bool
    category_ok: bool
    blocks: list[BlockReport] = field(default_factory=list)
    legacy_pattern_findings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def split_frontmatter(file_text: str) -> tuple[str, str]:
    """Minimal, dependency-free YAML-frontmatter split -- deliberately not
    pulling in a full YAML parser for a single field extraction. Returns
    (frontmatter_text, body_text). Raises ValueError if no frontmatter
    delimiter is found, since a page with no frontmatter at all is itself
    a real problem worth surfacing, not silently treating as bodyless."""
    match = _FRONTMATTER_RE.match(file_text)
    if not match:
        raise ValueError("No YAML frontmatter block found (expected leading '---' ... '---')")
    return match.group(1), match.group(2)


def extract_category(frontmatter_text: str) -> str | None:
    match = _CATEGORY_FIELD_RE.search(frontmatter_text)
    return match.group(1) if match else None


def lint_off_the_clock_page(markdown_body: str, category: str) -> ContentLintReport:
    reasons: list[str] = []

    category_ok = category in OFF_THE_CLOCK_CATEGORIES
    if not category_ok:
        reasons.append(f"Category '{category}' is not a recognized Off the Clock category "
                        f"({sorted(OFF_THE_CLOCK_CATEGORIES)})")

    legacy_findings = [pattern for pattern in LEGACY_PATTERNS if pattern in markdown_body]
    for pattern in legacy_findings:
        reasons.append(f"Legacy layout pattern found: '{pattern}' -- retired 2026-07-18, "
                        "use photo-single/photo-strip instead")

    blocks: list[BlockReport] = []
    for block_type, block_body in _BLOCK_RE.findall(markdown_body):
        expected = PHOTO_SINGLE_EXPECTED_COUNT if block_type == "photo-single" else PHOTO_STRIP_EXPECTED_COUNT
        image_count = len(_FIGURE_RE.findall(block_body))
        passed = image_count == expected
        blocks.append(BlockReport(block_type, image_count, expected, passed))
        if not passed:
            reasons.append(f"{block_type} block has {image_count} image(s), expected exactly {expected}")

    all_blocks_pass = all(b.passed for b in blocks)
    overall_pass = category_ok and not legacy_findings and all_blocks_pass

    return ContentLintReport(
        passed=overall_pass, category_ok=category_ok, blocks=blocks,
        legacy_pattern_findings=legacy_findings, reasons=reasons,
    )


def lint_off_the_clock_file(path: str) -> ContentLintReport:
    """Convenience wrapper: read a real .md file, split frontmatter, extract
    category, and lint. Used by both `mediactl content-lint` and the layout
    tests that run this against every real production file."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    frontmatter_text, body = split_frontmatter(text)
    category = extract_category(frontmatter_text) or ""
    return lint_off_the_clock_page(body, category)
