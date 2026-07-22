"""Regression corpus (Commit 13, Appendix I). Ten named fixtures derived
directly from real incidents already documented in the main project's
CLAUDE.md -- this is not synthetic/hypothetical test data, it is a
permanent, runnable record of mistakes NookGuard exists to catch a second
time. Appendix I lists ten rows (nine FAIL, one PASS control); this module
reproduces each one against the SPECIFIC real subsystem that would have
caught it in production, because the real incidents themselves spanned
three different subsystems:

  - aggregate() (Commit 8) for semantic-judgment cases (forbidden objects,
    missing evidence, unsatisfied continuity/identity constraints)
  - off_the_clock_schema.lint_off_the_clock_page() (Commit 9) for the
    layout-schema case
  - production_verifier.verify_against_local_build() (Commit 12) for the
    production-hash-mismatch case

There is deliberately no single "regression-test function" pretending all
ten fixtures go through the same code path -- that would test something
that doesn't match how these bugs actually happened, and would silently
stop covering two-thirds of the real corpus."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .aggregator import aggregate
from .off_the_clock_schema import lint_off_the_clock_page
from .production_verifier import verify_against_local_build
from .schemas import (
    AssetContract,
    BlindObservation,
    ContractJudgment,
    ForbiddenObjectFinding,
    MediaType,
    Requirement,
    RequirementJudgment,
    RequirementResult,
    RiskTier,
)
from .state_machine import AssetState

# ---- shared builders (kept local to this module -- production code should
# not import test helpers, and these fixtures are themselves the "test
# data," permanently maintained as part of the corpus, not throwaway) ----


def _contract(**overrides) -> AssetContract:
    base = dict(
        asset_id="regression-fixture", project_id="nest-and-nook", page_id="p1", slot_id="hero",
        media_type=MediaType.IMAGE, risk_tier=RiskTier.TIER_1, page_type_contract_version="1",
        source_excerpt="...", source_excerpt_sha256="x", canonical_reference_bundle_sha256="y",
        subject="Winnie", action="doing the thing", scene="the scene",
        planner_session_id="s1", plan_evaluator_session_id="s2",
    )
    base.update(overrides)
    return AssetContract(**base)


def _judgment(**overrides) -> ContractJudgment:
    base = dict(candidate_sha256="c1", spec_sha256="s1", judge_session_id="j1", judge_agent_hash="h1",
                context_bundle_sha256="cb1")
    base.update(overrides)
    return ContractJudgment(**base)


def _observation(role: str, **overrides) -> BlindObservation:
    base = dict(review_id="r1", candidate_sha256="c1", review_pack_sha256="rp1", reviewer_agent_hash="h1",
                reviewer_session_id="s1", context_bundle_sha256="cb1", observer_role=role)
    base.update(overrides)
    return BlindObservation(**base)


@dataclass
class RegressionFixtureResult:
    fixture_id: str
    description: str
    category: str
    expected_state: str
    actual_state: str
    passed: bool
    detail: str = ""


@dataclass
class RegressionRunReport:
    results: list[RegressionFixtureResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)


@dataclass
class RegressionFixture:
    fixture_id: str
    description: str
    category: str
    expected_state: str
    run: Callable[[], tuple[str, str]]  # -> (actual_state_value, detail)


# ---- fixture 1: banana bread foil fused to crust -----------------------

def _run_banana_foil() -> tuple[str, str]:
    contract = _contract(requirements=[
        Requirement(requirement_id="r1", type="material_boundary",
                    statement="foil is a separate, removable liner, not fused to the crust", critical=True),
    ])
    judgment = _judgment(requirements=[
        RequirementJudgment(requirement_id="r1", result=RequirementResult.TRUE),  # no evidence cited
    ])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    return result.state.value, "; ".join(result.reasons)


# ---- fixture 2: cup collection with unrequested living-room furniture --

def _run_cup_collection_furniture() -> tuple[str, str]:
    contract = _contract(forbidden_objects=["living-room furniture (armchair, sofa, coffee table)"])
    judgment = _judgment(forbidden_object_findings=[
        ForbiddenObjectFinding(label="living-room furniture (armchair, sofa, coffee table)",
                                confidence=0.85, source_observation_id="obs1"),
    ])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    return result.state.value, "; ".join(result.reasons)


# ---- fixture 3: cup page using singular cup after owner removed concept

def _run_cup_singular_after_owner_removed() -> tuple[str, str]:
    """The owner already rejected single-cup imagery for this page (a real
    prior NEEDS_OWNER -> OWNER_REJECTED decision, tracked in owner_queue.py
    separately) -- the contract now carries "cup" as a standing forbidden
    object for this asset going forward. The mechanism that must still
    catch a regenerated candidate reintroducing it is identical to fixture
    2's: a forbidden-object finding, never overridable by prose."""
    contract = _contract(forbidden_objects=["single cup (owner-excluded composition)"])
    judgment = _judgment(forbidden_object_findings=[
        ForbiddenObjectFinding(label="single cup (owner-excluded composition)",
                                confidence=0.9, source_observation_id="obs1"),
    ])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    return result.state.value, "; ".join(result.reasons)


