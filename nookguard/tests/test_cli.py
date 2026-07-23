"""Integration test: exercises the real mediactl commands end-to-end through
run_cli() (no subprocess — faster, same code path a subprocess would hit)."""

import json
import tempfile
from pathlib import Path

import pytest

from nookguard.cli import run_cli

SAMPLE_CONTRACT = {
    "asset_id": "test-asset-1", "project_id": "nest-and-nook", "page_id": "p1",
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


@pytest.fixture(autouse=True)
def _fast_containment_site_root(monkeypatch, tmp_path):
    """Commit 24: observe/judge/preview-review -prepare/-submit each open a
    containment snapshot (containment.py) of an entire site tree before and
    after the reviewer's turn. Left at its production default (the real
    site/ directory -- hundreds of real content images per CLAUDE.md's own
    backlog notes), every CLI-level test in this file that touches one of
    those six commands would re-hash the ENTIRE real site tree on every
    single call -- confirmed directly: a real-site-rooted run of this file
    took 74+ seconds even AFTER this fix scoped things down, and was still
    running (unclear how much longer) before this fix existed. These tests
    exercise the CLI's OWN logic (state transitions, custody-hash
    validation, containment-violation detection), not the real site's
    content, so every test gets a small, real, per-test directory as its
    containment site-root instead -- same evidence-based snapshot/diff
    mechanism containment.py always uses, just scoped to a directory these
    tests actually control and that starts empty (a nonexistent/empty root
    snapshots as zero files, per containment._iter_files's own early
    return -- cheap and correct).

    Patches `cli_module._site_root` itself (the helper exclusively used by
    the six observe/judge/preview-review commands), NOT
    public_media_guard.DEFAULT_SITE_ROOT directly -- an earlier version of
    this fixture patched that module attribute instead, which broke three
    unrelated pre-existing tests (test_media_audit_cli_real_site_tree_is_
    clean, test_write_path_audit_cli_real_site_tree,
    test_deploy_cli_real_unmocked_reaches_wrangler_with_real_credentials)
    that each do their own `from nookguard.public_media_guard import
    DEFAULT_SITE_ROOT` to deliberately test against the REAL site tree --
    patching the shared module attribute silently redirected those live
    imports too. Patching `_site_root` instead only touches the six
    containment-using commands, leaving every other command's own
    site-root resolution completely untouched.

    Tests that need to prove something about a real mutation (e.g. the
    containment-violation test) monkeypatch `cli_module._site_root` again
    themselves, pointed at their own explicit fixture directory -- this
    simply overrides the value for that one test, no conflict."""
    import nookguard.cli as cli_module
    fixture_root = tmp_path / "fixture_site_root"
    monkeypatch.setattr(cli_module, "_site_root", lambda args: fixture_root)
    return fixture_root


def test_full_pipeline_run_start_through_validate():
    with tempfile.TemporaryDirectory() as d:
        store_root = str(Path(d) / "store")
        contract_path = Path(d) / "contract.json"
        contract_path.write_text(json.dumps(SAMPLE_CONTRACT))

        run_result = run_cli(["run-start", "--store-root", store_root])
        assert run_result["ok"]
        run_id = run_result["run_id"]

        pre = run_cli(["run-preflight", "--store-root", store_root, "--run-id", run_id])
        assert pre["ok"], pre

        spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id,
                         "--contract", str(contract_path)])
        assert spec["ok"], spec
        spec_sha = spec["spec_sha256"]

        prompt = run_cli(["prompt-compile", "--store-root", store_root, "--run-id", run_id,
                           "--spec", spec_sha])
        assert prompt["ok"], prompt
        prompt_sha = prompt["prompt_sha256"]

        gen = run_cli(["generate", "--store-root", store_root, "--run-id", run_id,
                        "--spec", spec_sha, "--prompt", prompt_sha, "--adapter", "stub"])
        assert gen["ok"], gen
        candidate_sha = gen["candidate_sha256"]

        reg = run_cli(["register", "--store-root", store_root, "--run-id", run_id,
                        "--spec", spec_sha, "--prompt", prompt_sha,
                        "--candidate-sha256", candidate_sha,
                        "--adapter-version", gen["adapter_version"],
                        "--session-id", "test-generator-session"])
        assert reg["ok"], reg

        val = run_cli(["validate", "--store-root", store_root, "--run-id", run_id,
                        "--candidate-sha256", candidate_sha])
        assert val["ok"], val
        assert val["result"] == "technical_pass"
        assert val["report"]["technical_pass"] is True

        pack = run_cli(["review-pack-build", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha])
        assert pack["ok"], pack
        assert set(pack["review_packs"].keys()) == {"blind_a", "adversarial_b"}
        assert pack["review_packs"]["blind_a"]["review_pack_sha256"] != \
            pack["review_packs"]["adversarial_b"]["review_pack_sha256"]


def test_full_pipeline_through_observe_judge_to_semantic_pass(monkeypatch):
    """Extends the same pipeline through observe/judge, with the Claude
    review-agent calls monkeypatched (nookguard.cli's own imported names,
    since `from .agent_runner import ...` binds a local reference) so no
    real API call happens. Proves cmd_observe/cmd_judge/aggregate are wired
    together correctly end to end through the real CLI, not just unit-level."""
    import nookguard.cli as cli_module
    from nookguard.schemas import BlindObservation, ContractJudgment, RequirementJudgment, RequirementResult

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

    monkeypatch.setattr(cli_module, "run_observer_session", fake_observer)
    monkeypatch.setattr(cli_module, "run_judge_session", fake_judge)

    with tempfile.TemporaryDirectory() as d:
        store_root = str(Path(d) / "store")
        contract_path = Path(d) / "contract.json"
        contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
        run_id = "test-run-observe-judge"

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
        assert obs["ok"], obs
        assert set(obs["observations"].keys()) == {"blind_a", "adversarial_b"}

        judge = run_cli(["judge", "--store-root", store_root, "--run-id", run_id,
                          "--candidate-sha256", candidate_sha])
        assert judge["ok"], judge
        assert judge["result"] == "semantic_pass"


def test_observe_rejects_when_not_in_observing_state():
    with tempfile.TemporaryDirectory() as d:
        store_root = str(Path(d) / "store")
        contract_path = Path(d) / "contract.json"
        contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
        run_id = "test-run-observe-reject"
        spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id,
                         "--contract", str(contract_path)])
        prompt = run_cli(["prompt-compile", "--store-root", store_root, "--run-id", run_id,
                           "--spec", spec["spec_sha256"]])
        gen = run_cli(["generate", "--store-root", store_root, "--run-id", run_id,
                        "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"], "--adapter", "stub"])
        run_cli(["register", "--store-root", store_root, "--run-id", run_id, "--spec", spec["spec_sha256"],
                 "--prompt", prompt["prompt_sha256"], "--candidate-sha256", gen["candidate_sha256"],
                 "--adapter-version", gen["adapter_version"], "--session-id", "gen-session"])
        # No validate/review-pack-build -- asset is at CANDIDATE_REGISTERED, not OBSERVING.
        result = run_cli(["observe", "--store-root", store_root, "--run-id", run_id,
                           "--candidate-sha256", gen["candidate_sha256"]])
        assert not result["ok"]
        assert "Illegal transition" in result["error"]


