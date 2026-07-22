"""Regression corpus tests (Commit 13, Appendix I). Confirms every one of
the 10 named real-incident fixtures resolves to its documented expected
label -- this is the actual, checkable proof behind Definition of Done's
"the banana-foil and goat-fence regression fixtures both correctly FAIL,"
extended to cover the full corpus, not just those two named examples."""

from __future__ import annotations

from nookguard.regression_corpus import (
    FIXTURES,
    _FILESYSTEM_FIXTURES,
    _run_otter_aviary_stale_bytes_and_furniture,
    _run_repository_replacement_hash_mismatch,
    run_regression_corpus,
)
from nookguard.state_machine import AssetState


def _fixture(fixture_id: str):
    for f in FIXTURES:
        if f.fixture_id == fixture_id:
            return f
    raise KeyError(fixture_id)


def test_banana_foil_fixture_yields_fail_evidence():
    fixture = _fixture("banana_foil_fused_to_crust")
    actual, _ = fixture.run()
    assert actual == AssetState.FAIL_EVIDENCE.value == fixture.expected_state


def test_cup_collection_furniture_fixture_yields_semantic_fail():
    fixture = _fixture("cup_collection_unrequested_furniture")
    actual, _ = fixture.run()
    assert actual == AssetState.SEMANTIC_FAIL.value == fixture.expected_state


def test_cup_singular_owner_removed_fixture_yields_semantic_fail():
    fixture = _fixture("cup_singular_after_owner_removed")
    actual, _ = fixture.run()
    assert actual == AssetState.SEMANTIC_FAIL.value == fixture.expected_state


def test_goat_enclosure_fixture_yields_fail_reference():
    fixture = _fixture("goat_enclosure_clean_fence")
    actual, _ = fixture.run()
    assert actual == AssetState.FAIL_REFERENCE.value == fixture.expected_state


def test_halloween_apples_fixture_yields_semantic_fail():
    fixture = _fixture("halloween_apple_closeups_after_owner_removed")
    actual, _ = fixture.run()
    assert actual == AssetState.SEMANTIC_FAIL.value == fixture.expected_state


def test_parade_dresser_fixture_yields_semantic_fail_despite_rationalizing_prose():
    """The direct, checkable proof of Definition of Done's 'a forbidden-
    object finding ... cannot be overridden by prose' -- this fixture's
    judge session explicitly tries to explain the object away, and the
    aggregator must fail it anyway."""
    fixture = _fixture("parade_float_dresser_rationalized_as_altar")
    actual, detail = fixture.run()
    assert actual == AssetState.SEMANTIC_FAIL.value == fixture.expected_state
    assert "dresser" in detail.lower()


def test_off_the_clock_wrong_strip_count_fixture_yields_layout_fail():
    fixture = _fixture("off_the_clock_wrong_strip_count")
    actual, detail = fixture.run()
    assert actual == "LAYOUT_FAIL" == fixture.expected_state
    assert "photo-strip" in detail


def test_known_clean_control_fixture_yields_semantic_pass():
    fixture = _fixture("known_clean_control")
    actual, _ = fixture.run()
    assert actual == AssetState.SEMANTIC_PASS.value == fixture.expected_state


# ---- filesystem-backed fixtures (production integrity) ----

def test_otter_aviary_fixture_catches_both_real_failure_modes(tmp_path):
    actual, detail = _run_otter_aviary_stale_bytes_and_furniture(tmp_path)
    assert actual == "SEMANTIC_FAIL+PROD_MISMATCH"
    assert "semantic=semantic_fail" in detail.lower()
    assert "production=prod_mismatch" in detail.lower()


def test_repository_replacement_fixture_yields_prod_mismatch(tmp_path):
    actual, reason = _run_repository_replacement_hash_mismatch(tmp_path)
    assert actual == AssetState.PROD_MISMATCH.value
    assert "hash to" in reason


def test_filesystem_fixtures_registry_has_expected_two_entries():
    ids = {entry[0] for entry in _FILESYSTEM_FIXTURES}
    assert ids == {"otter_aviary_stale_bytes_and_furniture", "repository_replacement_hash_mismatch"}


# ---- full corpus run ----

def test_run_regression_corpus_covers_all_ten_fixtures_and_all_pass(tmp_path):
    def tmp_dir_factory(name: str):
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    report = run_regression_corpus(tmp_dir_factory)
    assert len(report.results) == 10
    assert report.all_passed, [r for r in report.results if not r.passed]


def test_run_regression_corpus_reports_appendix_i_categories(tmp_path):
    """Sanity check that the corpus is genuinely tied to Appendix I's real
    table, not just internally self-consistent -- every documented category
    from the spec must be present."""
    def tmp_dir_factory(name: str):
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    report = run_regression_corpus(tmp_dir_factory)
    categories = {r.category for r in report.results}
    expected_categories = {
        "Material boundary/relationship",
        "Unexpected objects/scene purity",
        "Owner exclusion/page integration",
        "Location continuity",
        "Production integrity + unexpected objects",
        "Narrative/owner instruction",
        "Unexpected object; no narrative override",
        "Layout schema",
        "Production hash mismatch",
        "Correct control",
    }
    assert categories == expected_categories
