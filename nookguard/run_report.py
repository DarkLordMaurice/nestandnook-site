"""Section 24, "Completion and Evidence Protocol" (NookGuard-Plan.docx p.26):

    "Claude's final message is not the record of truth. NookGuard generates
    run-report.json, run-report.md, and a compact owner summary from ledger
    events."

    "Claude may say 'complete' only when terminal_status is PROD_VERIFIED.
    Otherwise it must say exactly what remains and link the blocker
    receipt."

This module builds that report from a run's real ledger events plus each
touched asset's real current state (via Store.get_state) -- never from a
session's own narrative of what happened. It is the mechanical enforcement
of the rule above: `terminal_status` is computed, not asserted, and
`blocking` always says exactly what's outstanding when it isn't
PROD_VERIFIED.

The docx's own example schema (page 26) is a floor, not a literal template
this codebase can fill in unmodified -- three of its seven fields don't map
onto anything that exists yet, and this module is honest about that rather
than fabricating values:

- `release_manifest_sha256` is shown as a single top-level field in the
  spec's example. This codebase's ReleaseManifestEntry (manifest.py)
  computes that hash per released asset -- there is no single aggregate
  release-manifest file anywhere in the pipeline. This module derives one
  deterministic value instead: the canonical-JSON SHA-256 of the sorted
  list of every `asset.released` event's own `release_manifest_sha256`
  for this run. It is a real, reproducible, checkable value -- just a
  DERIVED aggregate, not a pre-existing file's hash, and is documented as
  such in the field's own report entry.
- `production_deployment_id` has no source anywhere in this Python
  package -- no Cloudflare Pages API call exists on this side (see
  BUILD-LOG Commit 16 "unresolved risks"). Accepted only as an optional
  caller-supplied override; defaults to None and never gates
  `terminal_status`, since withholding completion for a field this side
  genuinely cannot produce would be dishonest in the other direction.
- `evidence_index` is shown as an r2:// URL in the spec's example. The
  Python pipeline is not wired to nookguard-worker/R2 yet (BUILD-LOG
  Commit 16's single biggest standing gap). This module writes a real
  local evidence index JSON file (every ledger event for the run, with
  its own payload_sha256) and points `evidence_index` at that real local
  path, not a fabricated r2:// URL.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .hashing import sha256_canonical_json
from .ledger import Ledger
from .regression_corpus import run_regression_corpus
from .schemas import Event, utcnow_iso
from .state_machine import AssetState
from .store import Store

# Bucketed off state_machine.TRANSITIONS's own terminal/non-terminal split
# (see state_machine.py) -- not a new, hand-picked taxonomy. The 9 states
# with no outgoing transition other than PROD_VERIFIED are the "regenerate
# only" states (state_machine._REGENERATE_SOURCES); PROD_VERIFIED is the
# one success terminal.
REJECTED_STATES = frozenset({
    AssetState.GENERATION_BLOCKED, AssetState.TECHNICAL_FAIL, AssetState.SEMANTIC_FAIL,
    AssetState.FAIL_EVIDENCE, AssetState.FAIL_REFERENCE, AssetState.REVIEW_ERROR,
    AssetState.OWNER_REJECTED, AssetState.PREVIEW_REVIEW_FAIL, AssetState.PROD_MISMATCH,
})
# "Cleared review" -- has passed judgment (or an owner) and is proceeding
# toward release, whether or not it has arrived yet. production_verified
# (below) is always a subset of this set, never a sibling of it -- matches
# the spec's own example where approved == production_verified on a fully
# clean run.
APPROVED_STATES = frozenset({
    AssetState.SEMANTIC_PASS, AssetState.OWNER_APPROVED, AssetState.INTEGRATED,
    AssetState.PREVIEWED, AssetState.PREVIEW_REVIEW_PASS, AssetState.RELEASED,
    AssetState.PROD_VERIFIED,
})
NEEDS_OWNER_STATES = frozenset({AssetState.NEEDS_OWNER})


@dataclass
class RunReport:
    run_id: str
    terminal_status: str
    repository_commit: Optional[str]
    release_manifest_sha256: Optional[str]
    production_deployment_id: Optional[str]
    assets: dict[str, int]
    regression_suite: dict[str, Any]
    evidence_index: str
    blocking: list[str] = field(default_factory=list)
    unknown_state_assets: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "terminal_status": self.terminal_status,
            "repository_commit": self.repository_commit,
            "release_manifest_sha256": self.release_manifest_sha256,
            "production_deployment_id": self.production_deployment_id,
            "assets": self.assets,
            "regression_suite": self.regression_suite,
            "evidence_index": self.evidence_index,
            "blocking": self.blocking,
            "unknown_state_assets": self.unknown_state_assets,
            "generated_at": self.generated_at,
        }


def _asset_ids_for_run(events: list[Event]) -> list[str]:
    """Preserves first-seen order -- deterministic, and reads naturally as
    "the order these assets entered this run" in the rendered report."""
    seen: list[str] = []
    for event in events:
        if event.asset_id and event.asset_id not in seen:
            seen.append(event.asset_id)
    return seen


def _aggregate_release_manifest_sha256(events: list[Event]) -> Optional[str]:
    hashes = sorted({
        event.payload["release_manifest_sha256"]
        for event in events
        if event.event_type == "asset.released" and "release_manifest_sha256" in event.payload
    })
    if not hashes:
        return None
    return sha256_canonical_json(hashes)


def _build_evidence_index(events: list[Event]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "asset_id": event.asset_id,
            "actor_role": event.actor_role,
            "created_at": event.created_at,
            "payload_sha256": event.payload_sha256,
        }
        for event in events
    ]


def default_repository_commit(project_root: Path) -> Optional[str]:
    """Real `git rev-parse HEAD` against project_root. Returns None (never
    raises) if git isn't available or project_root isn't a repo -- a
    missing commit hash is a fact to report, not a reason to crash a report
    generator."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(project_root),
            capture_output=True, text=True, timeout=10, check=True,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def default_regression_runner(store_root: Path) -> dict[str, Any]:
    """Runs the real Appendix I regression corpus fresh, same pattern as
    cli.py's cmd_regression_run -- a report claiming completeness must
    prove the regression corpus still passes NOW, not recall a prior run's
    narrated result (nothing in this pipeline persists regression-run
    results anywhere to recall from -- see cli.py, cmd_regression_run
    doesn't log to the ledger)."""
    base = store_root / "_regression_tmp"
    base.mkdir(parents=True, exist_ok=True)

    def tmp_dir_factory(name: str) -> Path:
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    report = run_regression_corpus(tmp_dir_factory)
    passed = sum(1 for r in report.results if r.passed)
    failed = len(report.results) - passed
    return {
        "passed": passed,
        "failed": failed,
        "all_passed": report.all_passed,
        "results": [
            {"fixture_id": r.fixture_id, "category": r.category, "passed": r.passed}
            for r in report.results
        ],
    }


