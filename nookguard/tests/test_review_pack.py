import pytest

from nookguard.review_pack import FAILURE_TAXONOMY, build_review_pack


def test_blind_a_gets_no_failure_taxonomy():
    """Appendix C: Observer A gets nothing beyond 'describe what you see' --
    no expected-object list, and (per this project's reading of the spec) no
    failure taxonomy either, since that would bias what it looks for."""
    pack = build_review_pack("cand-1", "/tmp/cand-1.png", "blind_a")
    assert pack.failure_taxonomy == []


def test_adversarial_b_gets_the_real_failure_taxonomy():
    pack = build_review_pack("cand-1", "/tmp/cand-1.png", "adversarial_b")
    assert pack.failure_taxonomy == FAILURE_TAXONOMY
    assert "unexpected_furniture" in pack.failure_taxonomy


def test_review_pack_never_contains_contract_or_prompt_fields():
    """Structural regression test for Appendix C's core rule. If a future
    edit ever adds a 'contract' or 'prompt_text' field to ReviewPack, this
    test catches it immediately."""
    pack = build_review_pack("cand-1", "/tmp/cand-1.png", "adversarial_b")
    payload = pack.to_dict()
    forbidden_keys = {"contract", "requirements", "prompt_text", "expected_objects",
                       "allowed_objects", "subject", "action", "scene"}
    assert forbidden_keys.isdisjoint(payload.keys())


def test_unknown_observer_role_rejected():
    with pytest.raises(ValueError):
        build_review_pack("cand-1", "/tmp/cand-1.png", "not_a_real_role")


def test_review_pack_sha256_is_deterministic_for_same_inputs():
    pack1 = build_review_pack("cand-1", "/tmp/x.png", "blind_a")
    pack2 = build_review_pack("cand-1", "/tmp/x.png", "blind_a")
    assert pack1.review_pack_sha256 == pack2.review_pack_sha256


def test_review_pack_sha256_differs_by_role():
    """Same candidate, different role -> different pack, different hash --
    the two observers must be provably distinguishable artifacts, not the
    same pack relabeled."""
    pack_a = build_review_pack("cand-1", "/tmp/x.png", "blind_a")
    pack_b = build_review_pack("cand-1", "/tmp/x.png", "adversarial_b")
    assert pack_a.review_pack_sha256 != pack_b.review_pack_sha256
