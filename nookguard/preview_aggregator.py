"""Preview-QA code aggregator (Commit 10) -- the PREVIEWED -> {PREVIEW_REVIEW_PASS,
PREVIEW_REVIEW_FAIL} decision, same "code decides, model never asserts a
verdict" pattern as aggregator.py (Commit 8). PageReviewResult deliberately
has no overall pass field (see schemas.py) -- this module is the only place
that turns PageCaptureReport(s) + PageReviewResult into a release-relevant
AssetState.

Two independent evidence sources feed the decision:
  - PageCaptureReport: deterministic, code-observed facts from the real
    browser (broken <img> tags, console errors, failed network requests).
    Any of these is an automatic fail -- there is no code path that reads a
    reviewer's prose and overrides a real broken image.
  - PageReviewResult: the page reviewer's structured issue list. Only
    critical/major severities are blocking; a page with only minor issues
    still passes (matches the reviewer's own instructions not to flag
    subjective taste as a defect -- minor findings are informational, not
    gating)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .preview import PageCaptureReport
from .schemas import PageReviewResult
from .state_machine import AssetState

BLOCKING_SEVERITIES = {"critical", "major"}


@dataclass
class PreviewAggregationResult:
    state: AssetState
    reasons: list[str] = field(default_factory=list)


def aggregate_preview(
    capture_reports: list[PageCaptureReport],
    review: PageReviewResult,
) -> PreviewAggregationResult:
    if not capture_reports:
        raise ValueError("aggregate_preview requires at least one PageCaptureReport")

    reasons: list[str] = []

    for report in capture_reports:
        if report.broken_images:
            reasons.append(
                f"{report.viewport_name}: broken image(s) {report.broken_images}"
            )
        if report.console_errors:
            reasons.append(
                f"{report.viewport_name}: console error(s) {report.console_errors}"
            )
        if report.failed_requests:
            reasons.append(
                f"{report.viewport_name}: failed network request(s) {report.failed_requests}"
            )

    blocking_issues = [i for i in review.issues if i.severity in BLOCKING_SEVERITIES]
    for issue in blocking_issues:
        reasons.append(
            f"{issue.viewport}: {issue.category} ({issue.severity}) -- {issue.description}"
        )

    if reasons:
        return PreviewAggregationResult(AssetState.PREVIEW_REVIEW_FAIL, reasons)

    return PreviewAggregationResult(
        AssetState.PREVIEW_REVIEW_PASS,
        ["No broken images, console errors, or failed requests in any captured "
         "viewport; no critical/major reviewer findings"],
    )