# ---- fixture 4: goat enclosure with clean fence instead of real rails ---

def _run_goat_enclosure_clean_fence() -> tuple[str, str]:
    contract = _contract(
        continuity_constraints=["fence/mesh must match the real reference rails/mesh photographed on location"],
        requirements=[],  # no continuity requirement was ever judged true -- the real failure mode
    )
    judgment = _judgment(requirements=[])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    return result.state.value, "; ".join(result.reasons)


# ---- fixture 5: otter/aviary with older production bytes + furniture ---

def _run_otter_aviary_stale_bytes_and_furniture(tmp_path: Path) -> tuple[str, str]:
    """This incident was two failures at once -- the real lesson Appendix I
    records. Both mechanisms must independently catch it: the semantic
    aggregator on the unexpected-furniture finding, and the production
    verifier on the stale bytes. Takes a tmp_path since, unlike every other
    fixture, this one needs real files on disk (production_verifier reads
    real bytes, not synthetic observation data)."""
    contract = _contract(forbidden_objects=["indoor furniture in an outdoor otter/aviary enclosure"])
    judgment = _judgment(forbidden_object_findings=[
        ForbiddenObjectFinding(label="indoor furniture in an outdoor otter/aviary enclosure",
                                confidence=0.8, source_observation_id="obs1"),
    ])
    semantic_result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))

    public_root = tmp_path / "public"
    public_dir = public_root / "winnie"
    public_dir.mkdir(parents=True)
    dist_root = tmp_path / "dist"
    (dist_root / "winnie").mkdir(parents=True)
    public_path = public_dir / "otter-aviary-abc123ef0912.jpg"
    public_path.write_bytes(b"current correct bytes, furniture removed")
    dist_path = dist_root / "winnie" / "otter-aviary-abc123ef0912.jpg"
    dist_path.write_bytes(b"OLDER production bytes that still contain furniture")  # stale

    from .hashing import sha256_bytes
    prod_result = verify_against_local_build(
        public_path, sha256_bytes(public_path.read_bytes()), dist_root, public_root)

    semantic_caught = semantic_result.state == AssetState.SEMANTIC_FAIL
    production_caught = prod_result.state == AssetState.PROD_MISMATCH
    both_caught = semantic_caught and production_caught
    detail = (f"semantic={semantic_result.state.value} ({'; '.join(semantic_result.reasons)}); "
              f"production={prod_result.state.value} ({prod_result.reason})")
    # Represent "both real failure modes correctly caught" as a single
    # pass/fail signal for this fixture's expected_state comparison.
    actual = "SEMANTIC_FAIL+PROD_MISMATCH" if both_caught else "INCOMPLETE_DETECTION"
    return actual, detail