def build_run_report(
    store: Store,
    ledger: Ledger,
    run_id: str,
    *,
    project_root: Optional[Path] = None,
    production_deployment_id: Optional[str] = None,
    repository_commit_resolver: Callable[[Path], Optional[str]] = default_repository_commit,
    regression_runner: Optional[Callable[[Path], dict[str, Any]]] = None,
) -> RunReport:
    """Builds the report entirely from real ledger events + each asset's
    real current Store state -- no argument here lets a caller assert a
    status directly; every field is derived."""
    events = ledger.for_run(run_id)
    asset_ids = _asset_ids_for_run(events)

    approved = rejected = needs_owner = production_verified = in_progress = 0
    unknown_state_assets: list[str] = []
    for asset_id in asset_ids:
        raw_state = store.get_state(asset_id)
        if raw_state is None:
            unknown_state_assets.append(asset_id)
            continue
        state = AssetState(raw_state)
        if state in REJECTED_STATES:
            rejected += 1
        elif state in NEEDS_OWNER_STATES:
            needs_owner += 1
        elif state in APPROVED_STATES:
            approved += 1
            if state is AssetState.PROD_VERIFIED:
                production_verified += 1
        else:
            in_progress += 1

    regression_runner = regression_runner or default_regression_runner
    store_root = store.root
    regression = regression_runner(store_root)

    blocking: list[str] = []
    if not asset_ids:
        blocking.append("no assets recorded for this run_id (no events with an asset_id)")
    if unknown_state_assets:
        blocking.append(
            f"{len(unknown_state_assets)} asset(s) referenced in ledger events but have no "
            f"recorded state in the store: {', '.join(unknown_state_assets)}"
        )
    if needs_owner:
        blocking.append(f"{needs_owner} asset(s) awaiting owner decision (state: needs_owner)")
    if in_progress:
        blocking.append(f"{in_progress} asset(s) still mid-pipeline (not yet a terminal state)")
    if approved > production_verified:
        blocking.append(
            f"{approved - production_verified} asset(s) approved but not yet production-verified"
        )
    if not regression["all_passed"]:
        blocking.append(
            f"regression corpus: {regression['failed']} of "
            f"{regression['passed'] + regression['failed']} fixtures failing"
        )

    terminal_status = "PROD_VERIFIED" if not blocking else "INCOMPLETE"

    resolved_project_root = project_root if project_root is not None else store_root
    repository_commit = repository_commit_resolver(resolved_project_root)

    evidence_entries = _build_evidence_index(events)
    evidence_dir = store_root / "reports" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "evidence-index.json"
    evidence_path.write_text(json.dumps(evidence_entries, indent=2), encoding="utf-8")

    return RunReport(
        run_id=run_id,
        terminal_status=terminal_status,
        repository_commit=repository_commit,
        release_manifest_sha256=_aggregate_release_manifest_sha256(events),
        production_deployment_id=production_deployment_id,
        assets={
            "approved": approved,
            "rejected": rejected,
            "needs_owner": needs_owner,
            "production_verified": production_verified,
            "in_progress": in_progress,
        },
        regression_suite=regression,
        evidence_index=str(evidence_path),
        blocking=blocking,
        unknown_state_assets=unknown_state_assets,
    )


