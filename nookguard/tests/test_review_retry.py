"""Commit 19, requirement 8/9: REVIEW_ERROR -> REVIEW_PENDING -> OBSERVING
recovery (`mediactl review-retry`). Tests: unchanged-candidate retry
succeeds and resumes real review, changed-candidate retry is rejected, and
retry exhaustion is enforced. Same monkeypatch-the-imported-name pattern as
test_cli.py's other observe/judge tests -- no real CLI or credential
needed."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from nookguard.agent_runner import ReviewSessionError
from nookguard.cli import run_cli

SAMPLE_CONTRACT = {
    "asset_id": "test-asset-retry", "project_id": "nest-and-nook", "page_id": "p1",
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


def _drive_to_review_error(monkeypatch, store_root: str, run_id: str, contract_path: Path) -> str:
    """Runs the real pipeline up through a real observer-session failure,
    landing the asset in REVIEW_ERROR with one real observation.error event
    already in the ledger -- exactly the state a genuine auth/infra failure
    leaves behind (see docs/nookguard/BUILD-LOG.md's Commit 18 live-canary
    entry)."""
    import nookguard.cli as cli_module

    def fake_observer_fails(review_pack, **kwargs):
        raise ReviewSessionError(review_pack.observer_role, "simulated review-process failure")

    monkeypatch.setattr(cli_module, "run_observer_session", fake_observer_fails)

    spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id,
                     "--contract", str(contract_path)])
    prompt = run_cli(["prompt-compile", "--store-root", store_root, "--run-id", run_id,
                       "--spec", spec["spec_sha256"]])
    gen = run_cli(["generate", "--store-root", store_root, "--run-id", run_id,
                    "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"], "--adapter", "stub"])
    candidate_sha = gen["candidate_sha256"]
    run_cli(["register", "--store-root", store_root, "--run-id", run_id, "--spec", spec["spec_sha256"],
             "--prompt", prompt["prompt_sha256"], "--candidate-sha256", candidate_sha,
             "--adapter-version", gen["adapter_version"], "--session-id", "gen-session"])
    run_cli(["validate", "--store-root", store_root, "--run-id", run_id, "--candidate-sha256", candidate_sha])
    run_cli(["review-pack-build", "--store-root", store_root, "--run-id", run_id,
             "--candidate-sha256", candidate_sha])

    obs = run_cli(["observe", "--store-root", store_root, "--run-id", run_id,
                    "--candidate-sha256", candidate_sha])
    assert not obs["ok"], obs

    state = run_cli(["run-report", "--store-root", store_root, "--run-id", run_id])  # sanity, non-blocking
    assert state is not None

    return candidate_sha


def test_review_retry_unchanged_candidate_succeeds_and_resumes_real_observation(monkeypatch, tmp_path):
    import nookguard.cli as cli_module
    from nookguard.schemas import BlindObservation, ContractJudgment, RequirementJudgment, RequirementResult

    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-retry-success"

    candidate_sha = _drive_to_review_error(monkeypatch, store_root, run_id, contract_path)

    retry = run_cli(["review-retry", "--store-root", store_root, "--run-id", run_id,
                      "--candidate-sha256", candidate_sha])
    assert retry["ok"], retry
    assert retry["state"] == "observing"
    assert retry["prior_failure_count"] == 1
    assert retry["retries_remaining"] == 1  # MAX_REVIEW_RETRIES(3) - 1 - 1

    # Recovery must actually resume real review, not just flip a state flag
    # -- swap the mock to succeed and confirm `observe` (unmodified) works
    # exactly as if this were a first attempt.
    def fake_observer_succeeds(review_pack, **kwargs):
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

    monkeypatch.setattr(cli_module, "run_observer_session", fake_observer_succeeds)
    monkeypatch.setattr(cli_module, "run_judge_session", fake_judge)

    obs = run_cli(["observe", "--store-root", store_root, "--run-id", run_id,
                    "--candidate-sha256", candidate_sha])
    assert obs["ok"], obs

    judge = run_cli(["judge", "--store-root", store_root, "--run-id", run_id,
                      "--candidate-sha256", candidate_sha])
    assert judge["ok"], judge
    assert judge["result"] == "semantic_pass"


def test_review_retry_rejects_when_asset_not_in_review_error():
    with tempfile.TemporaryDirectory() as d:
        store_root = str(Path(d) / "store")
        contract_path = Path(d) / "contract.json"
        contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
        run_id = "test-run-retry-wrong-state"
        spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id,
                         "--contract", str(contract_path)])
        prompt = run_cli(["prompt-compile", "--store-root", store_root, "--run-id", run_id,
                           "--spec", spec["spec_sha256"]])
        gen = run_cli(["generate", "--store-root", store_root, "--run-id", run_id,
                        "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"], "--adapter", "stub"])
        run_cli(["register", "--store-root", store_root, "--run-id", run_id, "--spec", spec["spec_sha256"],
                 "--prompt", prompt["prompt_sha256"], "--candidate-sha256", gen["candidate_sha256"],
                 "--adapter-version", gen["adapter_version"], "--session-id", "gen-session"])
        # Asset is at CANDIDATE_REGISTERED, never touched REVIEW_ERROR.
        result = run_cli(["review-retry", "--store-root", store_root, "--run-id", run_id,
                           "--candidate-sha256", gen["candidate_sha256"]])
        assert not result["ok"]
        assert "Illegal transition" in result["error"]


def test_review_retry_rejects_changed_candidate(monkeypatch, tmp_path):
    """If the ledger's most recent review-failure event names a DIFFERENT
    candidate than the one review-retry was called with, the retry must be
    refused -- recovering a stale/wrong candidate would be exactly the
    'fix a bad candidate and reuse it' failure mode this whole mechanism
    exists to prevent (see state_machine.py's _REGENERATE_SOURCES comment)."""
    from nookguard.ledger import Ledger

    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-retry-changed-candidate"

    candidate_sha = _drive_to_review_error(monkeypatch, store_root, run_id, contract_path)

    # Simulate a later failure event (e.g. a since-superseded retry cycle)
    # recorded against a different candidate hash for the same asset --
    # this becomes the new "most recent" failure.
    ledger = Ledger(Path(store_root) / "events.jsonl")
    ledger.append(run_id=run_id, event_type="observation.error", actor_role="test",
                   payload={"candidate_sha256": "some-other-candidate-hash-entirely", "role": "blind_a",
                            "reason": "simulated"},
                   asset_id="test-asset-retry")

    result = run_cli(["review-retry", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha])
    assert not result["ok"]
    assert result["reason"] == "changed_candidate"


def test_review_retry_rejects_after_retry_exhaustion(monkeypatch, tmp_path):
    """Bounded retries: once a candidate has failed review
    MAX_REVIEW_RETRIES times, review-retry must refuse and require a brand
    new generation attempt instead of recovering in place indefinitely."""
    from nookguard.cli import MAX_REVIEW_RETRIES
    from nookguard.ledger import Ledger

    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-retry-exhaustion"

    candidate_sha = _drive_to_review_error(monkeypatch, store_root, run_id, contract_path)
    # _drive_to_review_error already recorded 1 real failure; append enough
    # more (same candidate_sha256, so they don't trip the changed_candidate
    # guard) to reach the bound exactly.
    ledger = Ledger(Path(store_root) / "events.jsonl")
    for _ in range(MAX_REVIEW_RETRIES - 1):
        ledger.append(run_id=run_id, event_type="observation.error", actor_role="test",
                       payload={"candidate_sha256": candidate_sha, "role": "blind_a",
                                "reason": "simulated repeated failure"},
                       asset_id="test-asset-retry")

    result = run_cli(["review-retry", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha])
    assert not result["ok"]
    assert result["reason"] == "retry_exhausted"
    assert result["retry_count"] == MAX_REVIEW_RETRIES


def test_auth_check_cli_command_reports_real_unauthenticated_state(monkeypatch):
    """`mediactl auth-check` is a thin wrapper around
    cli_reviewer.check_claude_cli_auth -- confirm the CLI layer surfaces its
    real result faithfully (ok mirrors authenticated) without needing a
    real CLI/credential, by injecting a fake result at the cli_reviewer
    import site cli.py actually calls through."""
    import nookguard.cli as cli_module

    monkeypatch.setattr(cli_module, "check_claude_cli_auth",
                         lambda: {"authenticated": False, "reason": "cli_not_found",
                                   "claude_cli_path": None, "instructions": "install it"})
    result = run_cli(["auth-check"])
    assert result["ok"] is False
    assert result["authenticated"] is False
    assert result["reason"] == "cli_not_found"


def test_generate_real_adapter_refuses_without_passing_auth_check(monkeypatch, tmp_path):
    """Requirement 7: real (non-stub) generation must not proceed if the
    candidate it produces could never be reviewed afterward. Uses the
    huggingface adapter (a real AVAILABLE_ADAPTERS entry) with a failing
    auth-check injected, and confirms generation is refused before any
    adapter call happens."""
    import nookguard.cli as cli_module

    monkeypatch.setattr(cli_module, "check_claude_cli_auth",
                         lambda: {"authenticated": False, "reason": "auth_unavailable",
                                   "claude_cli_path": "C:/fake/claude.exe", "instructions": "run setup-token"})

    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-generate-auth-gate"

    spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id,
                     "--contract", str(contract_path)])
    prompt = run_cli(["prompt-compile", "--store-root", store_root, "--run-id", run_id,
                       "--spec", spec["spec_sha256"]])
    result = run_cli(["generate", "--store-root", store_root, "--run-id", run_id,
                       "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"],
                       "--adapter", "huggingface"])
    assert not result["ok"]
    assert result["reason"] == "auth_check_failed"
    assert result["auth_check"]["reason"] == "auth_unavailable"


