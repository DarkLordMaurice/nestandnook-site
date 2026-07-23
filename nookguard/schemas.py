"""Pydantic models for NookGuard's core artifacts. Field sets are taken directly
from docs/nookguard/SPEC.md (Appendices B, C, D, H) — do not add convenience
fields that let a model bypass the 'no narrative override' rule (see
ContractJudgment: there is deliberately no free-text override field)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RiskTier(str, Enum):
    TIER_0 = "tier_0_decorative"
    TIER_1 = "tier_1_routine"
    TIER_2 = "tier_2_identity_continuity"
    TIER_3 = "tier_3_brand_critical"


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    SLIDES = "slides"


class Requirement(BaseModel):
    """One atomic, evidence-checkable requirement inside an AssetContract.
    Schema validation rejects vague statements ('looks good', 'cozy') unless the
    'statement' field itself names observable evidence — enforced by the
    validator below, not by convention."""

    requirement_id: str
    type: str  # presence|absence|count|relationship|material_boundary|continuity|identity|narrative|composition|layout
    statement: str
    critical: bool
    evidence_policy: str = "boxes_required"

    def is_vague(self) -> bool:
        vague_terms = {"looks good", "cozy", "matches prompt", "nice", "fits well"}
        return self.statement.strip().lower() in vague_terms


class CountConstraint(BaseModel):
    label: str
    exact_count: Optional[int] = None
    min_count: Optional[int] = None
    max_count: Optional[int] = None


class RelationshipConstraint(BaseModel):
    subject: str
    predicate: str
    object: str
    required: bool = True


class AssetContract(BaseModel):
    """Appendix B — required fields for a locked asset spec."""

    asset_id: str
    project_id: str
    page_id: str
    slot_id: str
    media_type: MediaType
    risk_tier: RiskTier
    page_type_contract_version: str

    source_excerpt: str
    source_excerpt_sha256: str
    canonical_reference_bundle_sha256: str

    subject: str
    action: str
    scene: str

    requirements: list[Requirement] = Field(default_factory=list)
    allowed_objects: list[str] = Field(default_factory=list)
    forbidden_objects: list[str] = Field(default_factory=list)
    count_constraints: list[CountConstraint] = Field(default_factory=list)
    relationship_constraints: list[RelationshipConstraint] = Field(default_factory=list)
    continuity_constraints: list[str] = Field(default_factory=list)
    identity_constraints: list[str] = Field(default_factory=list)
    composition_constraints: list[str] = Field(default_factory=list)
    layout_constraints: dict[str, Any] = Field(default_factory=dict)
    legal_compliance_constraints: list[str] = Field(default_factory=list)
    # Commit 20, requirement 5: when True, cmd_validate (cli.py) passes
    # require_ocr=True to validators/image.py's validate(), which blocks
    # the asset with blocking_reason="VALIDATOR_UNAVAILABLE" if the real
    # OCR engine (validators/ocr.py) could not run. Defaults False so every
    # existing contract/test is unaffected — this is additive, not a
    # behavior change for assets that don't opt in.
    requires_ocr_scan: bool = False

    planner_session_id: str
    plan_evaluator_session_id: str

    created_at: str = Field(default_factory=utcnow_iso)
    locked_at: Optional[str] = None
    spec_sha256: Optional[str] = None

    def validate_requirements_are_concrete(self) -> list[str]:
        """Returns requirement_ids that are vague and must be rejected — the
        doc's rule: 'a requirement must state what evidence would make it true
        or false.'"""
        return [r.requirement_id for r in self.requirements if r.is_vague()]


class GenerationAttempt(BaseModel):
    """Section 27 — one record per generated output, immutable once written."""

    candidate_sha256: str
    asset_id: str
    spec_sha256: str
    prompt_sha256: str
    adapter_version: str
    model_revision: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    generator_session_id: str
    artifact_uri: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utcnow_iso)


class EntityObservation(BaseModel):
    label: str
    count: int
    boxes: list[list[float]] = Field(default_factory=list)
    confidence: float


