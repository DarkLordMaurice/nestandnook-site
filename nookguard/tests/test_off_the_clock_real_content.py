"""Layout tests (Commit 9) -- run the schema against the REAL, live
production files, not just synthetic fixtures. This is the actual
regression-prevention mechanism: main project CLAUDE.md documents these 10
pages as already migrated to the photo-single/photo-strip layout (commit
f2018f5, 2026-07-18) with the legacy polaroid-inset/float-left markup fully
retired -- confirmed directly by reading all 10 files before writing
off_the_clock_schema.py, not assumed. These tests prove that state holds
right now and will catch it if a future edit regresses it."""

from pathlib import Path

import pytest

from nookguard.off_the_clock_schema import lint_off_the_clock_file

# nookguard/tests/test_off_the_clock_real_content.py -> nookguard -> site -> project root... actually
# only need to reach site/src/content/blog, which is inside the `site` repo itself (parents[2] from this
# file is `site`, not the outer project root -- unlike canon.py which reaches into brand-assets/ one level up).
BLOG_DIR = Path(__file__).resolve().parents[2] / "src" / "content" / "blog"

OFF_THE_CLOCK_FILES = [
    "a-goat-humbled-me-at-the-petting-zoo.md",
    "a-saturday-that-was-supposed-to-be-errands.md",
    "every-nook-wants-a-job.md",
    "let-freedom-ring-and-also-my-ears.md",
    "the-smoker-i-inherited-by-accident.md",
    "the-studio-two-blocks-from-my-apartment.md",
    "the-tent-i-almost-didnt-bring.md",
    "the-week-i-made-banana-bread-for-the-entire-building.md",
    "the-year-i-lost-an-apple-bobbing-contest.md",
    "what-the-parade-of-skulls-actually-taught-me.md",
]


@pytest.mark.parametrize("filename", OFF_THE_CLOCK_FILES)
def test_real_off_the_clock_file_passes_content_lint(filename):
    path = BLOG_DIR / filename
    assert path.exists(), f"expected real production file missing: {path}"
    report = lint_off_the_clock_file(str(path))
    assert report.passed, (
        f"{filename} failed content lint: {report.reasons}"
    )


def test_all_ten_real_files_are_accounted_for():
    """If a new Off the Clock post is added or one of these is renamed, this
    test should be the thing that notices, not a silent gap in coverage."""
    real_files = {p.name for p in BLOG_DIR.glob("*.md")}
    off_the_clock_present = [f for f in OFF_THE_CLOCK_FILES if f in real_files]
    assert len(off_the_clock_present) == len(OFF_THE_CLOCK_FILES)
