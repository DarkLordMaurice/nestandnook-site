"""Asset state machine. This is the thing that makes 'a candidate byte change
invalidates review/integration automatically' (Definition of Done, section 46)
actually true — it's not a suggestion, illegal transitions raise.

States and transitions are synthesized from the pipeline described across the
plan (sections 25-37) since the doc doesn't print one master table. If a future
commit needs a state this doesn't have, add it here with a docs/nookguard/
BUILD-LOG.md note explaining why, rather than routing around the machine."""

from __future__ import annotations

from enum import Enum

from .exceptions import InvalidTransitionError


class AssetState(str, Enum):
    SPEC_LOCKED = "spec_locked"
    PROMPT_COMPILED = "prompt_compiled"
    GENERATING = "generating"
    GENERATION_BLOCKED = "generation_blocked"
    CANDIDATE_REGISTERED = "candidate_registered"
    TECHNICAL_VALIDATING = "technical_validating"
    TECHNICAL_FAIL = "technical_fail"
    TECHNICAL_PASS = "technical_pass"
    OBSERVING = "observing"
    JUDGING = "judging"
    SEMANTIC_PASS = "semantic_pass"
    SEMANTIC_FAIL = "semantic_fail"
    FAIL_EVIDENCE = "fail_evidence"
    FAIL_REFERENCE = "fail_reference"
    NEEDS_OWNER = "needs_owner"
    REVIEW_ERROR = "review_error"
    OWNER_APPROVED = "owner_approved"
    OWNER_REJECTED = "owner_rejected"
    INTEGRATED = "integrated"
    PREVIEWED = "previewed"
    PREVIEW_REVIEW_PASS = "preview_review_pass"
    PREVIEW_REVIEW_FAIL = "preview_review_fail"
    RELEASED = "released"
    PROD_VERIFIED = "prod_verified"
    PROD_MISMATCH = "prod_mismatch"


# Terminal-ish failure states that only ever move forward via a brand NEW
# generation attempt (a fresh candidate_sha256), never by editing in place —
# section 27's "no automatic fix in place" rule, enforced structurally: this
# table has no edge from a FAIL state back to a PASS state for the SAME asset
# state machine instance. A repair means a new AssetState() for a new attempt.
_REGENERATE_SOURCES = {
    AssetState.GENERATION_BLOCKED,
    AssetState.TECHNICAL_FAIL,
    AssetState.SEMANTIC_FAIL,
    AssetState.FAIL_EVIDENCE,
    AssetState.FAIL_REFERENCE,
    AssetState.REVIEW_ERROR,
    AssetState.OWNER_REJECTED,
    AssetState.PREVIEW_REVIEW_FAIL,
    AssetState.PROD_MISMATCH,
}

TRANSITIONS: dict[AssetState, set[AssetState]] = {
    AssetState.SPEC_LOCKED: {AssetState.PROMPT_COMPILED},
    AssetState.PROMPT_COMPILED: {AssetState.GENERATING},
    AssetState.GENERATING: {AssetState.GENERATION_BLOCKED, AssetState.CANDIDATE_REGISTERED},
    AssetState.CANDIDATE_REGISTERED: {AssetState.TECHNICAL_VALIDATING},
    AssetState.TECHNICAL_VALIDATING: {AssetState.TECHNICAL_FAIL, AssetState.TECHNICAL_PASS},
    AssetState.TECHNICAL_PASS: {AssetState.OBSERVING},
    # REVIEW_ERROR here too, not just from JUDGING (added Commit 8): an
    # observer session can fail exactly the same way a judge session can —
    # invalid JSON, an interrupted call — and section 29.5 defines
    # REVIEW_ERROR as covering "session interrupted" generally, not just the
    # judge step specifically. See docs/nookguard/BUILD-LOG.md's Commit 8
    # entry for the concrete case that surfaced this gap.
    AssetState.OBSERVING: {AssetState.JUDGING, AssetState.REVIEW_ERROR},
    AssetState.JUDGING: {
        AssetState.SEMANTIC_PASS,
        AssetState.SEMANTIC_FAIL,
        AssetState.FAIL_EVIDENCE,
        AssetState.FAIL_REFERENCE,
        AssetState.NEEDS_OWNER,
        AssetState.REVIEW_ERROR,
    },
    AssetState.NEEDS_OWNER: {AssetState.OWNER_APPROVED, AssetState.OWNER_REJECTED},
    AssetState.OWNER_APPROVED: {AssetState.INTEGRATED},
    AssetState.SEMANTIC_PASS: {AssetState.INTEGRATED},
    AssetState.INTEGRATED: {AssetState.PREVIEWED},
    # REVIEW_ERROR here too, same rationale as OBSERVING's edge above (added
    # Commit 10): the page-reviewer session can fail the identical way any
    # other agent session can -- invalid JSON, an interrupted call -- and
    # section 29.5's "session interrupted -> REVIEW_ERROR" isn't role-scoped.
    AssetState.PREVIEWED: {AssetState.PREVIEW_REVIEW_PASS, AssetState.PREVIEW_REVIEW_FAIL,
                            AssetState.REVIEW_ERROR},
    AssetState.PREVIEW_REVIEW_PASS: {AssetState.RELEASED},
    AssetState.RELEASED: {AssetState.PROD_VERIFIED, AssetState.PROD_MISMATCH},
}


def is_regenerate_source(state: AssetState) -> bool:
    """True if the only legal way forward from this state is a brand new
    generation attempt (new candidate_sha256), not an in-place fix."""
    return state in _REGENERATE_SOURCES


def transition(current: AssetState, target: AssetState, *, asset_id: str = "") -> AssetState:
    """Validate and perform a state transition. Raises InvalidTransitionError on
    any move not present in TRANSITIONS — this is the enforcement point hook
    H001-style callers should route through instead of setting state directly."""
    allowed = TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError(current.value, target.value, asset_id)
    return target


def legal_next_states(current: AssetState) -> set[AssetState]:
    return set(TRANSITIONS.get(current, set()))
