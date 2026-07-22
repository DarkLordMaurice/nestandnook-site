"""No real Anthropic API calls -- every test injects a fake `executor`
callable, matching the same dependency-injection pattern already used for
the Hugging Face adapter (Commit 5)."""

import inspect
import json
import tempfile
from pathlib import Path

import pytest

from nookguard.agent_runner import (
    ReviewSessionError,
    _extract_json,
    agent_definition_hash,
    run_judge_session,
    run_observer_session,
)
from nookguard.review_pack import build_review_pack
from nookguard.schemas import AssetContract, MediaType, Requirement, RiskTier


def _contract(**overrides) -> AssetContract:
    base = dict(
        asset_id="a1", project_id="nest-and-nook", page_id="p1", slot_id="hero",
        media_type=MediaType.IMAGE, risk_tier=RiskTier.TIER_2,
        page_type_contract_version="1", source_excerpt="...", source_excerpt_sha256="x",
        canonical_reference_bundle_sha256="y", subject="Winnie", action="measuring", scene="office",
        planner_session_id="s1", plan_evaluator_session_id="s2",
        requirements=[Requirement(requirement_id="r1", type="count",
                                   statement="exactly 1 tape measure visible", critical=True)],
        forbidden_objects=["logo"],
    )
    base.update(overrides)
    return AssetContract(**base)


def _fake_image_path() -> str:
    from PIL import Image
    p = Path(tempfile.mkdtemp()) / "cand.png"
    Image.new("RGB", (16, 16), color=(10, 20, 30)).save(p)
    return str(p)


def _fixed_response(payload: dict):
    def executor(system_prompt, user_content):
        return json.dumps(payload)
    return executor


def _capturing_executor(payload: dict, captured: dict):
    def executor(system_prompt, user_content):
        captured["system_prompt"] = system_prompt
        captured["user_content"] = user_content
        return json.dumps(payload)
    return executor


# ---- run_observer_session ----

def test_run_observer_session_blind_a_parses_valid_response():
    pack = build_review_pack("cand-1", _fake_image_path(), "blind_a")
    obs = run_observer_session(pack, executor=_fixed_response({
        "overall_summary_for_humans": "A tape measure on a desk.",
        "visible_entities": [{"label": "tape measure", "count": 1, "confidence": 0.9}],
    }))
    assert obs.observer_role == "blind_a"
    assert obs.candidate_sha256 == "cand-1"
    assert obs.review_pack_sha256 == pack.review_pack_sha256
    assert obs.visible_entities[0].label == "tape measure"


def test_run_observer_session_adversarial_b_instruction_mentions_taxonomy():
    pack = build_review_pack("cand-1", _fake_image_path(), "adversarial_b")
    captured = {}
    run_observer_session(pack, executor=_capturing_executor({}, captured))
    instruction_text = captured["user_content"][1]["text"]
    assert "failure-taxonomy" in instruction_text.lower() or "taxonomy" in instruction_text.lower()


def test_run_observer_session_blind_a_instruction_has_no_taxonomy_mention():
    pack = build_review_pack("cand-1", _fake_image_path(), "blind_a")
    captured = {}
    run_observer_session(pack, executor=_capturing_executor({}, captured))
    instruction_text = captured["user_content"][1]["text"]
    assert "taxonomy" not in instruction_text.lower()


def test_run_observer_session_sends_image_content_block():
    pack = build_review_pack("cand-1", _fake_image_path(), "blind_a")
    captured = {}
    run_observer_session(pack, executor=_capturing_executor({}, captured))
    assert captured["user_content"][0]["type"] == "image"


def test_run_observer_session_raises_on_invalid_json():
    pack = build_review_pack("cand-1", _fake_image_path(), "blind_a")
    with pytest.raises(ReviewSessionError) as exc_info:
        run_observer_session(pack, executor=lambda sp, uc: "not json at all")
    assert exc_info.value.role == "blind_a"


def test_run_observer_session_raises_on_schema_validation_failure():
    pack = build_review_pack("cand-1", _fake_image_path(), "blind_a")
    bad_payload = {"visible_entities": [{"label": "x", "count": "not-a-number", "confidence": 0.9}]}
    with pytest.raises(ReviewSessionError):
        run_observer_session(pack, executor=_fixed_response(bad_payload))