def test_content_lint_passes_a_real_off_the_clock_file():
    from pathlib import Path as _P
    real_file = (_P(__file__).resolve().parents[2] / "src" / "content" / "blog"
                 / "the-tent-i-almost-didnt-bring.md")
    result = run_cli(["content-lint", "--file", str(real_file)])
    assert result["ok"], result


def test_content_lint_fails_bad_synthetic_file(tmp_path):
    bad_file = tmp_path / "bad.md"
    bad_file.write_text(
        '---\ncategory: "Life outside the nook"\n---\n'
        '<div class="photo-strip">\n  <figure class="polaroid"><img src="x.jpg" /></figure>\n</div>\n',
        encoding="utf-8",
    )
    result = run_cli(["content-lint", "--file", str(bad_file)])
    assert not result["ok"]
    assert any("photo-strip" in r for r in result["reasons"])


def test_content_lint_reports_error_for_missing_file():
    result = run_cli(["content-lint", "--file", "/nonexistent/path.md"])
    assert not result["ok"]
    assert "error" in result


def test_content_lint_dir_batch_mode_against_real_blog_directory():
    from pathlib import Path as _P
    blog_dir = _P(__file__).resolve().parents[2] / "src" / "content" / "blog"
    result = run_cli(["content-lint", "--dir", str(blog_dir)])
    assert result["ok"], [r for r in result["results"] if not r["ok"]]
    skipped = [r for r in result["results"] if r.get("skipped")]
    linted = [r for r in result["results"] if not r.get("skipped")]
    # 5 Guides posts (Desk fixes/Kitchen fixes) are out of scope and skipped;
    # 10 Off the Clock posts are actually linted and must all pass.
    assert len(skipped) == 5
    assert len(linted) == 10
    assert all(r["ok"] for r in linted)


def test_generate_rejects_unimplemented_adapter():
    """"huggingface" graduated to a real adapter in Commit 5 — use a name
    that is genuinely still outside AVAILABLE_ADAPTERS to test rejection."""
    with tempfile.TemporaryDirectory() as d:
        result = run_cli(["generate", "--store-root", str(Path(d) / "store"),
                           "--spec", "x", "--prompt", "y", "--adapter", "openai"])
        assert not result["ok"]
        assert "not available yet" in result["error"]


def test_spec_lock_rejects_vague_requirement():
    with tempfile.TemporaryDirectory() as d:
        bad = dict(SAMPLE_CONTRACT)
        bad["requirements"] = [
            {"requirement_id": "r1", "type": "composition", "statement": "looks good", "critical": True}
        ]
        contract_path = Path(d) / "contract.json"
        contract_path.write_text(json.dumps(bad))
        result = run_cli(["spec-lock", "--store-root", str(Path(d) / "store"),
                           "--contract", str(contract_path)])
        assert not result["ok"]
        assert result["vague_requirement_ids"] == ["r1"]


def test_cannot_register_before_generate():
    """Enforces the state machine through the real CLI, not just in isolation:
    spec locked + prompt compiled, but generate/quarantine was never called, so
    the state is still PROMPT_COMPILED, not GENERATING -> register must reject."""
    with tempfile.TemporaryDirectory() as d:
        store_root = str(Path(d) / "store")
        contract_path = Path(d) / "contract.json"
        contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
        run_id = "test-run"
        spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id,
                         "--contract", str(contract_path)])
        assert spec["ok"], spec
        prompt = run_cli(["prompt-compile", "--store-root", store_root, "--run-id", run_id,
                           "--spec", spec["spec_sha256"]])
        assert prompt["ok"], prompt
        result = run_cli(["register", "--store-root", store_root, "--run-id", run_id,
                           "--session-id", "test-session",
                           "--spec", spec["spec_sha256"],
                           "--prompt", prompt["prompt_sha256"], "--candidate-sha256", "deadbeef",
                           "--adapter-version", "stub-0.1.0"])
        assert not result["ok"]
        assert "Illegal transition" in result["error"]