class RelationshipObservation(BaseModel):
    subject: str
    predicate: str
    object: str
    observation: str
    boxes: list[list[float]] = Field(default_factory=list)


class AnomalyObservation(BaseModel):
    category: str
    severity: str  # critical|major|minor
    observation: str
    boxes: list[list[float]] = Field(default_factory=list)
    confidence: float = 0.0


class BlindObservation(BaseModel):
    """Appendix C. Deliberately carries NO pass/fail or expected-object field —
    the observer session never sees the contract. Do not add one."""

    review_id: str
    candidate_sha256: str
    review_pack_sha256: str
    reviewer_agent_hash: str
    reviewer_session_id: str
    context_bundle_sha256: str
    observer_role: str  # "blind_a" | "adversarial_b"

    people: list[str] = Field(default_factory=list)
    visible_entities: list[EntityObservation] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    relationships: list[RelationshipObservation] = Field(default_factory=list)
    readable_text: list[str] = Field(default_factory=list)
    anomalies: list[AnomalyObservation] = Field(default_factory=list)
    uncertain_regions: list[str] = Field(default_factory=list)
    overall_summary_for_humans: str = ""

    created_at: str = Field(default_factory=utcnow_iso)


class RequirementResult(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNCERTAIN = "uncertain"
    NOT_APPLICABLE = "not_applicable"


class RequirementJudgment(BaseModel):
    requirement_id: str
    result: RequirementResult
    evidence_observation_ids: list[str] = Field(default_factory=list)
    evidence_boxes: list[list[float]] = Field(default_factory=list)
    confidence: float = 0.0
    concise_reason: str = ""

    model_config = ConfigDict(extra="forbid")  # blocks an extra_justification style override field


class ForbiddenObjectFinding(BaseModel):
    label: str
    confidence: float
    source_observation_id: str


class ContractJudgment(BaseModel):
    """Appendix D. No overall pass field on purpose — the code aggregator (see
    aggregator.py, Commit 8) computes the release decision from this data. A
    judge session that tries to add its own pass/fail verdict is out of schema."""

    candidate_sha256: str
    spec_sha256: str
    judge_session_id: str
    judge_agent_hash: str
    context_bundle_sha256: str
    requirements: list[RequirementJudgment] = Field(default_factory=list)
    forbidden_object_findings: list[ForbiddenObjectFinding] = Field(default_factory=list)
    created_at: str = Field(default_factory=utcnow_iso)

    model_config = ConfigDict(extra="forbid")


class PageReviewIssue(BaseModel):
    """One visual/layout defect found on a rendered page contact sheet
    (Commit 10). Deliberately no severity-implies-verdict field beyond
    `severity` itself -- the caller's code decides PREVIEW_REVIEW_PASS/FAIL
    from the list of issues, same 'code decides, model never asserts a
    verdict' pattern as ContractJudgment."""

    category: str  # broken_image|overlapping_elements|text_overflow|missing_element|
    #                spacing_inconsistency|wrong_element_count|other
    severity: str  # critical|major|minor
    description: str
    viewport: str = "unspecified"  # desktop|mobile|unspecified


class PageReviewResult(BaseModel):
    """Appendix A's 'page reviewer' output. No overall pass field, same as
    ContractJudgment -- see docs/nookguard/BUILD-LOG.md's Commit 10 entry
    for the aggregation function that computes PREVIEW_REVIEW_PASS/FAIL from
    this in code."""

    page_url: str
    viewports_reviewed: list[str] = Field(default_factory=list)
    review_session_id: str
    reviewer_agent_hash: str
    context_bundle_sha256: str
    issues: list[PageReviewIssue] = Field(default_factory=list)
    overall_summary_for_humans: str = ""
    created_at: str = Field(default_factory=utcnow_iso)

    model_config = ConfigDict(extra="forbid")


class Event(BaseModel):
    """Appendix H events table, mirrored here for the JSON-lines ledger used
    before Commit 14's D1 backend exists."""

    event_id: str
    run_id: str
    asset_id: Optional[str] = None
    event_type: str
    actor_role: str
    actor_session_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_sha256: str
    created_at: str = Field(default_factory=utcnow_iso)