def test_run_observer_session_signature_has_no_contract_parameter():
    """Structural enforcement check, not just a docstring claim -- Appendix
    C's 'observer never sees the contract' has to be true at the function
    signature level."""
    params = set(inspect.signature(run_observer_session).parameters.keys())
    assert "contract" not in params
    assert "requirements" not in params
    assert "prompt_text" not in params


def test_run_observer_session_handles_code_fenced_response():
    pack = build_review_pack("cand-1", _fake_image_path(), "blind_a")
    fenced = "```json\n" + json.dumps({"overall_summary_for_humans": "fenced"}) + "\n```"
    obs = run_observer_session(pack, executor=lambda sp, uc: fenced)
    assert obs.overall_summary_for_humans == "fenced"


# ---- run_judge_session ----

def test_run_judge_session_parses_valid_response():
    contract = _contract()
    blind = run_observer_session(build_review_pack("c1", _fake_image_path(), "blind_a"),
                                  executor=_fixed_response({}))
    adversarial = run_observer_session(build_review_pack("c1", _fake_image_path(), "adversarial_b"),
                                        executor=_fixed_response({}))
    judgment = run_judge_session(
        contract, "spec-sha-123", blind, adversarial,
        executor=_fixed_response({
            "requirements": [{"requirement_id": "r1", "result": "true",
                               "evidence_observation_ids": [], "confidence": 0.9,
                               "concise_reason": "tape measure seen"}],
            "forbidden_object_findings": [],
        }),
    )
    assert judgment.spec_sha256 == "spec-sha-123"
    assert judgment.candidate_sha256 == "c1"
    assert judgment.requirements[0].result.value == "true"


def test_run_judge_session_raises_on_invalid_json():
    contract = _contract()
    blind = run_observer_session(build_review_pack("c1", _fake_image_path(), "blind_a"),
                                  executor=_fixed_response({}))
    adversarial = run_observer_session(build_review_pack("c1", _fake_image_path(), "adversarial_b"),
                                        executor=_fixed_response({}))
    with pytest.raises(ReviewSessionError) as exc_info:
        run_judge_session(contract, "spec-sha", blind, adversarial, executor=lambda sp, uc: "garbage")
    assert exc_info.value.role == "judge"


def test_run_judge_session_signature_has_no_image_parameter():
    params = set(inspect.signature(run_judge_session).parameters.keys())
    assert "image_path" not in params
    assert "prompt_text" not in params


def test_run_judge_session_result_object_has_no_overall_pass_field():
    contract = _contract()
    blind = run_observer_session(build_review_pack("c1", _fake_image_path(), "blind_a"),
                                  executor=_fixed_response({}))
    adversarial = run_observer_session(build_review_pack("c1", _fake_image_path(), "adversarial_b"),
                                        executor=_fixed_response({}))
    judgment = run_judge_session(contract, "spec-sha", blind, adversarial, executor=_fixed_response({}))
    assert "overall_pass" not in type(judgment).model_fields
    assert "pass" not in type(judgment).model_fields


# ---- agent_definition_hash / _extract_json ----

def test_agent_definition_hash_deterministic():
    d = Path(tempfile.mkdtemp())
    (d / "test_agent.md").write_text("instructions v1", encoding="utf-8")
    h1 = agent_definition_hash("test_agent.md", agents_dir=d)
    h2 = agent_definition_hash("test_agent.md", agents_dir=d)
    assert h1 == h2


def test_agent_definition_hash_changes_with_content():
    d = Path(tempfile.mkdtemp())
    (d / "test_agent.md").write_text("instructions v1", encoding="utf-8")
    h1 = agent_definition_hash("test_agent.md", agents_dir=d)
    (d / "test_agent.md").write_text("instructions v2", encoding="utf-8")
    h2 = agent_definition_hash("test_agent.md", agents_dir=d)
    assert h1 != h2


def test_extract_json_handles_plain_json():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_handles_code_fence_with_json_label():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_raises_on_no_json_object():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("there is no JSON here at all")


def test_real_agent_definition_files_exist_and_hash():
    """Confirms the actual shipped instruction files (not a fixture) are
    present and loadable -- catches a typo'd filename immediately."""
    for filename in ("blind_observer_system_prompt.md", "adversarial_observer_system_prompt.md",
                      "contract_judge_system_prompt.md"):
        h = agent_definition_hash(filename)
        assert len(h) == 64  # sha256 hex digest length