def test_register_without_session_id_returns_graceful_error_not_a_crash(tmp_path):
    """Regression test for a real bug Commit 13's canary-run uncovered:
    GenerationAttempt.generator_session_id is a required (non-Optional)
    str field, so omitting --session-id used to raise a raw, unhandled
    pydantic ValidationError instead of the module's own stated
    {"ok": false, "error": ...} contract."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-register-no-session"

    spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id, "--contract", str(contract_path)])
    prompt = run_cli(["prompt-compile", "--store-root", store_root, "--run-id", run_id,
                       "--spec", spec["spec_sha256"]])
    gen = run_cli(["generate", "--store-root", store_root, "--run-id", run_id,
                    "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"], "--adapter", "stub"])

    result = run_cli(["register", "--store-root", store_root, "--run-id", run_id,
                       "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"],
                       "--candidate-sha256", gen["candidate_sha256"], "--adapter-version", gen["adapter_version"]])
    assert not result["ok"]
    assert "session-id" in result["error"].lower()


def test_generate_dispatches_to_huggingface_adapter(monkeypatch, tmp_path):
    """cmd_generate must actually route to the huggingface adapter module
    (not silently fall back to stub) when --adapter huggingface is passed.
    Network is never touched — the module's own client factory is patched to
    a fake client, exercising the real generate()/cmd_generate() code path."""
    from PIL import Image

    from nookguard.adapters import huggingface as hf_adapter

    def fake_generate(prompt_text, **kwargs):
        img_path = tmp_path / "fake.png"
        Image.new("RGB", (8, 8), color=(1, 2, 3)).save(img_path)
        import io
        from PIL import Image as I
        buf = io.BytesIO()
        I.open(img_path).convert("RGB").save(buf, "JPEG", quality=88)
        return buf.getvalue()

    monkeypatch.setattr(hf_adapter, "generate", fake_generate)

    with tempfile.TemporaryDirectory() as d:
        store_root = str(Path(d) / "store")
        contract_path = Path(d) / "contract.json"
        contract_path.write_text(json.dumps(SAMPLE_CONTRACT))

        run_id = "test-run-hf"
        spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id,
                         "--contract", str(contract_path)])
        assert spec["ok"], spec
        prompt = run_cli(["prompt-compile", "--store-root", store_root, "--run-id", run_id,
                           "--spec", spec["spec_sha256"]])
        assert prompt["ok"], prompt

        # Commit 19, requirement 7: real (non-stub) generation now gates on a
        # real Claude CLI auth-check first. This test is about adapter
        # dispatch, not auth-gating (that has its own dedicated tests in
        # test_review_retry.py), so it opts out via --skip-auth-check --
        # exactly what that flag exists for.
        gen = run_cli(["generate", "--store-root", store_root, "--run-id", run_id,
                        "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"],
                        "--adapter", "huggingface", "--skip-auth-check"])
        assert gen["ok"], gen
        assert gen["adapter_version"] == hf_adapter.ADAPTER_VERSION
        assert gen["artifact_uri"].endswith(".jpg")


# ---- integrate / preview-capture / preview-review (Commit 10) ----

def _write_html(html: str, tmp_path: Path) -> str:
    p = tmp_path / "page.html"
    p.write_text(html, encoding="utf-8")
    return p.as_uri()


def _drive_to_semantic_pass(monkeypatch, store_root: str, run_id: str, contract_path: Path) -> str:
    """Shared setup: reaches SEMANTIC_PASS through the real CLI with the
    Claude review-agent calls monkeypatched, same pattern as
    test_full_pipeline_through_observe_judge_to_semantic_pass above. Returns
    the candidate_sha256, left at SEMANTIC_PASS (not yet integrated)."""
    import nookguard.cli as cli_module
    from nookguard.schemas import BlindObservation, ContractJudgment, RequirementJudgment, RequirementResult

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

    monkeypatch.setattr(cli_module, "run_observer_session", fake_observer)
    monkeypatch.setattr(cli_module, "run_judge_session", fake_judge)

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
    run_cli(["observe", "--store-root", store_root, "--run-id", run_id, "--candidate-sha256", candidate_sha])
    judge = run_cli(["judge", "--store-root", store_root, "--run-id", run_id, "--candidate-sha256", candidate_sha])
    assert judge["result"] == "semantic_pass", judge
    return candidate_sha


def _drive_to_observing(store_root: str, run_id: str, contract_path: Path) -> str:
    """Commit 23: reaches OBSERVING through the real CLI with no review-agent
    calls at all (nothing to monkeypatch -- spec-lock through review-pack-
    build never touches an executor). Returns candidate_sha256."""
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
    return candidate_sha


def _write_response_file(tmp_path: Path, name: str, payload: dict) -> str:
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def _submit_custody_args(prepared: dict, response_file: str, *, pack_key: str = "review_pack_sha256",
                          session_id: str = "test-reviewer-session") -> list:
    """Commit 24: builds the --containment-id/--reviewer-session-id/
    --raw-response-sha256/--review-pack-sha256(or --contact-sheet-sha256)
    flags every *-submit command now requires, from a real *-prepare
    response and the real response-file bytes already on disk -- this is
    exactly what a real caller must compute, not a shortcut around the
    custody chain. `pack_key` is 'review_pack_sha256' for observe/judge or
    'contact_sheet_sha256' for preview-review."""
    from nookguard.hashing import sha256_bytes
    raw_bytes = Path(response_file).read_bytes()
    flag = "--" + pack_key.replace("_", "-")
    return [
        "--containment-id", prepared["containment_id"],
        "--reviewer-session-id", session_id,
        "--raw-response-sha256", sha256_bytes(raw_bytes),
        flag, prepared[pack_key],
    ]


# ---- Commit 23: observe-prepare/-submit, judge-prepare/-submit, preview-
# review-prepare/-submit -- the agent-native path a live orchestrating
# agent (this Cowork session, or a scheduled task) uses instead of the
# separate-Claude-Code-CLI-login executor. No monkeypatching of run_*_
# session is needed for these -- prepare/submit never call an executor at
# all, so a real --response-file is genuinely exercising the same finalize_
# * validation logic the atomic commands use. ----

def test_observe_prepare_returns_real_system_prompt_and_image_path(tmp_path):
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    candidate_sha = _drive_to_observing(store_root, "run-op1", contract_path)

    prepared = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                         "--role", "blind_a"])
    assert prepared["ok"], prepared
    assert prepared["role"] == "blind_a"
    assert "blind visual observer" in prepared["system_prompt"].lower()
    assert Path(prepared["image_path"]).exists()


def test_observe_prepare_rejects_unknown_role(tmp_path):
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    candidate_sha = _drive_to_observing(store_root, "run-op2", contract_path)
    result = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                       "--role", "bogus_role"])
    assert not result["ok"]


def test_observe_submit_waits_for_both_roles_then_transitions_to_judging(tmp_path):
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-os1"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    prepared_a = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                           "--role", "blind_a"])
    assert prepared_a["ok"], prepared_a
    response_a = _write_response_file(tmp_path, "blind_a.json", {"overall_summary_for_humans": "sees a desk"})
    first = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                      "--candidate-sha256", candidate_sha,
                      "--role", "blind_a", "--response-file", response_a,
                      *_submit_custody_args(prepared_a, response_a)])
    assert first["ok"], first
    assert first.get("waiting_for") == "adversarial_b"

    prepared_b = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                           "--role", "adversarial_b"])
    assert prepared_b["ok"], prepared_b
    response_b = _write_response_file(tmp_path, "adversarial_b.json", {"overall_summary_for_humans": "sees a desk too"})
    second = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha,
                       "--role", "adversarial_b", "--response-file", response_b,
                       *_submit_custody_args(prepared_b, response_b)])
    assert second["ok"], second
    assert second["state"] == "judging"
    assert set(second["observations"].keys()) == {"blind_a", "adversarial_b"}


def test_observe_submit_either_order_reaches_judging(tmp_path):
    """Order independence: submitting adversarial_b first, then blind_a,
    must reach the same JUDGING outcome."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-os2"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    prepared_b = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                           "--role", "adversarial_b"])
    response_b = _write_response_file(tmp_path, "adversarial_b.json", {})
    run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
             "--candidate-sha256", candidate_sha,
             "--role", "adversarial_b", "--response-file", response_b,
             *_submit_custody_args(prepared_b, response_b)])
    prepared_a = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                           "--role", "blind_a"])
    response_a = _write_response_file(tmp_path, "blind_a.json", {})
    second = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha,
                       "--role", "blind_a", "--response-file", response_a,
                       *_submit_custody_args(prepared_a, response_a)])
    assert second["state"] == "judging"


def test_observe_submit_invalid_response_transitions_to_review_error(tmp_path):
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-os3"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    prepared = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                         "--role", "blind_a"])
    bad_response = tmp_path / "bad.json"
    bad_response.write_text("not json at all", encoding="utf-8")
    result = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha,
                       "--role", "blind_a", "--response-file", str(bad_response),
                       *_submit_custody_args(prepared, str(bad_response))])
    assert not result["ok"]
    assert result["role"] == "blind_a"

    # State machine reflects the failure for real -- a second submit attempt
    # (even a valid one) is correctly rejected, matching the atomic
    # observe command's own all-or-nothing failure behavior. The state
    # check runs before any custody validation, so placeholder custody
    # values are fine here -- this call is rejected before they'd matter.
    good_response = _write_response_file(tmp_path, "good.json", {})
    retry = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                      "--candidate-sha256", candidate_sha,
                      "--role", "adversarial_b", "--response-file", good_response,
                      "--containment-id", "placeholder", "--reviewer-session-id", "placeholder",
                      "--raw-response-sha256", "placeholder", "--review-pack-sha256", "placeholder"])
    assert not retry["ok"]


