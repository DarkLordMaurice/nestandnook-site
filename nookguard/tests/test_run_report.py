"""Section 24, "Completion and Evidence Protocol" (NookGuard-Plan.docx
p.26): run-report.json/.md + owner summary, derived from real ledger
events + each asset's real store state -- never from a narrated claim.
Covers both unit-level bucketing (via a fake stubbed regression runner,
manually-set store states) and one real end-to-end integration path
through the actual pipeline commands (spec-lock through production-verify)
to prove the wiring produces a real PROD_VERIFIED terminal_status, not
just a plausible-looking one."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import nookguard.cli as cli_module
from nookguard.cli import run_cli
from nookguard.ledger import Ledger
from nookguard.run_report import (
    build_run_report,
    default_regression_runner,
    render_markdown,
    render_owner_summary,
    write_run_report,
)
from nookguard.schemas import BlindObservation, ContractJudgment, PageReviewResult, RequirementJudgment, RequirementResult
from nookguard.state_machine import AssetState
from nookguard.store import Store

PASSING_REGRESSION = {"passed": 10, "failed": 0, "all_passed": True, "results": []}
FAILING_REGRESSION = {"passed": 8, "failed": 2, "all_passed": False, "results": []}


def _fixed_commit(_project_root: Path):
    return "deadbeefcafefeed0000000000000000000000"


def test_no_assets_for_run_is_incomplete():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        report = build_run_report(
            store, ledger, "empty-run",
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )
        assert report.terminal_status == "INCOMPLETE"
        assert any("no assets recorded" in b for b in report.blocking)
        assert report.assets == {
            "approved": 0, "rejected": 0, "needs_owner": 0,
            "production_verified": 0, "in_progress": 0,
            "process_error": 0, "prod_mismatch": 0,
        }


def test_mixed_asset_states_bucket_correctly_and_block():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "mixed-run"

        # One ledger event per asset is enough to register it as "touched
        # by this run" -- the report reads current state from the store,
        # not from replaying every transition itself.
        for asset_id in ("a1", "a2", "a3", "a4"):
            ledger.append(run_id=run_id, event_type="generation.registered",
                           actor_role="test", payload={}, asset_id=asset_id)

        store.set_state("a1", AssetState.PROD_VERIFIED.value)   # fully done
        store.set_state("a2", AssetState.OWNER_REJECTED.value)  # correctly rejected
        store.set_state("a3", AssetState.NEEDS_OWNER.value)     # pending human
        store.set_state("a4", AssetState.RELEASED.value)        # approved, not yet verified

        report = build_run_report(
            store, ledger, run_id,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )

        assert report.assets == {
            "approved": 2,             # a1 (prod_verified) + a4 (released)
            "rejected": 1,              # a2
            "needs_owner": 1,           # a3
            "production_verified": 1,   # a1 only
            "in_progress": 0,
            "process_error": 0,
            "prod_mismatch": 0,
        }
        assert report.terminal_status == "INCOMPLETE"
        assert any("needs_owner" in b or "needs owner" in b.lower() for b in report.blocking)
        assert any("approved but not yet production-verified" in b for b in report.blocking)
        assert report.repository_commit == "deadbeefcafefeed0000000000000000000000"


def test_review_error_never_yields_prod_verified():
    """Regression test for a real defect caught 2026-07-22 during a live
    canary run (see BUILD-LOG Commit 18): a lone asset that hit
    REVIEW_ERROR -- meaning the review process itself never completed, no
    decision was ever reached -- was originally folded into the same
    'rejected' bucket as a genuinely resolved content rejection, so the
    report claimed terminal_status=PROD_VERIFIED / ok=true even though
    nothing had actually been reviewed. This must never regress: a
    review_error asset must always block, and must be distinctly named in
    both `assets` and `blocking`, never silently absorbed into 'rejected'."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "review-error-run"
        ledger.append(run_id=run_id, event_type="generation.registered",
                       actor_role="test", payload={}, asset_id="a1")
        store.set_state("a1", AssetState.REVIEW_ERROR.value)

        report = build_run_report(
            store, ledger, run_id,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )
        assert report.assets["process_error"] == 1
        assert report.assets["rejected"] == 0
        assert report.terminal_status == "INCOMPLETE"
        assert any("review_error" in b or "review-process error" in b for b in report.blocking)


