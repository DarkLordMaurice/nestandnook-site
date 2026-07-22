"""Isolated from real project canon — uses a temp CanonRegistry so these tests
stay deterministic even as the real brand-assets content evolves."""

import tempfile
from pathlib import Path

import pytest

from nookguard.canon import CanonRegistry
from nookguard.exceptions import MissingCanonError, StaleCanonError
from nookguard.prompt_compiler import compile_prompt
from nookguard.schemas import AssetContract, MediaType, RiskTier


def _canon_root() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "canon.md").write_text("Winnie has brown hair.", encoding="utf-8")
    return root


def _registry(root: Path) -> CanonRegistry:
    return CanonRegistry(root, files=["canon.md"])


def _contract(**overrides) -> AssetContract:
    base = dict(
        asset_id="a1", project_id="nest-and-nook", page_id="p1", slot_id="hero",
        media_type=MediaType.IMAGE, risk_tier=RiskTier.TIER_2,
        page_type_contract_version="1", source_excerpt="...", source_excerpt_sha256="x",
        canonical_reference_bundle_sha256="", subject="Winnie", action="measuring",
        scene="office", planner_session_id="s1", plan_evaluator_session_id="s2",
    )
    base.update(overrides)
    return AssetContract(**base)


def test_compile_prompt_includes_canon_bundle_hash():
    root = _canon_root()
    registry = _registry(root)
    contract = _contract(canonical_reference_bundle_sha256=registry.bundle_sha256())
    text = compile_prompt(contract, canon_registry=registry)
    assert f"Canon bundle: {registry.bundle_sha256()}" in text


def test_compile_prompt_raises_on_missing_canon_file():
    root = Path(tempfile.mkdtemp())  # no canon.md written
    registry = CanonRegistry(root, files=["canon.md"])
    contract = _contract()
    with pytest.raises(MissingCanonError):
        compile_prompt(contract, canon_registry=registry)


def test_compile_prompt_raises_on_stale_canon_reference():
    """H007: the contract references an OLD bundle hash; canon has since
    changed. Compile must fail, not silently use the new canon."""
    root = _canon_root()
    registry = _registry(root)
    stale_hash = registry.bundle_sha256()
    (root / "canon.md").write_text("Winnie has red hair now.", encoding="utf-8")

    contract = _contract(canonical_reference_bundle_sha256=stale_hash)
    with pytest.raises(StaleCanonError):
        compile_prompt(contract, canon_registry=registry)


def test_compile_prompt_allows_empty_bundle_reference():
    """An unset canonical_reference_bundle_sha256 (e.g. a spec never locked
    through cmd_spec_lock) skips the staleness check rather than crashing —
    cmd_spec_lock is what actually stamps a real hash in the CLI flow."""
    root = _canon_root()
    registry = _registry(root)
    contract = _contract(canonical_reference_bundle_sha256="")
    text = compile_prompt(contract, canon_registry=registry)
    assert "Subject: Winnie" in text


def test_compile_prompt_selects_outdoor_module_for_outdoor_scene():
    root = _canon_root()
    registry = _registry(root)
    contract = _contract(scene="a sunny park trail", canonical_reference_bundle_sha256="")
    text = compile_prompt(contract, canon_registry=registry)
    assert "outdoor" in text.lower()
    assert "do not introduce indoor furniture" in text.lower()


def test_compile_prompt_selects_indoor_module_for_indoor_scene():
    root = _canon_root()
    registry = _registry(root)
    contract = _contract(scene="home office", canonical_reference_bundle_sha256="")
    text = compile_prompt(contract, canon_registry=registry)
    assert "curated, lived-in background" in text.lower() or "warm, lived-in indoor" in text.lower()


def test_compile_prompt_never_selects_both_indoor_and_outdoor():
    """Structural regression test for the real incident this module split
    fixes — no scene text should ever be able to trigger both modules."""
    root = _canon_root()
    registry = _registry(root)
    for scene in ["office", "a park", "kitchen", "hilltop trail", "garage", "zoo enclosure"]:
        contract = _contract(scene=scene, canonical_reference_bundle_sha256="")
        text = compile_prompt(contract, canon_registry=registry)
        has_indoor = "warm, lived-in indoor" in text.lower()
        has_outdoor = "candid outdoor" in text.lower()
        assert not (has_indoor and has_outdoor), f"scene '{scene}' selected both modules"