# ---- fixture 6: Halloween apple closeups after owner removed concept ---

def _run_halloween_apples_after_owner_removed() -> tuple[str, str]:
    contract = _contract(forbidden_objects=["apple bobbing / apple closeups (owner-excluded concept)"])
    judgment = _judgment(forbidden_object_findings=[
        ForbiddenObjectFinding(label="apple bobbing / apple closeups (owner-excluded concept)",
                                confidence=0.88, source_observation_id="obs1"),
    ])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    return result.state.value, "; ".join(result.reasons)


# ---- fixture 7: parade float dresser rationalized as an altar ----------

def _run_parade_dresser_rationalized_as_altar() -> tuple[str, str]:
    """Definition of Done: "a forbidden-object finding from either blind
    observer cannot be overridden by prose." The judge's own concise_reason
    here explicitly tries to rationalize the object away -- aggregate()
    must still fail, because it never reads concise_reason to decide
    anything; it only reads forbidden_object_findings' confidence."""
    contract = _contract(forbidden_objects=["furniture (dresser) on a parade float"])
    judgment = _judgment(
        requirements=[RequirementJudgment(
            requirement_id="r-narrative", result=RequirementResult.TRUE,
            concise_reason="this reads as a dressed altar for the float's theme, not a literal dresser",
        )],
        forbidden_object_findings=[
            ForbiddenObjectFinding(label="furniture (dresser) on a parade float",
                                    confidence=0.75, source_observation_id="obs1"),
        ],
    )
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    return result.state.value, "; ".join(result.reasons)


# ---- fixture 8: Off the Clock page with wrong photo-strip count --------

def _run_off_the_clock_wrong_strip_count() -> tuple[str, str]:
    broken_strip = '<div class="photo-strip">\n<figure></figure><figure></figure>\n</div>'  # 2, not 3
    body = f"Some real narrative text.\n\n{broken_strip}\n"
    report = lint_off_the_clock_page(body, "Life outside the nook")
    state = "LAYOUT_FAIL" if not report.passed else "LAYOUT_PASS"
    return state, "; ".join(report.reasons)


# ---- fixture 9: repository replacement differs from served bytes -------

def _run_repository_replacement_hash_mismatch(tmp_path: Path) -> tuple[str, str]:
    from .hashing import sha256_bytes

    public_root = tmp_path / "public"
    public_dir = public_root / "winnie"
    public_dir.mkdir(parents=True)
    dist_root = tmp_path / "dist"
    (dist_root / "winnie").mkdir(parents=True)

    public_path = public_dir / "hero-fedcba098765.jpg"
    public_path.write_bytes(b"the repository's current, correct bytes")
    dist_path = dist_root / "winnie" / "hero-fedcba098765.jpg"
    dist_path.write_bytes(b"different bytes actually being served by Cloudflare")

    result = verify_against_local_build(
        public_path, sha256_bytes(public_path.read_bytes()), dist_root, public_root)
    return result.state.value, result.reason


# ---- fixture 10: known clean control (PASS) -- also the canary payload -

def _run_known_clean_control() -> tuple[str, str]:
    contract = _contract(requirements=[
        Requirement(requirement_id="r1", type="count", statement="exactly 1 tape measure visible", critical=True),
    ])
    judgment = _judgment(requirements=[
        RequirementJudgment(requirement_id="r1", result=RequirementResult.TRUE,
                             evidence_observation_ids=["obs1"]),
    ])
    result = aggregate(contract, judgment, _observation("blind_a"), _observation("adversarial_b"))
    return result.state.value, "; ".join(result.reasons)