def test_prod_mismatch_never_yields_prod_verified():
    """Same class of bug, other direction: a released asset whose
    production bytes don't match the approved candidate must always block
    terminal_status=PROD_VERIFIED, not be silently treated as an
    acceptable resolved rejection."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "prod-mismatch-run"
        ledger.append(run_id=run_id, event_type="generation.registered",
                       actor_role="test", payload={}, asset_id="a1")
        store.set_state("a1", AssetState.PROD_MISMATCH.value)

        report = build_run_report(
            store, ledger, run_id,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )
        assert report.assets["prod_mismatch"] == 1
        assert report.assets["rejected"] == 0
        assert report.terminal_status == "INCOMPLETE"
        assert any("prod_mismatch" in b for b in report.blocking)


def test_default_regression_runner_is_safe_to_call_twice_against_same_store():
    """Regression test for a real defect caught 2026-07-22 (see BUILD-LOG
    Commit 18): the first live invocation of `mediactl run-report` against
    a real store succeeded, but running it again against the SAME store
    (a completely normal thing to do -- check status, resolve something,
    check again) crashed with a raw FileExistsError, because the scratch
    directory used for regression fixtures was reused as-is across calls
    while at least one fixture creates its own subdirectories assuming a
    fresh directory every time. Must never regress: calling this twice in
    a row against the same store_root must succeed both times with the
    same real result."""
    with tempfile.TemporaryDirectory() as d:
        store_root = Path(d)
        first = default_regression_runner(store_root)
        second = default_regression_runner(store_root)
        assert first["all_passed"] is True
        assert second["all_passed"] is True
        assert first["passed"] == second["passed"] == 10


def test_regression_failure_blocks_even_with_clean_assets():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "regression-fail-run"
        ledger.append(run_id=run_id, event_type="generation.registered",
                       actor_role="test", payload={}, asset_id="a1")
        store.set_state("a1", AssetState.PROD_VERIFIED.value)

        report = build_run_report(
            store, ledger, run_id,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: FAILING_REGRESSION,
        )
        assert report.terminal_status == "INCOMPLETE"
        assert any("regression corpus" in b for b in report.blocking)


def test_unknown_state_asset_is_surfaced_not_silently_dropped():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "orphan-run"
        # Asset appears in the ledger but store.set_state was never called
        # for it -- a real anomaly (should never happen in a healthy run)
        # that must show up, not vanish from the counts.
        ledger.append(run_id=run_id, event_type="generation.registered",
                       actor_role="test", payload={}, asset_id="ghost-asset")

        report = build_run_report(
            store, ledger, run_id,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )
        assert report.unknown_state_assets == ["ghost-asset"]
        assert report.terminal_status == "INCOMPLETE"
        assert any("ghost-asset" in b for b in report.blocking)


def test_release_manifest_sha256_is_derived_from_release_events():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "release-run"
        ledger.append(run_id=run_id, event_type="asset.released", actor_role="test",
                       payload={"candidate_sha256": "c1", "public_url": "/x",
                                "release_manifest_sha256": "hash-a"},
                       asset_id="a1")
        store.set_state("a1", AssetState.RELEASED.value)

        report = build_run_report(
            store, ledger, run_id,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )
        # Derived (sha256 of the sorted per-asset hash list), not a literal
        # passthrough of "hash-a" -- see module docstring.
        assert report.release_manifest_sha256 is not None
        assert report.release_manifest_sha256 != "hash-a"
        assert len(report.release_manifest_sha256) == 64  # hex sha256


def test_no_releases_gives_none_release_manifest_sha256():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "no-release-run"
        ledger.append(run_id=run_id, event_type="generation.registered",
                       actor_role="test", payload={}, asset_id="a1")
        store.set_state("a1", AssetState.TECHNICAL_VALIDATING.value)

        report = build_run_report(
            store, ledger, run_id,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )
        assert report.release_manifest_sha256 is None


def test_evidence_index_written_to_real_file_and_matches_events():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "evidence-run"
        ledger.append(run_id=run_id, event_type="generation.registered",
                       actor_role="test", payload={"x": 1}, asset_id="a1")
        ledger.append(run_id=run_id, event_type="technical_validation.completed",
                       actor_role="test", payload={"result": "technical_pass"}, asset_id="a1")
        store.set_state("a1", AssetState.TECHNICAL_PASS.value)

        report = build_run_report(
            store, ledger, run_id,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )
        evidence_path = Path(report.evidence_index)
        assert evidence_path.exists()
        entries = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert len(entries) == 2
        assert {e["event_type"] for e in entries} == {
            "generation.registered", "technical_validation.completed",
        }


def test_render_markdown_and_owner_summary_reflect_blocking_state():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "render-run"
        ledger.append(run_id=run_id, event_type="generation.registered",
                       actor_role="test", payload={}, asset_id="a1")
        store.set_state("a1", AssetState.NEEDS_OWNER.value)

        report = build_run_report(
            store, ledger, run_id,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )
        md = render_markdown(report)
        assert "INCOMPLETE" not in md.split("Complete")[0] or "terminal_status" in md
        assert "`INCOMPLETE`" in md
        assert "Blocking" in md

        summary = render_owner_summary(report)
        assert summary.startswith(f"Run {run_id}: INCOMPLETE")
        assert "Remaining:" in summary


def test_write_run_report_writes_all_three_artifacts():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store, ledger = Store(root), Ledger(root / "events.jsonl")
        run_id = "write-run"
        ledger.append(run_id=run_id, event_type="generation.registered",
                       actor_role="test", payload={}, asset_id="a1")
        store.set_state("a1", AssetState.PROD_VERIFIED.value)

        out_dir = root / "out"
        result = write_run_report(
            store, ledger, run_id, out_dir,
            repository_commit_resolver=_fixed_commit,
            regression_runner=lambda _root: PASSING_REGRESSION,
        )
        assert result["terminal_status"] == "PROD_VERIFIED"
        assert Path(result["run_report_json_path"]).exists()
        assert Path(result["run_report_md_path"]).exists()
        assert Path(result["owner_summary_path"]).exists()
        payload = json.loads(Path(result["run_report_json_path"]).read_text(encoding="utf-8"))
        assert payload["run_id"] == run_id


SAMPLE_CONTRACT = {
    "asset_id": "run-report-e2e-asset", "project_id": "nest-and-nook", "page_id": "p1",
    "slot_id": "hero", "media_type": "image", "risk_tier": "tier_0_decorative",
    "page_type_contract_version": "1", "source_excerpt": "test", "source_excerpt_sha256": "x",
    "canonical_reference_bundle_sha256": "y", "subject": "Winnie", "action": "measuring",
    "scene": "office", "planner_session_id": "s1", "plan_evaluator_session_id": "s2",
    "requirements": [
        {"requirement_id": "r1", "type": "count", "statement": "exactly 1 tape measure visible",
         "critical": True}
    ],
    "forbidden_objects": ["logo", "brand text"],
}


def test_run_report_cli_end_to_end_reaches_prod_verified(monkeypatch, tmp_path):
    """Drives the real pipeline (spec-lock through production-verify, same
    steps cmd_canary_run chains) for one asset, then runs the real
    `run-report` CLI command -- including the REAL regression corpus (no
    stub here) -- and confirms it reports PROD_VERIFIED with a real,
    checkable release_manifest_sha256 and a real evidence index file on
    disk. This is the actual proof the wiring works end to end, not just
    that the unit-level bucketing logic is correct in isolation.

    observe/judge/preview-review are monkeypatched at nookguard.cli's own
    imported names (not agent_runner's) -- same established pattern as
    test_cli.py's `_drive_to_preview_review_pass` -- since this sandbox has
    no live Anthropic credentials for the real Claude review-agent calls
    those commands make. Everything else in this test runs for real."""

    def fake_observer(review_pack, **kwargs):
        return BlindObservation(
            review_id="r1", candidate_sha256=review_pack.candidate_sha256,
            review_pack_sha256=review_pack.review_pack_sha256, reviewer_agent_hash="h",
            reviewer_session_id="s", context_bundle_sha256="cb", observer_role=review_pack.observer_role,
        )

    def fake_judge(contract, spec_sha256, blind_obs, adversarial_obs, **kwargs):
        return ContractJudgment(
            candidate_sha256=blind_obs.candidate_sha256, spec_sha256=spec_sha256,
            judge_session_id="j", judge_agent_hash="h", context_bundle_sha256="cb",
            requirements=[RequirementJudgment(requirement_id="r1", result=RequirementResult.TRUE,
                                               evidence_observation_ids=["obs1"])],
        )

    def fake_page_reviewer(contact_sheet_path, page_url, viewports_captured, **kwargs):
        return PageReviewResult(
            page_url=page_url, viewports_reviewed=viewports_captured,
            review_session_id="prs-e2e", reviewer_agent_hash="h", context_bundle_sha256="cb", issues=[],
        )

    monkeypatch.setattr(cli_module, "run_observer_session", fake_observer)
    monkeypatch.setattr(cli_module, "run_judge_session", fake_judge)
    monkeypatch.setattr(cli_module, "run_page_review_session", fake_page_reviewer)

    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    common = ["--store-root", store_root, "--run-id", "e2e-run", "--actor-role", "test"]

    spec = run_cli(["spec-lock", *common, "--contract", str(contract_path)])
    assert spec["ok"], spec
    prompt = run_cli(["prompt-compile", *common, "--spec", spec["spec_sha256"]])
    assert prompt["ok"], prompt
    gen = run_cli(["generate", *common, "--spec", spec["spec_sha256"],
                    "--prompt", prompt["prompt_sha256"], "--adapter", "stub"])
    assert gen["ok"], gen
    candidate_sha = gen["candidate_sha256"]
    reg = run_cli(["register", *common, "--spec", spec["spec_sha256"],
                    "--prompt", prompt["prompt_sha256"], "--candidate-sha256", candidate_sha,
                    "--adapter-version", gen["adapter_version"], "--session-id", "gen-session"])
    assert reg["ok"], reg
    val = run_cli(["validate", *common, "--candidate-sha256", candidate_sha])
    assert val["ok"] and val["result"] == "technical_pass", val
    pack = run_cli(["review-pack-build", *common, "--candidate-sha256", candidate_sha])
    assert pack["ok"], pack
    obs = run_cli(["observe", *common, "--candidate-sha256", candidate_sha])
    assert obs["ok"], obs
    judge = run_cli(["judge", *common, "--candidate-sha256", candidate_sha])
    assert judge["ok"] and judge["result"] == "semantic_pass", judge
    integ = run_cli(["integrate", *common, "--candidate-sha256", candidate_sha])
    assert integ["ok"], integ

    page_path = tmp_path / "_e2e_page.html"
    page_path.write_text("<html><body><h1>e2e</h1></body></html>", encoding="utf-8")
    cap = run_cli(["preview-capture", *common, "--candidate-sha256", candidate_sha,
                    "--page-url", page_path.resolve().as_uri()])
    assert cap["ok"], cap
    rev = run_cli(["preview-review", *common, "--candidate-sha256", candidate_sha])
    assert rev["ok"] and rev["result"] == "preview_review_pass", rev

    public_root = tmp_path / "_e2e_public"
    public_dir = public_root / "winnie"
    rel = run_cli(["release", *common, "--candidate-sha256", candidate_sha,
                    "--public-dir", str(public_dir), "--public-url-prefix", "/winnie",
                    "--name-hint", "e2e"])
    assert rel["ok"], rel

    dist_root = tmp_path / "_e2e_dist"
    released_file = Path(rel["public_path"])
    relative = released_file.resolve().relative_to(public_root.resolve())
    dist_target = dist_root / relative
    dist_target.parent.mkdir(parents=True, exist_ok=True)
    dist_target.write_bytes(released_file.read_bytes())

    verify = run_cli(["production-verify", *common, "--candidate-sha256", candidate_sha,
                       "--public-root", str(public_root), "--dist-root", str(dist_root)])
    assert verify["ok"] and verify["result"] == "prod_verified", verify

    report = run_cli(["run-report", *common])
    assert report["ok"], report
    assert report["terminal_status"] == "PROD_VERIFIED"
    assert report["blocking"] == []
    assert report["assets"]["production_verified"] == 1
    assert report["assets"]["approved"] == 1
    assert report["release_manifest_sha256"] is not None
    assert Path(report["run_report_json_path"]).exists()
    assert Path(report["run_report_md_path"]).exists()
    assert Path(report["owner_summary_path"]).exists()
    assert Path(report["evidence_index"]).exists()
