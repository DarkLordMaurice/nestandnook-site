from nookguard.aggregator import aggregate
from nookguard.schemas import (
    AssetContract,
    BlindObservation,
    ContractJudgment,
    EntityObservation,
    ForbiddenObjectFinding,
    MediaType,
    Requirement,
    RequirementJudgment,
    RequirementResult,
    RiskTier,
)
from nookguard.state_machine import AssetState


def _contract(risk_tier=RiskTier.TIER_1, requirements=None, forbidden_objects=None,
              identity_constraints=None, continuity_constraints=None) -> AssetContract:
    return AssetContract(
        asset_id="a1", project_id="nest-and-nook", page_id="p1", slot_id="hero",
        media_type=MediaType.IMAGE, risk_tier=risk_tier,
        page_type_contract_version="1", source_excerpt="...", source_excerpt_sha256="x",
        canonical_reference_bundle_sha256="y", subject="Winnie", action="measuring", scene="office",
        planner_session_id="s1", plan_evaluator_session_id="s2",
        requirements=requirements or [], forbidden_objects=forbidden_objects or [],
        identity_constraints=identity_constraints or [], continuity_constraints=continuity_constraints or [],
    )


def _judgment(requirements=None, forbidden_object_findings=None) -> ContractJudgment:
    return ContractJudgment(
        candidate_sha256="c1", spec_sha256="s1", judge_session_id="j1", judge_agent_hash="h1",
        context_bundle_sha256="cb1", requirements=requirements or [],
        forbidden_object_findings=forbidden_object_findings or [],
    )


def _observation(role="blind_a", visible_entities=None) -> BlindObservation:
    return BlindObservation(
        review_id="r1", candidate_sha256="c1", review_pack_sha256="rp1",
        reviewer_agent_hash="h1", reviewer_session_id="s1", context_bundle_sha256="cb1",
        observer_role=role, visible_entities=visible_entities or [],
    )


def _rj(rid, result, evidence_observation_ids=None, evidence_boxes=None) -> RequirementJudgment:
    return RequirementJudgment(
        requirement_id=rid, result=result,
        evidence_observation_ids=evidence_observation_ids or [],
        evidence_boxes=evidence_boxes or [],
    )


def test_all_critical_true_yields_semantic_pass():
    contract = _contract(requirements=[
        Requirement(requirement_id="r1", type="count", statement="exactly 1 cup", critical=True),
    ])
    judgment = _judgment(requirements=[_rj("r1", RequirementResult.TRUE)])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.SEMANTIC_PASS


def test_critical_requirement_false_yields_semantic_fail():
    contract = _contract(requirements=[
        Requirement(requirement_id="r1", type="count", statement="exactly 1 cup", critical=True),
    ])
    judgment = _judgment(requirements=[_rj("r1", RequirementResult.FALSE)])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.SEMANTIC_FAIL
    assert "r1" in result.reasons[0]


def test_critical_requirement_never_judged_yields_semantic_fail():
    """A gap is exactly as dangerous as a false -- never silently pass it."""
    contract = _contract(requirements=[
        Requirement(requirement_id="r1", type="count", statement="exactly 1 cup", critical=True),
    ])
    judgment = _judgment(requirements=[])  # judge never addressed r1
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.SEMANTIC_FAIL


def test_forbidden_object_above_threshold_yields_semantic_fail():
    contract = _contract(forbidden_objects=["logo"])
    judgment = _judgment(forbidden_object_findings=[
        ForbiddenObjectFinding(label="logo", confidence=0.8, source_observation_id="r1"),
    ])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.SEMANTIC_FAIL
    assert "logo" in result.reasons[0]


def test_forbidden_object_below_threshold_does_not_fail_on_that_alone():
    contract = _contract(forbidden_objects=["logo"])
    judgment = _judgment(forbidden_object_findings=[
        ForbiddenObjectFinding(label="logo", confidence=0.2, source_observation_id="r1"),
    ])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.SEMANTIC_PASS


def test_material_requirement_true_without_evidence_yields_fail_evidence():
    contract = _contract(requirements=[
        Requirement(requirement_id="r1", type="material_boundary", statement="wood grain visible", critical=True),
    ])
    judgment = _judgment(requirements=[_rj("r1", RequirementResult.TRUE)])  # no evidence cited
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.FAIL_EVIDENCE


