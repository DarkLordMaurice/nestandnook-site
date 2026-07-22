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

        gen = run_cli(["generate", "--store-root", store_root, "--run-id", run_id,
                        "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"],
                        "--adapter", "huggingface"])
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