def test_generate_skip_auth_check_flag_bypasses_gate_for_tests(monkeypatch, tmp_path):
    """--skip-auth-check exists purely so tests can exercise a real adapter
    call site without a real Claude CLI/credential present -- confirm it
    actually bypasses the auth-check gate. The huggingface adapter's own
    `generate` is also monkeypatched here (nookguard.cli imports the
    `adapters.huggingface` module lazily inside cmd_generate, so patching
    the module attribute is what the real call site sees) purely so this
    test never attempts a real network call with real retries/backoff --
    that would make this a network-dependent, slow test for a question
    ('was auth-check invoked?') that has nothing to do with HF connectivity."""
    import nookguard.adapters.huggingface as hf_adapter
    import nookguard.cli as cli_module

    called = {"auth_check": False}

    def fake_check():
        called["auth_check"] = True
        return {"authenticated": False, "reason": "cli_not_found"}

    monkeypatch.setattr(cli_module, "check_claude_cli_auth", fake_check)
    monkeypatch.setattr(hf_adapter, "generate", lambda prompt_text, **kwargs: b"fake-jpeg-bytes")

    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-generate-skip-auth-gate"

    spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id,
                     "--contract", str(contract_path)])
    prompt = run_cli(["prompt-compile", "--store-root", store_root, "--run-id", run_id,
                       "--spec", spec["spec_sha256"]])
    result = run_cli(["generate", "--store-root", store_root, "--run-id", run_id,
                       "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"],
                       "--adapter", "huggingface", "--skip-auth-check"])
    assert called["auth_check"] is False
    assert result["ok"], result