def test_judge_prepare_requires_judging_state(tmp_path):
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    candidate_sha = _drive_to_observing(store_root, "run-jp1", contract_path)

    too_early = run_cli(["judge-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha])
    assert not too_early["ok"]


def test_full_pipeline_via_prepare_submit_reaches_semantic_pass(tmp_path):
    """The real, complete agent-native path this commit exists for: observe-
    prepare/-submit for both roles, then judge-prepare/-submit -- no
    monkeypatching of run_observer_session/run_judge_session anywhere,
    since prepare/submit never call an executor. This is the CLI-level
    proof that the split reaches the exact same SEMANTIC_PASS outcome the
    atomic observe/judge commands do."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-full-ps"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    for role in ("blind_a", "adversarial_b"):
        prepared = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                             "--role", role])
        assert prepared["ok"], prepared
        response_file = _write_response_file(tmp_path, f"{role}.json", {"overall_summary_for_humans": "ok"})
        submitted = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                              "--candidate-sha256", candidate_sha,
                              "--role", role, "--response-file", response_file,
                              *_submit_custody_args(prepared, response_file)])
        assert submitted["ok"], submitted

    judge_prepared = run_cli(["judge-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha])
    assert judge_prepared["ok"], judge_prepared
    assert "requirements" in judge_prepared["payload_json"]

    judge_response = _write_response_file(tmp_path, "judge.json", {
        "requirements": [{"requirement_id": "r1", "result": "true", "evidence_observation_ids": [],
                           "confidence": 0.9, "concise_reason": "tape measure seen"}],
        "forbidden_object_findings": [],
    })
    judged = run_cli(["judge-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha,
                       "--response-file", judge_response,
                       *_submit_custody_args(judge_prepared, judge_response)])
    assert judged["ok"], judged
    assert judged["result"] == "semantic_pass"


def test_judge_submit_invalid_response_transitions_to_review_error(tmp_path):
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-js1"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    for role in ("blind_a", "adversarial_b"):
        prepared = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                             "--role", role])
        response_file = _write_response_file(tmp_path, f"{role}.json", {})
        run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                 "--candidate-sha256", candidate_sha,
                 "--role", role, "--response-file", response_file,
                 *_submit_custody_args(prepared, response_file)])

    judge_prepared = run_cli(["judge-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha])
    assert judge_prepared["ok"], judge_prepared
    bad_response = tmp_path / "bad_judge.json"
    bad_response.write_text("garbage", encoding="utf-8")
    result = run_cli(["judge-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha,
                       "--response-file", str(bad_response),
                       *_submit_custody_args(judge_prepared, str(bad_response))])
    assert not result["ok"]
    assert result["role"] == "judge"


def test_preview_review_prepare_and_submit_reaches_preview_review_pass(monkeypatch, tmp_path):
    """Drives through integrate/preview-capture using the atomic observe/
    judge (monkeypatched, matching test_full_pipeline_through_preview_
    review_to_pass's own setup) since those aren't this commit's concern,
    then exercises the NEW preview-review-prepare/-submit pair for real,
    with no run_page_review_session monkeypatch at all."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-preview-prepare-submit"

    candidate_sha = _drive_to_semantic_pass(monkeypatch, store_root, run_id, contract_path)
    run_cli(["integrate", "--store-root", store_root, "--run-id", run_id,
             "--candidate-sha256", candidate_sha, "--page-url", "https://nestandnook.org/x/"])
    page_url = _write_html("<html><body><h1>Real rendered page</h1></body></html>", tmp_path)
    run_cli(["preview-capture", "--store-root", store_root, "--run-id", run_id,
             "--candidate-sha256", candidate_sha, "--page-url", page_url])

    prepared = run_cli(["preview-review-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha])
    assert prepared["ok"], prepared
    assert Path(prepared["image_path"]).exists()
    assert page_url == prepared["page_url"] or prepared["page_url"]  # real page_url present

    response_file = _write_response_file(tmp_path, "page_review.json", {
        "issues": [], "overall_summary_for_humans": "Clean render, no defects found.",
    })
    submitted = run_cli(["preview-review-submit", "--store-root", store_root, "--run-id", run_id,
                          "--candidate-sha256", candidate_sha,
                          "--response-file", response_file,
                          *_submit_custody_args(prepared, response_file, pack_key="contact_sheet_sha256")])
    assert submitted["ok"], submitted
    assert submitted["result"] == "preview_review_pass"


def test_full_pipeline_through_preview_review_to_pass(monkeypatch, tmp_path):
    """Extends the pipeline from SEMANTIC_PASS through integrate ->
    preview-capture (real Playwright screenshot of a real local page) ->
    preview-review (page-reviewer session monkeypatched, same pattern as the
    observer/judge tests) all the way to PREVIEW_REVIEW_PASS."""
    import nookguard.cli as cli_module
    from nookguard.schemas import PageReviewResult

    def fake_page_reviewer(contact_sheet_path, page_url, viewports_captured, **kwargs):
        return PageReviewResult(
            page_url=page_url, viewports_reviewed=viewports_captured,
            review_session_id="prs1", reviewer_agent_hash="h", context_bundle_sha256="cb",
            issues=[], overall_summary_for_humans="Clean render, no defects found.",
        )

    monkeypatch.setattr(cli_module, "run_page_review_session", fake_page_reviewer)

    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-preview-pass"

    candidate_sha = _drive_to_semantic_pass(monkeypatch, store_root, run_id, contract_path)

    integrated = run_cli(["integrate", "--store-root", store_root, "--run-id", run_id,
                           "--candidate-sha256", candidate_sha, "--page-url", "https://nestandnook.org/x/"])
    assert integrated["ok"], integrated

    page_url = _write_html("<html><body><h1>Real rendered page</h1></body></html>", tmp_path)
    captured = run_cli(["preview-capture", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha, "--page-url", page_url])
    assert captured["ok"], captured
    assert set(captured["viewports"]) == {"desktop", "mobile"}
    assert Path(captured["contact_sheet_path"]).exists()

    reviewed = run_cli(["preview-review", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha])
    assert reviewed["ok"], reviewed
    assert reviewed["result"] == "preview_review_pass"


def test_preview_capture_broken_image_flows_to_preview_review_fail(monkeypatch, tmp_path):
    """A real broken <img> on the captured page, with a page-reviewer session
    that reports zero issues of its own, must still fail -- the deterministic
    PageCaptureReport facts are never overridable by reviewer prose."""
    import nookguard.cli as cli_module
    from nookguard.schemas import PageReviewResult

    def fake_page_reviewer(contact_sheet_path, page_url, viewports_captured, **kwargs):
        return PageReviewResult(
            page_url=page_url, viewports_reviewed=viewports_captured,
            review_session_id="prs2", reviewer_agent_hash="h", context_bundle_sha256="cb", issues=[],
        )

    monkeypatch.setattr(cli_module, "run_page_review_session", fake_page_reviewer)

    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-preview-fail"

    candidate_sha = _drive_to_semantic_pass(monkeypatch, store_root, run_id, contract_path)
    run_cli(["integrate", "--store-root", store_root, "--run-id", run_id,
             "--candidate-sha256", candidate_sha])

    page_url = _write_html(
        '<html><body><img src="totally-missing.png" width="40" height="40"></body></html>', tmp_path,
    )
    captured = run_cli(["preview-capture", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha, "--page-url", page_url])
    assert captured["ok"], captured

    reviewed = run_cli(["preview-review", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha])
    assert reviewed["ok"], reviewed
    assert reviewed["result"] == "preview_review_fail"
    assert any("broken image" in r.lower() for r in reviewed["reasons"])


def test_preview_capture_rejects_when_not_integrated():
    with tempfile.TemporaryDirectory() as d:
        store_root = str(Path(d) / "store")
        contract_path = Path(d) / "contract.json"
        contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
        run_id = "test-run-preview-reject"
        spec = run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id,
                         "--contract", str(contract_path)])
        # Asset is only at SPEC_LOCKED -- nowhere near INTEGRATED.
        result = run_cli(["preview-capture", "--store-root", store_root, "--run-id", run_id,
                           "--candidate-sha256", "deadbeef", "--page-url", "https://example.com/"])
        assert not result["ok"]
        assert "error" in result


def test_preview_review_rejects_when_not_previewed(monkeypatch, tmp_path):
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-preview-review-reject"

    candidate_sha = _drive_to_semantic_pass(monkeypatch, store_root, run_id, contract_path)
    # Never integrated or captured -- asset is at SEMANTIC_PASS, not PREVIEWED.
    result = run_cli(["preview-review", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha])
    assert not result["ok"]
    assert "Illegal transition" in result["error"]


# ---- release / production-verify (Commit 12) ----

def _drive_to_preview_review_pass(monkeypatch, store_root: str, run_id: str, contract_path: Path,
                                   tmp_path: Path) -> str:
    """Shared setup: extends _drive_to_semantic_pass through integrate ->
    preview-capture -> preview-review, landing at PREVIEW_REVIEW_PASS --
    the real starting state `mediactl release` requires."""
    import nookguard.cli as cli_module
    from nookguard.schemas import PageReviewResult

    def fake_page_reviewer(contact_sheet_path, page_url, viewports_captured, **kwargs):
        return PageReviewResult(
            page_url=page_url, viewports_reviewed=viewports_captured,
            review_session_id="prs-release", reviewer_agent_hash="h", context_bundle_sha256="cb", issues=[],
        )

    monkeypatch.setattr(cli_module, "run_page_review_session", fake_page_reviewer)

    candidate_sha = _drive_to_semantic_pass(monkeypatch, store_root, run_id, contract_path)
    run_cli(["integrate", "--store-root", store_root, "--run-id", run_id, "--candidate-sha256", candidate_sha])

    page_url = _write_html("<html><body><h1>Real rendered page</h1></body></html>", tmp_path)
    run_cli(["preview-capture", "--store-root", store_root, "--run-id", run_id,
             "--candidate-sha256", candidate_sha, "--page-url", page_url])
    reviewed = run_cli(["preview-review", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha])
    assert reviewed["result"] == "preview_review_pass", reviewed
    return candidate_sha


def test_full_pipeline_release_and_local_build_production_verify_pass(monkeypatch, tmp_path):
    """Extends the pipeline from PREVIEW_REVIEW_PASS through release (real
    file copy to a content-hashed public path) and production-verify in
    real local-build mode (comparing against a real, populated dist/ dir)
    all the way to PROD_VERIFIED."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-release-pass"

    candidate_sha = _drive_to_preview_review_pass(monkeypatch, store_root, run_id, contract_path, tmp_path)

    public_root = tmp_path / "site-public"  # the site's real public/ directory
    public_dir = public_root / "winnie"  # the specific leaf dir this release goes into
    released = run_cli(["release", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha, "--public-dir", str(public_dir),
                         "--public-url-prefix", "/winnie", "--name-hint", "test-asset-hero"])
    assert released["ok"], released
    assert Path(released["public_path"]).exists()
    assert released["public_url"].startswith("/winnie/test-asset-hero-")
    assert released["release_manifest_sha256"]

    # Simulate a real `astro build` having copied public/ into dist/ verbatim
    # -- dist/ mirrors public_root's subdirectory structure, including winnie/.
    released_bytes = Path(released["public_path"]).read_bytes()
    dist_root = tmp_path / "dist"
    dist_target = dist_root / "winnie" / Path(released["public_path"]).name
    dist_target.parent.mkdir(parents=True)
    dist_target.write_bytes(released_bytes)

    verified = run_cli(["production-verify", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha, "--public-root", str(public_root),
                         "--dist-root", str(dist_root)])
    assert verified["ok"], verified
    assert verified["result"] == "prod_verified"


def test_release_then_stale_dist_bytes_yields_prod_mismatch(monkeypatch, tmp_path):
    """The exact regression fixture from SPEC.md Appendix I: 'Repository
    replacement differs from Cloudflare-served bytes -> FAIL'."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-release-mismatch"

    candidate_sha = _drive_to_preview_review_pass(monkeypatch, store_root, run_id, contract_path, tmp_path)

    public_root = tmp_path / "site-public"
    public_dir = public_root / "winnie"
    released = run_cli(["release", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha, "--public-dir", str(public_dir),
                         "--public-url-prefix", "/winnie", "--name-hint", "test-asset-hero"])
    assert released["ok"], released

    dist_root = tmp_path / "dist"
    dist_target = dist_root / "winnie" / Path(released["public_path"]).name
    dist_target.parent.mkdir(parents=True)
    dist_target.write_bytes(b"stale bytes from an old build")  # deliberately wrong

    verified = run_cli(["production-verify", "--store-root", store_root, "--run-id", run_id,
                         "--candidate-sha256", candidate_sha, "--public-root", str(public_root),
                         "--dist-root", str(dist_root)])
    assert verified["ok"], verified
    assert verified["result"] == "prod_mismatch"
    assert "hash to" in verified["reason"]


def test_release_rejects_when_not_preview_review_pass():
    with tempfile.TemporaryDirectory() as d:
        store_root = str(Path(d) / "store")
        contract_path = Path(d) / "contract.json"
        contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
        run_id = "test-run-release-reject"
        run_cli(["spec-lock", "--store-root", store_root, "--run-id", run_id, "--contract", str(contract_path)])
        # Asset is only at SPEC_LOCKED.
        result = run_cli(["release", "--store-root", store_root, "--run-id", run_id,
                           "--candidate-sha256", "deadbeef", "--public-dir", str(Path(d) / "pub"),
                           "--public-url-prefix", "/winnie", "--name-hint", "x"])
        assert not result["ok"]
        assert "error" in result


def test_production_verify_rejects_when_not_released(monkeypatch, tmp_path):
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "test-run-verify-reject"

    candidate_sha = _drive_to_preview_review_pass(monkeypatch, store_root, run_id, contract_path, tmp_path)
    # Never released -- asset is at PREVIEW_REVIEW_PASS, not RELEASED.
    result = run_cli(["production-verify", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha, "--public-root", str(tmp_path / "pub"),
                       "--dist-root", str(tmp_path / "dist")])
    assert not result["ok"]
    assert "Illegal transition" in result["error"]


# ---- regression-run / canary-run (Commit 13) ----

def test_regression_run_reports_all_ten_fixtures_passing(tmp_path):
    result = run_cli(["regression-run", "--store-root", str(tmp_path / "store")])
    assert result["ok"], result
    assert len(result["results"]) == 10
    assert all(r["passed"] for r in result["results"])


def test_canary_run_completes_full_pipeline_to_prod_verified(monkeypatch, tmp_path):
    """The canary is a smoke test of the pipeline's own WIRING: every step
    calls the real run_cli() entry point, chained exactly like a manual
    invocation would be. Only the Claude review-agent calls are
    monkeypatched (same pattern as every other pipeline test in this file)
    -- Playwright/Pillow/file-copy/hashing all run for real."""
    import nookguard.cli as cli_module
    from nookguard.schemas import (
        BlindObservation,
        ContractJudgment,
        PageReviewResult,
        RequirementJudgment,
        RequirementResult,
    )

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
            review_session_id="prs-canary", reviewer_agent_hash="h", context_bundle_sha256="cb", issues=[],
        )

    monkeypatch.setattr(cli_module, "run_observer_session", fake_observer)
    monkeypatch.setattr(cli_module, "run_judge_session", fake_judge)
    monkeypatch.setattr(cli_module, "run_page_review_session", fake_page_reviewer)

    result = run_cli(["canary-run", "--store-root", str(tmp_path / "store"), "--run-id", "canary-test"])
    assert result["ok"], result
    assert result["candidate_sha256"]
    assert result["release_manifest_sha256"]
    step_names = [s["command"] for s in result["steps"]]
    assert step_names == [
        "spec-lock", "prompt-compile", "generate", "register", "validate", "review-pack-build",
        "observe", "judge", "integrate", "preview-capture", "preview-review", "release",
        "production-verify",
    ]
    assert all(s["ok"] for s in result["steps"])


def test_canary_run_reports_which_step_failed(tmp_path):
    """No monkeypatching here -- the real run_observer_session will fail
    (no Anthropic credentials in this environment), and the canary must
    report exactly where it stopped, not a generic failure."""
    result = run_cli(["canary-run", "--store-root", str(tmp_path / "store"), "--run-id", "canary-fail-test"])
    assert not result["ok"]
    assert "canary failed at" in result["error"]
    assert len(result["steps"]) >= 1


def test_regression_deterministic_mode_matches_existing_regression_run(tmp_path):
    """Commit 20: `mediactl regression --mode deterministic` must produce
    the exact same real per-fixture results as the pre-existing
    `regression-run` command (Commit 13) -- it delegates to the identical
    run_regression_corpus() call, not a reimplementation."""
    legacy = run_cli(["regression-run", "--store-root", str(tmp_path / "store1")])
    new = run_cli(["regression", "--mode", "deterministic", "--store-root", str(tmp_path / "store2")])
    assert new["mode"] == "deterministic"
    assert new["ok"] == legacy["ok"]
    assert [r["fixture_id"] for r in new["results"]] == [r["fixture_id"] for r in legacy["results"]]
    assert [r["passed"] for r in new["results"]] == [r["passed"] for r in legacy["results"]]


def test_regression_live_review_mode_runs_real_corpus_unmocked(tmp_path):
    """No monkeypatching -- confirms the CLI layer actually reaches
    regression_live.py's real corpus (same honest real-environment
    assertion as test_canary_run_reports_which_step_failed and
    test_regression_live.py's own unmocked test)."""
    result = run_cli(["regression", "--mode", "live-review", "--store-root", str(tmp_path / "store")])
    assert result["mode"] == "live-review"
    assert result["fixture_count"] > 0
    assert result["review_process_completed_count"] == 0  # real auth wall, honestly reported
    assert not result["ok"]


def test_regression_unknown_mode_rejected(tmp_path):
    result = run_cli(["regression", "--mode", "bogus-mode", "--store-root", str(tmp_path / "store")])
    assert not result["ok"]


# ---- media-audit / write-path-audit / deploy (Commit 21) ----

def _write_media_file(root: Path, rel: str, content: bytes) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def test_media_audit_clean_against_a_baselined_tree(tmp_path):
    from nookguard.public_media_guard import snapshot_public_media, write_baseline

    site_root = tmp_path / "site"
    _write_media_file(site_root, "public/winnie/hero.jpg", b"legacy-content")
    baseline_path = site_root.parent / "baseline.json"
    write_baseline(snapshot_public_media(site_root), baseline_path)

    # media-audit takes --site-root, not --project-root; baseline_path is an
    # implementation detail of public_media_guard's own DEFAULT_BASELINE_PATH,
    # so this test drives audit_public_media directly through the CLI using a
    # tree where the CLI's own baked-in default baseline doesn't apply --
    # confirmed via the real committed baseline test below instead.
    from nookguard.public_media_guard import audit_public_media
    report = audit_public_media(site_root, baseline_path=baseline_path)
    assert report["ok"] is True


def test_media_audit_cli_flags_new_unapproved_file_against_real_committed_baseline(tmp_path):
    """Drives the real `mediactl media-audit` CLI path (not the library
    function directly) against a fresh site_root that has zero overlap with
    the real committed baseline -- every file found is therefore "new,
    unapproved" by construction, proving the CLI wiring (args.site_root,
    args.store_root_extra) reaches audit_public_media() correctly."""
    site_root = tmp_path / "site"
    _write_media_file(site_root, "public/winnie/brand-new-cli-test.jpg", b"new-content")

    result = run_cli(["media-audit", "--site-root", str(site_root),
                       "--store-root", str(tmp_path / "nookguard_store")])
    assert result["ok"] is False
    assert result["unapproved_count"] == 1
    assert result["unapproved"][0]["path"] == "public/winnie/brand-new-cli-test.jpg"


def test_media_audit_cli_approves_file_released_through_real_store_root(tmp_path):
    from nookguard.hashing import sha256_bytes
    from nookguard.manifest import ReleaseManifestEntry

    site_root = tmp_path / "site"
    p = _write_media_file(site_root, "public/winnie/released.jpg", b"released-bytes")
    real_hash = sha256_bytes(p.read_bytes())

    store_root = tmp_path / "nookguard_store"
    releases_dir = store_root / "releases"
    releases_dir.mkdir(parents=True)
    entry = ReleaseManifestEntry(
        release_id="r1", run_id="run1", asset_id="a1", candidate_sha256=real_hash,
        public_path=str(p), public_url="https://example.com/released.jpg",
    )
    (releases_dir / f"{real_hash}.json").write_text(entry.model_dump_json(), encoding="utf-8")

    result = run_cli(["media-audit", "--site-root", str(site_root), "--store-root", str(store_root)])
    assert result["ok"] is True
    assert result["approved_release_count"] == 1


def test_media_audit_cli_real_site_tree_is_clean():
    """Runs media-audit against the ACTUAL live site/ tree with its real,
    committed baseline and real nookguard_store -- the real gate this
    project will actually run before a deploy. Matches the already-verified
    result from Commit 21 development (344 files, all baseline-unchanged)."""
    from nookguard.public_media_guard import DEFAULT_SITE_ROOT
    result = run_cli(["media-audit", "--site-root", str(DEFAULT_SITE_ROOT)])
    assert result["ok"] is True
    assert result["total_files_scanned"] > 0
    assert result["unapproved_count"] == 0


def test_write_path_audit_cli_real_site_tree():
    from nookguard.public_media_guard import DEFAULT_SITE_ROOT
    result = run_cli(["write-path-audit", "--site-root", str(DEFAULT_SITE_ROOT)])
    assert result["ok"] is True
    assert result["files_scanned"] > 0
    assert result["media_write_count"] == 0


def test_write_path_audit_cli_finds_synthetic_finding(tmp_path):
    site_root = tmp_path / "site"
    site_root.mkdir(parents=True)
    (site_root / "gen_thing.py").write_text(
        "img.save('public/winnie/thing.jpg')\n", encoding="utf-8",
    )
    result = run_cli(["write-path-audit", "--site-root", str(site_root)])
    assert result["ok"] is True
    assert result["media_write_count"] == 1


def test_deploy_cli_refuses_when_public_media_unapproved(tmp_path):
    site_root = tmp_path / "site"
    _write_media_file(site_root, "public/winnie/unapproved.jpg", b"unapproved-content")

    result = run_cli(["deploy", "--site-root", str(site_root),
                       "--store-root", str(tmp_path / "nookguard_store")])
    assert result["ok"] is False
    assert result["reason"] == "unapproved_public_media"


@pytest.mark.xfail(
    reason="Pre-existing, confirmed-unrelated-to-Commit-24 Windows Wrangler crash "
           "(exit code 3221226505, 'Assertion failed: !(handle->flags & "
           "UV_HANDLE_CLOSING)', src/win/async.c line 94). Verified 2026-07-23 by "
           "stashing every Commit 24 change and running this exact test against "
           "clean HEAD (commit 25335c0) -- identical failure, byte-for-byte same "
           "assertion. This is precisely the issue Commit 27 ('Wrangler "
           "investigation and controlled deployment') exists to reproduce outside "
           "pytest and fix; Commit 24 does not touch deploy/wrangler code at all. "
           "strict=True so this marker itself becomes a hard failure (XPASS) the "
           "moment Commit 27's fix lands and this test starts passing again -- "
           "remove the marker then, don't let it linger.",
    strict=True,
)
def test_deploy_cli_real_unmocked_reaches_wrangler_with_real_credentials(tmp_path):
    """Real, unmocked `mediactl deploy` against the actual site tree (whose
    media-audit is confirmed clean above). Updated post-Commit-22 (see
    BUILD-LOG.md): real Cloudflare credentials are now configured on this
    machine, so the credentials gate this test used to stop at
    (cloudflare_credentials_unavailable) now genuinely passes -- see
    test_check_cloudflare_credentials_real_unmocked_call_on_this_machine in
    test_deploy.py for that half of the finding.

    This test proves the OTHER half for real: that a passed credentials
    gate reaches a genuine `wrangler pages deploy` subprocess call using
    those exact credentials, not a mocked one. It deliberately does NOT let
    that real call touch the actual `nestandnook-site` production project
    -- site/dist/ is a real, current production build on this machine, and
    the default --project-name IS the real live site, so running this
    unmocked would otherwise trigger a genuine production deployment as a
    side effect of the test suite. Confirmed safe alternative (manually
    verified 2026-07-22 outside pytest first, see BUILD-LOG.md Commit 23
    entry): `wrangler pages deploy <dir> --project-name <name-that-does-
    not-exist-in-the-account>` fails cleanly with a real Cloudflare error
    (exit code 1, 'The Pages project ... does not exist') and creates or
    modifies nothing -- so pointing --project-name at a nonexistent name
    and --dist-dir at a disposable tmp_path directory gives a real,
    unmocked, end-to-end proof that credentials+wrangler work, with zero
    risk to the live site."""
    from nookguard.public_media_guard import DEFAULT_SITE_ROOT
    throwaway_dist = tmp_path / "throwaway_dist"
    throwaway_dist.mkdir()
    (throwaway_dist / "index.html").write_text("<!doctype html><title>nookguard test probe</title>")

    result = run_cli([
        "deploy", "--site-root", str(DEFAULT_SITE_ROOT),
        "--dist-dir", str(throwaway_dist),
        "--project-name", "nookguard-test-nonexistent-project-xyz",
    ])
    # Must NOT stop at the credentials gate anymore -- real credentials are
    # configured and available.
    assert result.get("reason") != "cloudflare_credentials_unavailable"
    # Must NOT report a fabricated success -- there is no real deployment
    # (the project genuinely doesn't exist in the account).
    assert result["ok"] is False
    assert result["reason"] == "nonzero_exit"
    assert "does not exist" in result["error"]


# ---- Commit 24, requirement 8: reviewer containment and response custody
# tests -- unauthorized mutation, changed response bytes, wrong session ID,
# wrong candidate hash, wrong review-pack hash, and permitted scratch-file
# creation. ----

def test_containment_violation_invalidates_review_and_sets_review_error(monkeypatch, tmp_path):
    """Requirement 2/8: something writing outside the reviewer's scratch
    directory during the reviewer's turn -- exactly the failure mode a
    subagent's own tool-type restriction can't be trusted to prevent --
    must invalidate the review (never be silently accepted), transition
    the asset to REVIEW_ERROR, and leave a tamper-evident
    containment.violation ledger event."""
    import nookguard.cli as cli_module
    fake_site_root = tmp_path / "fake_site"
    (fake_site_root / "src").mkdir(parents=True)
    (fake_site_root / "src" / "existing.txt").write_text("original", encoding="utf-8")
    monkeypatch.setattr(cli_module, "_site_root", lambda args: fake_site_root)

    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-containment-violation"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    prepared = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                         "--role", "blind_a"])
    assert prepared["ok"], prepared

    # Unauthorized mutation: a file outside the designated reviewer scratch
    # directory changes during the reviewer's "turn".
    (fake_site_root / "src" / "existing.txt").write_text("mutated by something outside scratch", encoding="utf-8")

    response = _write_response_file(tmp_path, "blind_a.json", {"overall_summary_for_humans": "sees a desk"})
    result = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha,
                       "--role", "blind_a", "--response-file", response,
                       *_submit_custody_args(prepared, response)])
    assert not result["ok"], result
    assert result["reason"] == "containment_violation"
    assert any("existing.txt" in p for paths in result["violations"].values() for p in paths)

    from nookguard.state_machine import AssetState
    from nookguard.store import Store
    store = Store(Path(store_root))
    assert store.get_state(SAMPLE_CONTRACT["asset_id"]) == AssetState.REVIEW_ERROR.value

    ledger_path = Path(store_root) / "events.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    violation_events = [e for e in events if e["event_type"] == "containment.violation"]
    assert len(violation_events) == 1, events
    assert violation_events[0]["payload"]["candidate_sha256"] == candidate_sha


