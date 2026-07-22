"""Code aggregator (Commit 8) — implements the section 29.5 policy table.
This is the ONLY place a release decision is computed. A ContractJudgment
never carries an overall pass field (Commit 2's schema already structurally
forbids it) and a judge session's prose is never read for a verdict — this
module reads only structured fields (RequirementJudgment.result, confidence,
evidence lists; ForbiddenObjectFinding.confidence) and returns a deterministic
AssetState. No narrative override is possible because there is no code path
here that reads free text and lets it change the outcome."""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import (
    AssetContract,
    BlindObservation,
    ContractJudgment,
    RequirementResult,
    RiskTier,
)
from .state_machine import AssetState

FORBIDDEN_OBJECT_CONFIDENCE_THRESHOLD = 0.6
NONCRITICAL_PASS_THRESHOLD = 0.6  # fraction of noncritical requirements judged true
EVIDENCE_REQUIRED_TYPES = {"material_boundary", "relationship"}
IDENTITY_REFERENCE_TYPES = {"identity", "continuity"}


@dataclass
class AggregationResult:
    state: AssetState
    reasons: list[str] = field(default_factory=list)


def aggregate(
    contract: AssetContract,
    judgment: ContractJudgment,
    blind_observation: BlindObservation,
    adversarial_observation: BlindObservation,
) -> AggregationResult:
    reasons: list[str] = []

    by_id = {r.requirement_id: r for r in judgment.requirements}
    critical_ids = {r.requirement_id for r in contract.requirements if r.critical}
    missing_critical = critical_ids - set(by_id.keys())
    if missing_critical:
        # A critical requirement the judge never addressed at all is exactly
        # as dangerous as one judged false — never treat a gap as a pass.
        return AggregationResult(
            AssetState.SEMANTIC_FAIL,
            [f"Critical requirement(s) {sorted(missing_critical)} were never judged"],
        )

    # Rule: any critical requirement = false -> FAIL
    false_critical = [rid for rid in critical_ids if by_id[rid].result == RequirementResult.FALSE]
    if false_critical:
        return AggregationResult(
            AssetState.SEMANTIC_FAIL,
            [f"Critical requirement(s) {sorted(false_critical)} judged false"],
        )

    # Rule: forbidden object reported >= threshold -> FAIL, no free-text override
    forbidden_hits = [f for f in judgment.forbidden_object_findings
                       if f.confidence >= FORBIDDEN_OBJECT_CONFIDENCE_THRESHOLD]
    if forbidden_hits:
        return AggregationResult(
            AssetState.SEMANTIC_FAIL,
            [f"Forbidden object '{f.label}' reported at confidence {f.confidence}" for f in forbidden_hits],
        )

    # Rule: material/relationship requirement lacks evidence box -> FAIL_EVIDENCE
    req_by_id = {r.requirement_id: r for r in contract.requirements}
    for rid, rj in by_id.items():
        req = req_by_id.get(rid)
        if req is None or req.type not in EVIDENCE_REQUIRED_TYPES:
            continue
        if rj.result == RequirementResult.TRUE and not rj.evidence_observation_ids and not rj.evidence_boxes:
            reasons.append(f"Requirement '{rid}' ({req.type}) judged true with no cited evidence")
            return AggregationResult(AssetState.FAIL_EVIDENCE, reasons)

    # Rule: identity/location reference required but missing -> FAIL_REFERENCE
    if contract.identity_constraints or contract.continuity_constraints:
        identity_reqs = [r for r in contract.requirements if r.type in IDENTITY_REFERENCE_TYPES]
        satisfied = any(
            by_id.get(r.requirement_id) is not None
            and by_id[r.requirement_id].result == RequirementResult.TRUE
            and (by_id[r.requirement_id].evidence_observation_ids or by_id[r.requirement_id].evidence_boxes)
            for r in identity_reqs
        )
        if not identity_reqs or not satisfied:
            return AggregationResult(
                AssetState.FAIL_REFERENCE,
                ["Contract declares identity/continuity constraints but no identity/continuity "
                 "requirement was judged true with cited evidence"],
            )

    # Rule: exact-count observers disagree -> third adjudicator; if still
    # disputed, NEEDS_OWNER. No third-adjudicator session exists yet (that
    # would be a new agent role, out of this commit's scope) -- a real
    # count disagreement between the two independent observers routes
    # straight to NEEDS_OWNER, which has the same practical effect (a human
    # sees it) without fabricating a call to a nonexistent adjudicator.
    count_disagreements = _find_count_disagreements(blind_observation, adversarial_observation)
    if count_disagreements:
        return AggregationResult(
            AssetState.NEEDS_OWNER,
            [f"Observers disagree on count for '{label}': blind={a}, adversarial={b}"
             for label, a, b in count_disagreements],
        )

    # Rule: any critical requirement = uncertain -> NEEDS_OWNER or FAIL by
    # risk policy; never auto-pass. This project's policy: uncertain on a
    # Tier 2+ asset (identity/continuity/relationships/counts, or brand-
    # critical) needs a human; uncertain on Tier 0/1 fails outright rather
    # than silently blocking on an owner queue that isn't gating publish
    # yet (see SPEC.md's standing note on deferred owner gating).
    uncertain_critical = [rid for rid in critical_ids
                           if by_id[rid].result == RequirementResult.UNCERTAIN]
    if uncertain_critical:
        if contract.risk_tier in (RiskTier.TIER_2, RiskTier.TIER_3):
            return AggregationResult(
                AssetState.NEEDS_OWNER,
                [f"Critical requirement(s) {sorted(uncertain_critical)} uncertain on {contract.risk_tier.value}"],
            )
        return AggregationResult(
            AssetState.SEMANTIC_FAIL,
            [f"Critical requirement(s) {sorted(uncertain_critical)} uncertain on {contract.risk_tier.value} "
             "(fails rather than auto-passing an uncertain critical requirement)"],
        )

    # Rule: all critical true; noncritical score above threshold; no
    # forbidden object -> SEMANTIC_PASS
    noncritical_ids = [r.requirement_id for r in contract.requirements if not r.critical]
    if noncritical_ids:
        true_count = sum(1 for rid in noncritical_ids
                          if by_id.get(rid) and by_id[rid].result == RequirementResult.TRUE)
        score = true_count / len(noncritical_ids)
        if score < NONCRITICAL_PASS_THRESHOLD:
            return AggregationResult(
                AssetState.SEMANTIC_FAIL,
                [f"Noncritical requirement score {score:.2f} below threshold {NONCRITICAL_PASS_THRESHOLD}"],
            )

    return AggregationResult(AssetState.SEMANTIC_PASS, ["All critical requirements true, no forbidden objects"])


def _find_count_disagreements(
    blind_observation: BlindObservation, adversarial_observation: BlindObservation,
) -> list[tuple[str, int, int]]:
    blind_counts = {e.label: e.count for e in blind_observation.visible_entities}
    adversarial_counts = {e.label: e.count for e in adversarial_observation.visible_entities}
    disagreements = []
    for label, blind_count in blind_counts.items():
        if label in adversarial_counts and adversarial_counts[label] != blind_count:
            disagreements.append((label, blind_count, adversarial_counts[label]))
    return disagreements
