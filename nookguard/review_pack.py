"""Review-pack generator (Commit 6, consumed by Commit 7's blind-observer
Claude sessions). Builds the exact bundle an observer is allowed to see:
the candidate image reference plus role-appropriate metadata. Deliberately
excludes the contract, requirements, expected/allowed/forbidden objects, and
the compiled prompt text -- Appendix C is explicit: 'the observer session
never sees the contract.' A caller that wants to hand an observer session
more than what ReviewPack exposes is routing around the whole point of blind
review, not extending it."""

from __future__ import annotations

from dataclasses import dataclass, field

from .hashing import sha256_canonical_json

# Appendix C: Observer B gets a general failure taxonomy (still no
# prompt/expected answer) so it can actively try to falsify quality; Observer
# A gets nothing beyond "describe what you see."
FAILURE_TAXONOMY: list[str] = [
    "unexpected_furniture",
    "material_fusion",
    "duplicated_items",
    "malformed_anatomy_or_hands",
    "impossible_physics",
    "branded_or_readable_text",
    "environment_contradiction",
    "repeated_composition",
]

OBSERVER_ROLES = ("blind_a", "adversarial_b")


@dataclass(frozen=True)
class ReviewPack:
    candidate_sha256: str
    observer_role: str
    image_path: str
    failure_taxonomy: list[str] = field(default_factory=list)
    review_pack_sha256: str = ""

    def to_dict(self) -> dict:
        return {
            "candidate_sha256": self.candidate_sha256,
            "observer_role": self.observer_role,
            "image_path": self.image_path,
            "failure_taxonomy": self.failure_taxonomy,
            "review_pack_sha256": self.review_pack_sha256,
        }


def build_review_pack(candidate_sha256: str, image_path: str, observer_role: str) -> ReviewPack:
    if observer_role not in OBSERVER_ROLES:
        raise ValueError(f"Unknown observer_role '{observer_role}', expected one of {OBSERVER_ROLES}")

    taxonomy = list(FAILURE_TAXONOMY) if observer_role == "adversarial_b" else []

    # Hash the pack's own content (NOT the contract -- that's the point) so
    # tampering with what an observer was actually shown is detectable, same
    # spirit as spec_sha256/prompt_sha256 elsewhere in this system.
    hashable_payload = {
        "candidate_sha256": candidate_sha256,
        "observer_role": observer_role,
        "failure_taxonomy": taxonomy,
    }
    review_pack_sha256 = sha256_canonical_json(hashable_payload)

    return ReviewPack(
        candidate_sha256=candidate_sha256,
        observer_role=observer_role,
        image_path=image_path,
        failure_taxonomy=taxonomy,
        review_pack_sha256=review_pack_sha256,
    )