def render_markdown(report: RunReport) -> str:
    lines = [
        f"# NookGuard Run Report — {report.run_id}",
        "",
        f"**terminal_status:** `{report.terminal_status}`",
        f"**generated_at:** {report.generated_at}",
        f"**repository_commit:** `{report.repository_commit or 'unknown'}`",
        f"**release_manifest_sha256** (derived, see module docstring): "
        f"`{report.release_manifest_sha256 or 'none — no assets released this run'}`",
        f"**production_deployment_id:** {report.production_deployment_id or '_not provided_'}",
        "",
        "## Assets",
        "",
        "| approved | rejected | needs_owner | production_verified | in_progress |",
        "|---|---|---|---|---|",
        f"| {report.assets['approved']} | {report.assets['rejected']} | "
        f"{report.assets['needs_owner']} | {report.assets['production_verified']} | "
        f"{report.assets['in_progress']} |",
        "",
        "## Regression suite",
        "",
        f"{report.regression_suite['passed']} passed, {report.regression_suite['failed']} failed "
        f"(all_passed: {report.regression_suite['all_passed']})",
        "",
        f"## Evidence index",
        "",
        f"`{report.evidence_index}`",
        "",
    ]
    if report.blocking:
        lines.append("## Blocking — this run is NOT complete")
        lines.append("")
        for item in report.blocking:
            lines.append(f"- {item}")
        lines.append("")
    else:
        lines.append("## Complete")
        lines.append("")
        lines.append(
            "Every asset touched by this run reached a terminal, production-verified or "
            "correctly-rejected state, and the regression corpus passes. No blockers."
        )
        lines.append("")
    return "\n".join(lines)


def render_owner_summary(report: RunReport) -> str:
    """The "compact owner summary" the spec names alongside run-report.json
    and run-report.md -- short enough to read in one glance, per Appendix
    J's operational runbook framing of what Maurice actually needs."""
    headline = "COMPLETE" if report.terminal_status == "PROD_VERIFIED" else "INCOMPLETE"
    lines = [
        f"Run {report.run_id}: {headline}",
        f"Assets — approved {report.assets['approved']}, rejected {report.assets['rejected']}, "
        f"needs owner {report.assets['needs_owner']}, live-verified "
        f"{report.assets['production_verified']}, still in progress {report.assets['in_progress']}",
        f"Regression suite: {report.regression_suite['passed']} passed, "
        f"{report.regression_suite['failed']} failed",
    ]
    if report.blocking:
        lines.append("Remaining:")
        lines.extend(f"  - {item}" for item in report.blocking)
    else:
        lines.append("Nothing outstanding.")
    lines.append(f"Full report: {report.evidence_index}")
    return "\n".join(lines)


def write_run_report(
    store: Store,
    ledger: Ledger,
    run_id: str,
    out_dir: Path,
    **build_kwargs: Any,
) -> dict[str, Any]:
    """Builds the report and writes all three artifacts the spec names
    (run-report.json, run-report.md, a compact owner summary), plus the
    evidence index build_run_report already wrote under the store root.
    Returns the report dict plus every written path, so a caller (the CLI
    command below, or a scheduled task) never has to re-derive a path."""
    report = build_run_report(store, ledger, run_id, **build_kwargs)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "run-report.json"
    md_path = out_dir / "run-report.md"
    summary_path = out_dir / "owner-summary.txt"

    json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    summary_path.write_text(render_owner_summary(report), encoding="utf-8")

    return {
        **report.to_dict(),
        "run_report_json_path": str(json_path),
        "run_report_md_path": str(md_path),
        "owner_summary_path": str(summary_path),
    }
