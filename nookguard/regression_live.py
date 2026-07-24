"""Live-review regression corpus (Commit 20, requirements 1/2/4/6).

Unlike regression_corpus.py's fully deterministic fixtures (hand-built
BlindObservation/ContractJudgment dataclasses -- real, valuable coverage of
aggregate()'s own logic, but never touching a real image file or a real
Claude call), this module runs the ACTUAL observer and judge sessions
(agent_runner.run_observer_session / run_judge_session, via
cli_reviewer.claude_cli_executor -- Commit 19's default transport) against
real image files on disk. `mediactl regression --mode live-review` is the
only way an operational claim about NookGuard's real vision review, rather
than its aggregation logic alone, can be made honestly.

No synthetic observations or judgments are ever injected here: every
BlindObservation/ContractJudgment this module produces is exactly whatever
a real `run_observer_session`/`run_judge_session` call returns (or a real
ReviewSessionError if the process itself failed) -- there is no fallback
path that substitutes fabricated data for a failed or unavailable call.

Honest scope note on "historical" fixtures, documented here rather than
silently assumed: this module's own fixtures (below) are synthetic PIL
reproductions or an unrelated known-clean control photo, NOT the literal
original defective bytes -- that part of the original note was accurate.

CORRECTION (2026-07-23, Commit 25): the broader claim this docstring used
to make -- that the real historical defective candidate bytes "no longer
exist anywhere in this repository" -- was wrong, and was never actually
verified against git history before being written; it was an assumption
based on this project's "no fix in place, always regenerate" architecture
(state_machine.py's _REGENERATE_SOURCES comment) rather than a checked
fact. Commit 25's git archaeology proved otherwise: the real, literal
defective bytes for the banana-bread-foil and furniture-in-enclosure
incidents (plus a real object-count defect and a real reference-mismatch
defect) are still present in git history, at the git blob committed one
revision before each incident's fix commit, and were extracted byte-for-
byte via `git show <rev>:<path>` -- see `real_regression_fixtures.py` and
`regression_images_real/` for the real corpus this produced, and
docs/nookguard/BUILD-LOG.md's Commit 25 entry for the exact commit hashes.
That real corpus, not this module's synthetic one, is Commit 25's
operational-acceptance evidence.

This module still has a legitimate, narrower purpose despite that
correction: it is a fast, deterministic parser/evidence-flow test corpus
(see gen_regression_images.py's own docstring, relabeled the same day for
the same reason) -- useful for exercising the pipeline's plumbing cheaply,
not for demonstrating real defect-detection accuracy. It therefore still
draws its images from two honestly-labeled, distinct sources (see each
LiveRegressionFixture's `image_source_note`), never a fabricated verdict:

  1. A REAL, currently-published site photo (public/winnie/office-hero.jpg,
     copied verbatim into regression_images/) used as a known-clean
     control -- proving live review does not false-positive on
     legitimate, already-correct photography. This is real historical
     image data in the literal sense: it is a real photo that has been
     live on the site since before this commit.
  2. Purpose-built reproductions (rendered via PIL, `_gen_regression_
     images.py` at the repo root, committed under regression_images/),
     used only where the real original defective bytes are gone and a
     genuine rejection case is still needed. Each is documented plainly
     as a reproduction of the incident category, not the literal incident
     photo.

What this module CANNOT verify in this environment, honestly: whether the
real observer/judge calls actually reach a real, authenticated Claude
session. No real Claude Code CLI authentication exists on this machine as
of Commit 20 (see docs/nookguard/BUILD-LOG.md's Commit 18/19 entries) --
every fixture in this corpus will legitimately surface as
review_process_completed=False (a real REVIEW_ERROR, reason
auth_unavailable) until Maurice runs `claude setup-token` and a real
`mediactl auth-check` passes. That is the real, current, honestly-reported
result of running this corpus today, not a defect in this module -- see
Commit 22's live canary for what changes once real credentials exist."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .agent_runner import ReviewSessionError, run_judge_session, run_observer_session
from .aggregator import aggregate
from .review_pack import build_review_pack
from .schemas import AssetContract, MediaType, Requirement, RiskTier
from .state_machine import AssetState

REGRESSION_IMAGES_DIR = Path(__file__).resolve().parent / "regression_images"


def _contract(**overrides) -> AssetContract:
    base = dict(
        asset_id="live-regression-fixture", project_id="nest-and-nook", page_id="p1", slot_id="hero",
        media_type=MediaType.IMAGE, risk_tier=RiskTier.TIER_1, page_type_contract_version="1",
        source_excerpt="...", source_excerpt_sha256="x", canonical_reference_bundle_sha256="y",
        subject="Winnie", action="doing the thing", scene="the scene",
        planner_session_id="s1", plan_evaluator_session_id="s2",
    )
    base.update(overrides)
    return AssetContract(**base)


@dataclass
class LiveRegressionFixtureResult:
    fixture_id: str
    description: str
    category: str
    expected_state: str
    actual_state: str
    passed: bool
    detail: str = ""
    # False whenever a real REVIEW_ERROR (or a missing image file) stopped
    # this fixture before a real verdict was ever reached -- distinct from
    # `passed`, since "the review process didn't complete" and "it
    # completed and got the wrong answer" are different failure modes a
    # report must not blur together (the exact Commit 18 lesson).
    review_process_completed: bool = True


@dataclass
class LiveRegressionRunReport:
    results: list[LiveRegressionFixtureResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def review_process_completed_count(self) -> int:
        return sum(1 for r in self.results if r.review_process_completed)


@dataclass
class LiveRegressionFixture:
    fixture_id: str
    description: str
    category: str
    image_filename: str
    contract_builder: Callable[[], AssetContract]
    expected_state: str
    image_source_note: str


def _run_live_fixture(
    fixture: LiveRegressionFixture,
    *,
    images_dir: Path = REGRESSION_IMAGES_DIR,
) -> LiveRegressionFixtureResult:
    """The one real execution path: builds a real ReviewPack pointing at a
    real file, calls the real observer/judge functions (default transport,
    unless a test overrides them), and aggregates whatever real verdict
    comes back. `images_dir` is overridable purely so tests can point this
    at a tmp_path fixture image without touching the real corpus directory."""
    image_path = images_dir / fixture.image_filename
    if not image_path.exists():
        return LiveRegressionFixtureResult(
            fixture_id=fixture.fixture_id, description=fixture.description, category=fixture.category,
            expected_state=fixture.expected_state, actual_state="IMAGE_MISSING", passed=False,
            detail=f"regression image not found on disk: {image_path}", review_process_completed=False,
        )

    contract = fixture.contract_builder()
    candidate_sha256 = "live-regression-" + fixture.fixture_id

    observations: dict[str, object] = {}
    for role in ("blind_a", "adversarial_b"):
        pack = build_review_pack(candidate_sha256, str(image_path), role)
        try:
            observations[role] = run_observer_session(pack)
        except ReviewSessionError as e:
            return LiveRegressionFixtureResult(
                fixture_id=fixture.fixture_id, description=fixture.description, category=fixture.category,
                expected_state=fixture.expected_state, actual_state="REVIEW_ERROR", passed=False,
                detail=f"real observer session ({e.role}) did not complete: {e.reason}",
                review_process_completed=False,
            )

    try:
        judgment = run_judge_session(
            contract, "live-regression-spec", observations["blind_a"], observations["adversarial_b"]
        )
    except ReviewSessionError as e:
        return LiveRegressionFixtureResult(
            fixture_id=fixture.fixture_id, description=fixture.description, category=fixture.category,
            expected_state=fixture.expected_state, actual_state="REVIEW_ERROR", passed=False,
            detail=f"real judge session did not complete: {e.reason}", review_process_completed=False,
        )

    result = aggregate(contract, judgment, observations["blind_a"], observations["adversarial_b"])
    return LiveRegressionFixtureResult(
        fixture_id=fixture.fixture_id, description=fixture.description, category=fixture.category,
        expected_state=fixture.expected_state, actual_state=result.state.value,
        passed=(result.state.value == fixture.expected_state), detail="; ".join(result.reasons),
        review_process_completed=True,
    )


LIVE_FIXTURES: list[LiveRegressionFixture] = [
    LiveRegressionFixture(
        fixture_id="known_clean_real_site_photo",
        description="Real, currently-published site hero photo, no defect requirements",
        category="Real known-clean control",
        image_filename="known_clean_office_hero.jpg",
        contract_builder=lambda: _contract(requirements=[
            Requirement(requirement_id="r1", type="presence",
                        statement="a wall sign or wall fixture is visible in the office scene",
                        critical=False),
        ]),
        expected_state=AssetState.SEMANTIC_PASS.value,
        image_source_note="real, currently-live site photo (public/winnie/office-hero.jpg)",
    ),
    LiveRegressionFixture(
        fixture_id="object_count_contradiction_real_photo",
        description="Purpose-built photo with a single, unambiguous, verifiable object paired with a "
                     "deliberately, verifiably wrong required count",
        category="Object-count contradiction",
        image_filename="object_count_contradiction.jpg",
        contract_builder=lambda: _contract(requirements=[
            Requirement(requirement_id="r1", type="count",
                        statement="exactly 5 tape measures are visible", critical=True),
        ]),
        expected_state=AssetState.SEMANTIC_FAIL.value,
        image_source_note="purpose-built render (PIL) containing exactly 1 clearly labeled object, "
                           "verifiable by direct inspection of the generation script",
    ),
    LiveRegressionFixture(
        fixture_id="banana_foil_fusion_reproduction",
        description="Reproduction: foil rendered visually fused to a loaf's crust with no seam line",
        category="Material boundary/relationship",
        image_filename="banana_foil_fusion_reproduction.jpg",
        contract_builder=lambda: _contract(requirements=[
            Requirement(requirement_id="r1", type="material_boundary",
                        statement="foil is a separate, removable liner, not fused to the crust", critical=True),
        ]),
        expected_state=AssetState.SEMANTIC_FAIL.value,
        image_source_note="purpose-built reproduction (PIL-rendered), a parser/evidence-flow test fixture "
                           "only -- see gen_regression_images.py's module docstring. The real incident's "
                           "actual defective bytes DO still exist in git history (corrected 2026-07-23, "
                           "Commit 25) and are used for real operational-acceptance evidence instead; see "
                           "real_regression_fixtures.py's banana_foil fixture.",
    ),
    LiveRegressionFixture(
        fixture_id="unexpected_furniture_reproduction",
        description="Reproduction: indoor armchair furniture placed into an outdoor fenced enclosure scene",
        category="Unexpected objects/scene purity",
        image_filename="unexpected_furniture_reproduction.jpg",
        contract_builder=lambda: _contract(
            forbidden_objects=["indoor furniture (armchair) in an outdoor animal enclosure"]),
        expected_state=AssetState.SEMANTIC_FAIL.value,
        image_source_note="purpose-built reproduction (PIL-rendered), a parser/evidence-flow test fixture "
                           "only -- see gen_regression_images.py's module docstring. The real otter/aviary "
                           "incident's actual defective bytes DO still exist in git history (corrected "
                           "2026-07-23, Commit 25) and are used for real operational-acceptance evidence "
                           "instead; see real_regression_fixtures.py's furniture_enclosure fixture.",
    ),
]


def run_live_review_regression_corpus(
    *,
    images_dir: Path = REGRESSION_IMAGES_DIR,
) -> LiveRegressionRunReport:
    """Runs LIVE_FIXTURES for real -- every observation/judgment comes from
    a genuine agent_runner call (cli_reviewer.claude_cli_executor by
    default, Commit 19), never injected. See this module's own docstring
    for the honest image-provenance note and the standing REVIEW_ERROR
    caveat in this specific environment."""
    report = LiveRegressionRunReport()
    for fixture in LIVE_FIXTURES:
        report.results.append(_run_live_fixture(fixture, images_dir=images_dir))
    return report