def test_observe_submit_rejects_changed_response_bytes(tmp_path):
    """Requirement 5/8: --raw-response-sha256 must match the ACTUAL bytes in
    --response-file. A caller supplying a hash that doesn't correspond to
    the real file (simulating substitution/tampering between prepare and
    submit) must be rejected before the response is ever parsed or
    trusted."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-changed-bytes"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    prepared = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                         "--role", "blind_a"])
    assert prepared["ok"], prepared
    response = _write_response_file(tmp_path, "blind_a.json", {"overall_summary_for_humans": "sees a desk"})

    result = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha,
                       "--role", "blind_a", "--response-file", response,
                       "--containment-id", prepared["containment_id"],
                       "--reviewer-session-id", "test-reviewer-session",
                       "--raw-response-sha256", "0" * 64,  # deliberately wrong
                       "--review-pack-sha256", prepared["review_pack_sha256"]])
    assert not result["ok"], result
    assert result["reason"] == "raw_response_hash_mismatch"

    # The asset must still be in OBSERVING (this call never even reached
    # containment closure or the state machine) so a real, valid retry can
    # still succeed.
    from nookguard.state_machine import AssetState
    from nookguard.store import Store
    store = Store(Path(store_root))
    assert store.get_state(SAMPLE_CONTRACT["asset_id"]) == AssetState.OBSERVING.value


def test_observe_submit_rejects_missing_reviewer_session_id(tmp_path):
    """Requirement 5/8: an empty/missing --reviewer-session-id (a 'wrong'/
    absent session ID) must be rejected -- every submitted review must be
    attributable to a real reviewer session, never anonymous."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-wrong-session"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    prepared = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                         "--role", "blind_a"])
    assert prepared["ok"], prepared
    response = _write_response_file(tmp_path, "blind_a.json", {"overall_summary_for_humans": "sees a desk"})
    from nookguard.hashing import sha256_bytes
    raw_sha = sha256_bytes(Path(response).read_bytes())

    result = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha,
                       "--role", "blind_a", "--response-file", response,
                       "--containment-id", prepared["containment_id"],
                       "--reviewer-session-id", "   ",  # blank/whitespace-only -- treated as missing
                       "--raw-response-sha256", raw_sha,
                       "--review-pack-sha256", prepared["review_pack_sha256"]])
    assert not result["ok"], result
    assert result["reason"] == "missing_session_id"