FIXTURES: list[RegressionFixture] = [
    RegressionFixture("banana_foil_fused_to_crust",
                       "Banana bread with foil visually fused to crust",
                       "Material boundary/relationship", AssetState.FAIL_EVIDENCE.value,
                       _run_banana_foil),
    RegressionFixture("cup_collection_unrequested_furniture",
                       "Cup collection with unrequested living-room furniture",
                       "Unexpected objects/scene purity", AssetState.SEMANTIC_FAIL.value,
                       _run_cup_collection_furniture),
    RegressionFixture("cup_singular_after_owner_removed",
                       "Cup page using singular cup after owner removed concept",
                       "Owner exclusion/page integration", AssetState.SEMANTIC_FAIL.value,
                       _run_cup_singular_after_owner_removed),
    RegressionFixture("goat_enclosure_clean_fence",
                       "Goat enclosure with clean fence instead of real reference rails/mesh",
                       "Location continuity", AssetState.FAIL_REFERENCE.value,
                       _run_goat_enclosure_clean_fence),
    # fixture 5 needs a tmp_path -- registered separately below, not in this
    # flat list, since it can't run without a filesystem sandbox argument.
    RegressionFixture("halloween_apple_closeups_after_owner_removed",
                       "Halloween apple closeups after owner removed apple concept",
                       "Narrative/owner instruction", AssetState.SEMANTIC_FAIL.value,
                       _run_halloween_apples_after_owner_removed),
    RegressionFixture("parade_float_dresser_rationalized_as_altar",
                       "Parade float dresser rationalized as altar",
                       "Unexpected object; no narrative override", AssetState.SEMANTIC_FAIL.value,
                       _run_parade_dresser_rationalized_as_altar),
    RegressionFixture("off_the_clock_wrong_strip_count",
                       "Off the Clock page with 1, 4, or 5 photo strips instead of approved structure",
                       "Layout schema", "LAYOUT_FAIL",
                       _run_off_the_clock_wrong_strip_count),
    RegressionFixture("known_clean_control",
                       "Known clean image, correct scene, no critical defects",
                       "Correct control", AssetState.SEMANTIC_PASS.value,
                       _run_known_clean_control),
]

# Fixtures 5 and 9 need a tmp_path (real files on disk for the production
# verifier) -- kept as separate builders, run explicitly by
# run_regression_corpus() alongside the flat FIXTURES list above.
_FILESYSTEM_FIXTURES: list[tuple[str, str, str, str, Callable[[Path], tuple[str, str]]]] = [
    ("otter_aviary_stale_bytes_and_furniture",
     "Otter/aviary with older production bytes containing furniture",
     "Production integrity + unexpected objects", "SEMANTIC_FAIL+PROD_MISMATCH",
     _run_otter_aviary_stale_bytes_and_furniture),
    ("repository_replacement_hash_mismatch",
     "Repository replacement differs from Cloudflare-served bytes",
     "Production hash mismatch", AssetState.PROD_MISMATCH.value,
     _run_repository_replacement_hash_mismatch),
]


def run_regression_corpus(tmp_dir_factory: Callable[[str], Path]) -> RegressionRunReport:
    """Runs every fixture in the corpus (Appendix I, all 10 rows) and
    returns one consolidated report. `tmp_dir_factory(name) -> Path` supplies
    a fresh, real, writable directory for the two fixtures that need actual
    files on disk (the production-integrity cases) -- callers typically pass
    something backed by `tempfile.mkdtemp()` or pytest's `tmp_path_factory`."""
    report = RegressionRunReport()

    for fixture in FIXTURES:
        actual_state, detail = fixture.run()
        report.results.append(RegressionFixtureResult(
            fixture_id=fixture.fixture_id, description=fixture.description, category=fixture.category,
            expected_state=fixture.expected_state, actual_state=actual_state,
            passed=(actual_state == fixture.expected_state), detail=detail,
        ))

    for fixture_id, description, category, expected_state, run_fn in _FILESYSTEM_FIXTURES:
        tmp_path = tmp_dir_factory(fixture_id)
        actual_state, detail = run_fn(tmp_path)
        report.results.append(RegressionFixtureResult(
            fixture_id=fixture_id, description=description, category=category,
            expected_state=expected_state, actual_state=actual_state,
            passed=(actual_state == expected_state), detail=detail,
        ))

    return report