def test_material_requirement_true_with_evidence_does_not_fail_evidence():
    contract = _contract(requirements=[
        Requirement(requirement_id="r1", type="material_boundary", statement="wood grain visible", critical=True),
    ])
    judgment = _judgment(requirements=[_rj("r1", RequirementResult.TRUE, evidence_observation_ids=["obs1"])])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.SEMANTIC_PASS


def test_identity_constraint_without_satisfying_requirement_yields_fail_reference():
    contract = _contract(identity_constraints=["must match Winnie's locked identity"],
                          requirements=[])
    judgment = _judgment(requirements=[])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.FAIL_REFERENCE


def test_identity_constraint_with_satisfying_requirement_passes():
    contract = _contract(
        identity_constraints=["must match Winnie's locked identity"],
        requirements=[Requirement(requirement_id="r1", type="identity", statement="matches Winnie", critical=True)],
    )
    judgment = _judgment(requirements=[_rj("r1", RequirementResult.TRUE, evidence_observation_ids=["obs1"])])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.SEMANTIC_PASS


def test_count_disagreement_between_observers_yields_needs_owner():
    contract = _contract(requirements=[
        Requirement(requirement_id="r1", type="count", statement="cups", critical=False),
    ])
    judgment = _judgment(requirements=[_rj("r1", RequirementResult.TRUE)])
    blind = _observation("blind_a", visible_entities=[EntityObservation(label="cup", count=2, confidence=0.9)])
    adversarial = _observation("adversarial_b",
                                visible_entities=[EntityObservation(label="cup", count=5, confidence=0.9)])
    result = aggregate(contract, judgment, blind, adversarial)
    assert result.state == AssetState.NEEDS_OWNER


def test_count_agreement_does_not_trigger_needs_owner():
    contract = _contract()
    judgment = _judgment()
    blind = _observation("blind_a", visible_entities=[EntityObservation(label="cup", count=2, confidence=0.9)])
    adversarial = _observation("adversarial_b",
                                visible_entities=[EntityObservation(label="cup", count=2, confidence=0.9)])
    result = aggregate(contract, judgment, blind, adversarial)
    assert result.state == AssetState.SEMANTIC_PASS


def test_uncertain_critical_on_tier2_yields_needs_owner():
    contract = _contract(risk_tier=RiskTier.TIER_2, requirements=[
        Requirement(requirement_id="r1", type="identity", statement="matches Winnie", critical=True),
    ])
    judgment = _judgment(requirements=[_rj("r1", RequirementResult.UNCERTAIN)])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.NEEDS_OWNER


def test_uncertain_critical_on_tier0_yields_semantic_fail():
    contract = _contract(risk_tier=RiskTier.TIER_0, requirements=[
        Requirement(requirement_id="r1", type="count", statement="1 cup", critical=True),
    ])
    judgment = _judgment(requirements=[_rj("r1", RequirementResult.UNCERTAIN)])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.SEMANTIC_FAIL


def test_noncritical_score_below_threshold_yields_semantic_fail():
    contract = _contract(requirements=[
        Requirement(requirement_id="r1", type="composition", statement="pleasant framing", critical=False),
        Requirement(requirement_id="r2", type="composition", statement="good lighting", critical=False),
        Requirement(requirement_id="r3", type="composition", statement="balanced colors", critical=False),
    ])
    judgment = _judgment(requirements=[
        _rj("r1", RequirementResult.FALSE), _rj("r2", RequirementResult.FALSE), _rj("r3", RequirementResult.TRUE),
    ])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    assert result.state == AssetState.SEMANTIC_FAIL


def test_aggregation_result_never_asserts_pass_from_free_text():
    """Structural sanity check: aggregate() only ever reads structured
    fields (result/confidence/evidence lists), never any free-text field --
    proven by the fact that ContractJudgment/RequirementJudgment have no
    free-text override field to read in the first place (Commit 2's
    extra="forbid"), so this function cannot possibly branch on one."""
    import inspect
    source = inspect.getsource(aggregate)
    assert "extra_justification" not in source
    assert ".override" not in source.lower()  # no attribute-style read of an override field
    assert "override_reason" not in source.lower()