def test_observe_submit_rejects_unregistered_candidate_hash(tmp_path):
    """Requirement 5/8 ('wrong candidate hash'): submitting against a
    candidate_sha256 that was never registered/prepared for this store must
    be rejected cleanly, never silently accepted as if it were the real
    reviewed candidate."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-wrong-candidate"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    prepared = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                         "--role", "blind_a"])
    assert prepared["ok"], prepared
    response = _write_response_file(tmp_path, "blind_a.json", {"overall_summary_for_humans": "sees a desk"})

    wrong_candidate_sha = "f" * 64  # well-formed sha256 shape, but never registered
    result = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", wrong_candidate_sha,
                       "--role", "blind_a", "--response-file", response,
                       *_submit_custody_args(prepared, response)])
    assert not result["ok"], result
    assert "error" in result

    # The real candidate's own state is untouched by the rejected attempt.
    from nookguard.state_machine import AssetState
    from nookguard.store import Store
    store = Store(Path(store_root))
    assert store.get_state(SAMPLE_CONTRACT["asset_id"]) == AssetState.OBSERVING.value


def test_observe_submit_rejects_wrong_review_pack_hash(tmp_path):
    """Requirement 5/8: a --review-pack-sha256 that doesn't match the real
    review pack this candidate/role actually produces must be rejected --
    this is the check that catches a caller (or reviewer) claiming to have
    reviewed different requirements/forbidden-objects than what was
    genuinely shown."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-wrong-pack-hash"
    candidate_sha = _drive_to_observing(store_root, run_id, contract_path)

    prepared = run_cli(["observe-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha,
                         "--role", "blind_a"])
    assert prepared["ok"], prepared
    response = _write_response_file(tmp_path, "blind_a.json", {"overall_summary_for_humans": "sees a desk"})
    from nookguard.hashing import sha256_bytes
    raw_sha = sha256_bytes(Path(response).read_bytes())

    result = run_cli(["observe-submit", "--store-root", store_root, "--run-id", run_id,
                       "--candidate-sha256", candidate_sha,
                       "--role", "blind_a", "--response-file", response,
                       "--containment-id", prepared["containment_id"],
                       "--reviewer-session-id", "test-reviewer-session",
                       "--raw-response-sha256", raw_sha,
                       "--review-pack-sha256", "1" * 64])  # deliberately wrong
    assert not result["ok"], result
    assert result["reason"] == "review_pack_hash_mismatch"

    from nookguard.state_machine import AssetState
    from nookguard.store import Store
    store = Store(Path(store_root))
    assert store.get_state(SAMPLE_CONTRACT["asset_id"]) == AssetState.OBSERVING.value


