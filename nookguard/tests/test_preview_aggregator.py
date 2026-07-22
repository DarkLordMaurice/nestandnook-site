"""Preview-QA code aggregator tests (Commit 10) -- mirrors test_aggregator.py's
approach: pure unit tests over the dataclasses/models, no session/network
involved, since aggregate_preview() is deliberately the only place a
PREVIEW_REVIEW_PASS/FAIL decision gets made."""

from __future__ import annotations

import inspect

import pytest

from nookguard.preview import PageCaptureReport
from nookguard.preview_aggregator import aggregate_preview
from nookguard.schemas import PageReviewIssue, PageReviewResult
from nookguard.state_machine import AssetState


def _clean_report(viewport: str = "desktop") -> PageCaptureReport:
    return PageCaptureReport(url="https://nestandnook.org/x/", viewport_name=viewport,
                              screenshot_path="/tmp/x.png")


def _review(issues=None) -> PageReviewResult:
    return PageReviewResult(
        page_url="https://nestandnook.org/x/", viewports_reviewed=["desktop"],
        review_session_id="s1", reviewer_agent_hash="h1", context_bundle_sha256="cb1",
        issues=issues or [],
    )


def test_clean_capture_and_clean_review_yields_pass():
    result = aggregate_preview([_clean_report()], _review())
    assert result.state == AssetState.PREVIEW_REVIEW_PASS


def test_broken_image_in_capture_yields_fail():
    report = PageCaptureReport(url="https://x/", viewport_name="desktop", screenshot_path="/tmp/x.png",
                                broken_images=["https://x/hero.jpg"])
    result = aggregate_preview([report], _review())
    assert result.state == AssetState.PREVIEW_REVIEW_FAIL
    assert "broken image" in result.reasons[0].lower()


def test_console_error_in_capture_yields_fail():
    report = PageCaptureReport(url="https://x/", viewport_name="desktop", screenshot_path="/tmp/x.png",
                                console_errors=["TypeError: x is undefined"])
    result = aggregate_preview([report], _review())
    assert result.state == AssetState.PREVIEW_REVIEW_FAIL


def test_failed_request_in_capture_yields_fail():
    report = PageCaptureReport(url="https://x/", viewport_name="desktop", screenshot_path="/tmp/x.png",
                                failed_requests=["https://x/y.css: net::ERR_FAILED"])
    result = aggregate_preview([report], _review())
    assert result.state == AssetState.PREVIEW_REVIEW_FAIL


def test_critical_reviewer_issue_yields_fail():
    review = _review(issues=[PageReviewIssue(category="overlapping_elements", severity="critical",
                                              description="nav overlaps hero", viewport="mobile")])
    result = aggregate_preview([_clean_report()], review)
    assert result.state == AssetState.PREVIEW_REVIEW_FAIL


def test_major_reviewer_issue_yields_fail():
    review = _review(issues=[PageReviewIssue(category="text_overflow", severity="major",
                                              description="caption clipped", viewport="desktop")])
    result = aggregate_preview([_clean_report()], review)
    assert result.state == AssetState.PREVIEW_REVIEW_FAIL


def test_minor_reviewer_issue_alone_still_passes():
    """Matches the reviewer's own instructions: minor findings are
    informational, not gating -- a page shouldn't fail preview review over a
    slightly uneven margin."""
    review = _review(issues=[PageReviewIssue(category="spacing_inconsistency", severity="minor",
                                              description="slightly uneven margin", viewport="desktop")])
    result = aggregate_preview([_clean_report()], review)
    assert result.state == AssetState.PREVIEW_REVIEW_PASS


def test_multiple_viewport_reports_are_all_checked():
    reports = [
        _clean_report("desktop"),
        PageCaptureReport(url="https://x/", viewport_name="mobile", screenshot_path="/tmp/m.png",
                           broken_images=["https://x/m.jpg"]),
    ]
    result = aggregate_preview(reports, _review())
    assert result.state == AssetState.PREVIEW_REVIEW_FAIL
    assert any("mobile" in r for r in result.reasons)


def test_requires_at_least_one_capture_report():
    with pytest.raises(ValueError):
        aggregate_preview([], _review())


def test_never_reads_overall_summary_to_decide_pass_fail():
    """Structural check mirroring test_aggregator.py's equivalent -- proves
    the free-text overall_summary_for_humans field can never influence the
    verdict because the function's source never even references it."""
    source = inspect.getsource(aggregate_preview)
    assert "overall_summary_for_humans" not in source
