import pytest
from pydantic import ValidationError

from nookguard.schemas import (
    AssetContract,
    ContractJudgment,
    MediaType,
    Requirement,
    RequirementJudgment,
    RequirementResult,
    RiskTier,
)


def _contract(**overrides) -> AssetContract:
    base = dict(
        asset_id="a1", project_id="nest-and-nook", page_id="p1", slot_id="hero",
        media_type=MediaType.IMAGE, risk_tier=RiskTier.TIER_2,
        page_type_contract_version="1", source_excerpt="...", source_excerpt_sha256="x",
        canonical_reference_bundle_sha256="y", subject="Winnie", action="measuring", scene="office",
        planner_session_id="s1", plan_evaluator_session_id="s2",
    )
    base.update(overrides)
    return AssetContract(**base)


def test_vague_requirement_detected():
    c = _contract(requirements=[
        Requirement(requirement_id="r1", type="composition", statement="looks good", critical=True)
    ])
    assert c.validate_requirements_are_concrete() == ["r1"]


def test_concrete_requirement_not_flagged():
    c = _contract(requirements=[
        Requirement(requirement_id="r1", type="count", statement="exactly 8 cups visible", critical=True)
    ])
    assert c.validate_requirements_are_concrete() == []


def test_requirement_judgment_rejects_narrative_override_field():
    """The doc's 'no narrative override' rule (29.5): extra_justification and
    similar free-text override fields must not be accepted by the schema."""
    with pytest.raises(ValidationError):
        RequirementJudgment(
            requirement_id="r1",
            result=RequirementResult.FALSE,
            extra_justification="but it's fine because the narrative implies it",
        )


def test_contract_judgment_has_no_overall_pass_field():
    fields = ContractJudgment.model_fields
    assert "overall_pass" not in fields
    assert "pass" not in fields
    assert "extra_justification" not in fields