def test_permitted_scratch_file_creation_does_not_trigger_containment_violation(monkeypatch, tmp_path):
    """Requirement 4/8: a reviewer creating a crop file *inside* its own
    scratch directory is legitimate and must NOT be flagged -- containment
    only rejects changes OUTSIDE the scratch dir. Simulates the crop the
    way a real preview reviewer would produce one, then confirms submit
    still succeeds cleanly with no containment violation."""
    store_root = str(tmp_path / "store")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(SAMPLE_CONTRACT))
    run_id = "run-permitted-scratch"

    candidate_sha = _drive_to_semantic_pass(monkeypatch, store_root, run_id, contract_path)
    run_cli(["integrate", "--store-root", store_root, "--run-id", run_id,
             "--candidate-sha256", candidate_sha, "--page-url", "https://nestandnook.org/x/"])
    page_url = _write_html("<html><body><h1>Real rendered page</h1></body></html>", tmp_path)
    run_cli(["preview-capture", "--store-root", store_root, "--run-id", run_id,
             "--candidate-sha256", candidate_sha, "--page-url", page_url])

    prepared = run_cli(["preview-review-prepare", "--store-root", store_root, "--candidate-sha256", candidate_sha])
    assert prepared["ok"], prepared

    # A permitted crop, created exactly where requirement 4 says it's
    # allowed: inside the reviewer's own scratch directory.
    scratch_dir = Path(prepared["reviewer_scratch_dir"])
    (scratch_dir / "crop_region_1.png").write_bytes(b"fake-crop-bytes")

    response_file = _write_response_file(tmp_path, "page_review.json", {
        "issues": [], "overall_summary_for_humans": "Clean render, no defects found.",
    })
    submitted = run_cli(["preview-review-submit", "--store-root", store_root, "--run-id", run_id,
                          "--candidate-sha256", candidate_sha,
                          "--response-file", response_file,
                          *_submit_custody_args(prepared, response_file, pack_key="contact_sheet_sha256")])
    assert submitted["ok"], submitted
    assert submitted["result"] == "preview_review_pass"
