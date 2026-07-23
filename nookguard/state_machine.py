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
    REVIEW_PENDING = "review_pending"
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
#
# REVIEW_ERROR is deliberately NOT in this set as of Commit 19 -- this is a
# real, considered semantic change, not an oversight. Every OTHER state here
# means "content was actually judged and correctly found bad" -- that is a
# content-level verdict that genuinely must never be reused. REVIEW_ERROR
# means something categorically different: the REVIEW PROCESS ITSELF never
# completed (a live-canary example: a real Anthropic API authentication
# failure mid-`observe`, see docs/nookguard/BUILD-LOG.md's Commit 18 entry)
# -- no content verdict was ever reached, good or bad. Once the underlying
# infrastructure/authentication problem is fixed, retrying review of the
# EXACT SAME, UNCHANGED candidate bytes is not "fixing a bad candidate and
# reusing it" (the actual banana-bread-foil/goat-fence failure mode this
# rule exists to prevent) -- it is simply completing a review that never
# ran. See TRANSITIONS' REVIEW_ERROR -> REVIEW_PENDING -> OBSERVING edges
# below for the state-graph side of this, and cli.py's `cmd_review_retry`
# for the enforced guards (unchanged candidate_sha256, bounded retry count)
# that make sure this can never become a backdoor for reusing bad content.
_REGENERATE_SOURCES = {
    AssetState.GENERATION_BLOCKED,
    AssetState.TECHNICAL_FAIL,
    AssetState.SEMANTIC_FAIL,
    AssetState.FAIL_EVIDENCE,
    AssetState.FAIL_REFERENCE,
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
    # Commit 19 process-recovery path -- see the long comment on
    # _REGENERATE_SOURCES above for why this exists and why it is safe.
    # REVIEW_PENDING has exactly one legal forward edge, back to OBSERVING
    # -- never directly to a PASS state -- so recovering from REVIEW_ERROR
    # always means running a REAL, FRESH observer/judge cycle again, never
    # skipping straight to a verdict. cmd_review_retry (cli.py) is the only
    # caller allowed to walk this edge, and only after checking the
    # candidate_sha256 is unchanged and the retry count is within bounds --
    # those are business-logic guards enforced there, not by this table;
    # this table only says the edge is legal, not when it's earned.
    AssetState.REVIEW_ERROR: {AssetState.REVIEW_PENDING},
    AssetState.REVIEW_PENDING: {AssetState.OBSERVING},
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
