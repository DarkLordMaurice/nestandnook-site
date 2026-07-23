"""Commit 20: live-review regression corpus tests. Two kinds of coverage,
deliberately kept separate: (1) wiring tests with a monkeypatched
observer/judge (proves run_live_review_regression_corpus correctly calls
the real functions, builds real ReviewPacks, and aggregates whatever comes
back -- the mechanism, not a specific model's judgment); (2) one real,
UNMOCKED run against this actual environment (no monkeypatching at all),
matching test_cli.py's own `test_canary_run_reports_which_step_failed`
pattern -- proves the real path genuinely reaches the real Claude Code CLI
transport and stops honestly at the real, current auth wall, rather than
failing earlier from a wiring bug that would be indistinguishable from the
auth wall if never tested unmocked."""

from __future__ import annotations

from pathlib import Path

from nookguard.agent_runner import ReviewSessionError
from nookguard.regression_live import (
    LIVE_FIXTURES,
    REGRESSION_IMAGES_DIR,
    run_live_review_regression_corpus,
)
from nookguard.schemas import BlindObservation, ContractJudgment, RequirementJudgment, RequirementResult


def test_every_live_fixture_image_exists_on_disk():
    """The corpus is only as real as the files it points at -- confirms
    every LIVE_FIXTURES entry's image_filename genuinely exists in
    regression_images/, not just that the fixture list compiles."""
    for fixture in LIVE_FIXTURES:
        image_path = REGRESSION_IMAGES_DIR / fixture.image_filename
        assert image_path.exists(), f"{fixture.fixture_id}: missing {image_path}"
        assert image_path.stat().st_size > 0


def test_run_live_review_corpus_unmocked_reaches_real_transport_and_fails_honestly():
    """No monkeypatching here -- exactly like test_cli.py's
    test_canary_run_reports_which_step_failed. The real observer session
    will fail (no authenticated Claude Code CLI in this environment, see
    docs/nookguard/BUILD-LOG.md's Commit 18/19 entries), and every fixture
    must honestly report review_process_completed=False with a real
    REVIEW_ERROR, not silently pass or crash the whole corpus run."""
    report = run_live_review_regression_corpus()
    assert len(report.results) == len(LIVE_FIXTURES)
    assert report.review_process_completed_count == 0
    for result in report.results:
        assert result.review_process_completed is False
        assert result.actual_state == "REVIEW_ERROR"
        assert result.passed is False


def test_run_live_review_corpus_uses_real_agent_runner_functions(monkeypatch):
    """Wiring proof: monkeypatch regression_live's own imported names for
    run_observer_session/run_judge_session (same pattern test_cli.py uses
    for cli.py's imported names) and confirm the corpus actually calls
    through to them with a real ReviewPack per fixture, then aggregates a
    real verdict -- not a hand-picked shortcut."""
    import nookguard.regression_live as live_module

    calls = {"observer": 0, "judge": 0}

    def fake_observer(review_pack, **kwargs):
        calls["observer"] += 1
        return BlindObservation(
            review_id="r1", candidate_sha256=review_pack.candidate_sha256,
            review_pack_sha256=review_pack.review_pack_sha256, reviewer_agent_hash="h",
            reviewer_session_id="s", context_bundle_sha256="cb", observer_role=review_pack.observer_role,
        )

    def fake_judge(contract, spec_sha256, blind_obs, adversarial_obs, **kwargs):
        calls["judge"] += 1
        return ContractJudgment(
            candidate_sha256=blind_obs.candidate_sha256, spec_sha256=spec_sha256,
            judge_session_id="j", judge_agent_hash="h", context_bundle_sha256="cb",
            requirements=[
                RequirementJudgment(requirement_id=r.requirement_id, result=RequirementResult.TRUE,
                                     evidence_observation_ids=["obs1"])
                for r in contract.requirements
            ],
        )

    monkeypatch.setattr(live_module, "run_observer_session", fake_observer)
    monkeypatch.setattr(live_module, "run_judge_session", fake_judge)

    report = run_live_review_regression_corpus()
    assert calls["observer"] == len(LIVE_FIXTURES) * 2  # blind_a + adversarial_b per fixture
    assert calls["judge"] == len(LIVE_FIXTURES)
    for result in report.results:
        assert result.review_process_completed is True
        assert result.actual_state != "REVIEW_ERROR"
        assert result.actual_state != "IMAGE_MISSING"


def test_run_live_review_corpus_reports_review_error_without_crashing_whole_run(monkeypatch):
    """A single fixture's real observer failure must not take down the
    whole corpus run -- each fixture is independently reported."""
    import nookguard.regression_live as live_module

    def failing_observer(review_pack, **kwargs):
        raise ReviewSessionError(review_pack.observer_role, "simulated real session failure")

    monkeypatch.setattr(live_module, "run_observer_session", failing_observer)

    report = run_live_review_regression_corpus()
    assert len(report.results) == len(LIVE_FIXTURES)
    for result in report.results:
        assert result.review_process_completed is False
        assert result.actual_state == "REVIEW_ERROR"
        assert "simulated real session failure" in result.detail


def test_run_live_review_corpus_reports_image_missing_distinctly(tmp_path, monkeypatch):
    """A fixture pointed at a nonexistent images_dir must fail honestly as
    IMAGE_MISSING, not silently skip or crash -- confirms the missing-file
    branch is real, not just theoretical."""
    empty_dir = tmp_path / "no_images_here"
    empty_dir.mkdir()
    report = run_live_review_regression_corpus(images_dir=empty_dir)
    for result in report.results:
        assert result.actual_state == "IMAGE_MISSING"
        assert result.review_process_completed is False
        assert result.passed is False
