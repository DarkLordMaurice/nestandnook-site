import pytest

from nookguard.exceptions import InvalidTransitionError
from nookguard.state_machine import AssetState, is_regenerate_source, transition


def test_happy_path_full_pipeline():
    s = AssetState.SPEC_LOCKED
    s = transition(s, AssetState.PROMPT_COMPILED)
    s = transition(s, AssetState.GENERATING)
    s = transition(s, AssetState.CANDIDATE_REGISTERED)
    s = transition(s, AssetState.TECHNICAL_VALIDATING)
    s = transition(s, AssetState.TECHNICAL_PASS)
    s = transition(s, AssetState.OBSERVING)
    s = transition(s, AssetState.JUDGING)
    s = transition(s, AssetState.SEMANTIC_PASS)
    s = transition(s, AssetState.INTEGRATED)
    s = transition(s, AssetState.PREVIEWED)
    s = transition(s, AssetState.PREVIEW_REVIEW_PASS)
    s = transition(s, AssetState.RELEASED)
    s = transition(s, AssetState.PROD_VERIFIED)
    assert s == AssetState.PROD_VERIFIED


def test_cannot_skip_technical_validation():
    with pytest.raises(InvalidTransitionError):
        transition(AssetState.CANDIDATE_REGISTERED, AssetState.OBSERVING)


def test_cannot_self_certify_generation_to_release():
    """The core failure this whole system exists to prevent: a generator
    session moving its own output straight to release."""
    with pytest.raises(InvalidTransitionError):
        transition(AssetState.GENERATING, AssetState.RELEASED)


def test_semantic_fail_states_require_regenerate_not_fix_in_place():
    """Regression: the banana-bread-foil and goat-fence incidents were shipped
    because a rejected image got 'fixed' and reused instead of regenerated
    fresh. Every failure state here must be a regenerate source."""
    for state in [
        AssetState.SEMANTIC_FAIL,
        AssetState.FAIL_EVIDENCE,
        AssetState.FAIL_REFERENCE,
        AssetState.TECHNICAL_FAIL,
        AssetState.GENERATION_BLOCKED,
        AssetState.PROD_MISMATCH,
    ]:
        assert is_regenerate_source(state), f"{state} must require a fresh attempt"


def test_needs_owner_cannot_auto_pass():
    """Section 29.5: any critical requirement = uncertain -> NEEDS_OWNER or FAIL,
    never auto-pass. Confirm NEEDS_OWNER has no direct edge to RELEASED/
    INTEGRATED — it must go through an explicit owner decision first."""
    from nookguard.state_machine import legal_next_states

    next_states = legal_next_states(AssetState.NEEDS_OWNER)
    assert AssetState.INTEGRATED not in next_states
    assert AssetState.RELEASED not in next_states
    assert next_states == {AssetState.OWNER_APPROVED, AssetState.OWNER_REJECTED}


def test_observing_can_reach_review_error_not_just_judging():
    """Commit 8: an observer session can fail (bad JSON, interrupted call)
    exactly like a judge session can -- REVIEW_ERROR must be reachable from
    OBSERVING, not only from JUDGING."""
    from nookguard.state_machine import legal_next_states

    assert AssetState.REVIEW_ERROR in legal_next_states(AssetState.OBSERVING)
    s = transition(AssetState.OBSERVING, AssetState.REVIEW_ERROR)
    assert s == AssetState.REVIEW_ERROR
    assert is_regenerate_source(s)


def test_prod_mismatch_blocks_done_not_silently_fixed():
    from nookguard.state_machine import legal_next_states

    # PROD_MISMATCH is a regenerate source and a dead end in this machine on
    # purpose: nothing in TRANSITIONS lists it as a source key, so there is no
    # legal forward edge — a human/incident workflow must intervene.
    assert legal_next_states(AssetState.PROD_MISMATCH) == set()
