from nookguard.off_the_clock_schema import (
    extract_category,
    lint_off_the_clock_page,
    split_frontmatter,
)

VALID_BODY = """
Some intro text.

<div class="photo-single">
  <figure class="polaroid">
    <img src="/winnie/a.jpg" alt="a" />
  </figure>
</div>

More text.

<div class="photo-strip">
  <figure class="polaroid"><img src="/winnie/b.jpg" alt="b" /></figure>
  <figure class="polaroid"><img src="/winnie/c.jpg" alt="c" /></figure>
  <figure class="polaroid"><img src="/winnie/d.jpg" alt="d" /></figure>
</div>

— Winnie
"""


def test_valid_page_passes():
    report = lint_off_the_clock_page(VALID_BODY, "Life outside the nook")
    assert report.passed is True
    assert report.category_ok is True
    assert report.legacy_pattern_findings == []


def test_photo_strip_with_one_image_fails():
    """Direct regression fixture from SPEC.md Appendix I: '1, 4, or 5 photo
    strips instead of approved structure -> FAIL'."""
    body = VALID_BODY.replace(
        '<div class="photo-strip">\n  <figure class="polaroid"><img src="/winnie/b.jpg" alt="b" /></figure>\n'
        '  <figure class="polaroid"><img src="/winnie/c.jpg" alt="c" /></figure>\n'
        '  <figure class="polaroid"><img src="/winnie/d.jpg" alt="d" /></figure>\n</div>',
        '<div class="photo-strip">\n  <figure class="polaroid"><img src="/winnie/b.jpg" alt="b" /></figure>\n</div>',
    )
    report = lint_off_the_clock_page(body, "Life outside the nook")
    assert report.passed is False
    assert any("photo-strip" in r and "1 image" in r for r in report.reasons)


def test_photo_strip_with_four_images_fails():
    body = VALID_BODY.replace(
        "</figure>\n</div>\n\n— Winnie",
        '</figure>\n  <figure class="polaroid"><img src="/winnie/e.jpg" alt="e" /></figure>\n</div>\n\n— Winnie',
    )
    report = lint_off_the_clock_page(body, "Life outside the nook")
    assert report.passed is False
    strip_reports = [b for b in report.blocks if b.block_type == "photo-strip"]
    assert strip_reports[0].image_count == 4
    assert strip_reports[0].passed is False


def test_photo_strip_with_five_images_fails():
    body = VALID_BODY.replace(
        "</figure>\n</div>\n\n— Winnie",
        '</figure>\n  <figure class="polaroid"><img src="/winnie/e.jpg" alt="e" /></figure>\n'
        '  <figure class="polaroid"><img src="/winnie/f.jpg" alt="f" /></figure>\n</div>\n\n— Winnie',
    )
    report = lint_off_the_clock_page(body, "Life outside the nook")
    strip_reports = [b for b in report.blocks if b.block_type == "photo-strip"]
    assert strip_reports[0].image_count == 5
    assert report.passed is False


def test_photo_single_with_two_images_fails():
    body = VALID_BODY.replace(
        '<div class="photo-single">\n  <figure class="polaroid">\n    <img src="/winnie/a.jpg" alt="a" />\n  </figure>\n</div>',
        '<div class="photo-single">\n  <figure class="polaroid"><img src="/winnie/a.jpg" alt="a" /></figure>\n'
        '  <figure class="polaroid"><img src="/winnie/a2.jpg" alt="a2" /></figure>\n</div>',
    )
    report = lint_off_the_clock_page(body, "Life outside the nook")
    single_reports = [b for b in report.blocks if b.block_type == "photo-single"]
    assert single_reports[0].image_count == 2
    assert report.passed is False


def test_legacy_polaroid_inset_pattern_fails():
    body = VALID_BODY + '\n<figure class="polaroid inset"><img src="/winnie/legacy.jpg" /></figure>'
    report = lint_off_the_clock_page(body, "Life outside the nook")
    assert report.passed is False
    assert "polaroid inset" in report.legacy_pattern_findings


def test_legacy_float_left_pattern_fails():
    body = VALID_BODY + '\n<figure class="polaroid inset float-left"><img src="/winnie/legacy.jpg" /></figure>'
    report = lint_off_the_clock_page(body, "Life outside the nook")
    assert report.passed is False
    assert "float-left" in report.legacy_pattern_findings


def test_unrecognized_category_fails():
    report = lint_off_the_clock_page(VALID_BODY, "Desk fixes")
    assert report.passed is False
    assert report.category_ok is False


def test_behind_the_nook_category_is_valid():
    report = lint_off_the_clock_page(VALID_BODY, "Behind the nook")
    assert report.category_ok is True


def test_page_with_no_blocks_at_all_still_evaluates_category_and_legacy():
    """A page with zero photo-single/photo-strip blocks isn't itself a
    block-count violation (nothing to violate) -- category and legacy
    checks still run independently."""
    report = lint_off_the_clock_page("Just prose, no images at all.", "Life outside the nook")
    assert report.blocks == []
    assert report.passed is True


# ---- split_frontmatter / extract_category ----

def test_split_frontmatter_separates_correctly():
    text = '---\ntitle: "X"\ncategory: "Life outside the nook"\n---\nBody text here.\n'
    fm, body = split_frontmatter(text)
    assert "category:" in fm
    assert body.strip() == "Body text here."


def test_split_frontmatter_raises_without_delimiters():
    import pytest
    with pytest.raises(ValueError):
        split_frontmatter("No frontmatter here at all.")


def test_extract_category_finds_quoted_value():
    fm = 'title: "X"\ncategory: "Behind the nook"\nother: "y"'
    assert extract_category(fm) == "Behind the nook"


def test_extract_category_returns_none_when_absent():
    fm = 'title: "X"\nother: "y"'
    assert extract_category(fm) is None
