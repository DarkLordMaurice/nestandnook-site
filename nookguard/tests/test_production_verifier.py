from pathlib import Path

import pytest

from nookguard.hashing import sha256_bytes
from nookguard.production_verifier import (
    verify_against_live_url,
    verify_against_local_build,
    verify_production,
)
from nookguard.state_machine import AssetState


# ---- verify_against_local_build (real filesystem, no mocking) ----

def test_local_build_matching_bytes_yields_prod_verified(tmp_path):
    public_dir = tmp_path / "public" / "winnie"
    dist_root = tmp_path / "dist"
    public_dir.mkdir(parents=True)
    content = b"real released bytes"
    digest = sha256_bytes(content)
    public_path = public_dir / "hero-abc.jpg"
    public_path.write_bytes(content)
    dist_path = dist_root / "winnie" / "hero-abc.jpg"
    dist_path.parent.mkdir(parents=True)
    dist_path.write_bytes(content)  # dist/ has the same bytes -- a real build copied them

    result = verify_against_local_build(public_path, digest, dist_root, tmp_path / "public")
    assert result.state == AssetState.PROD_VERIFIED


def test_local_build_mismatched_bytes_yields_prod_mismatch(tmp_path):
    public_dir = tmp_path / "public" / "winnie"
    dist_root = tmp_path / "dist"
    public_dir.mkdir(parents=True)
    content = b"real released bytes"
    digest = sha256_bytes(content)
    public_path = public_dir / "hero-abc.jpg"
    public_path.write_bytes(content)
    dist_path = dist_root / "winnie" / "hero-abc.jpg"
    dist_path.parent.mkdir(parents=True)
    dist_path.write_bytes(b"STALE bytes Cloudflare is actually serving")  # differs

    result = verify_against_local_build(public_path, digest, dist_root, tmp_path / "public")
    assert result.state == AssetState.PROD_MISMATCH
    assert "hash to" in result.reason


def test_local_build_missing_dist_file_yields_prod_mismatch(tmp_path):
    public_dir = tmp_path / "public" / "winnie"
    dist_root = tmp_path / "dist"  # never populated
    public_dir.mkdir(parents=True)
    content = b"real released bytes"
    digest = sha256_bytes(content)
    public_path = public_dir / "hero-abc.jpg"
    public_path.write_bytes(content)

    result = verify_against_local_build(public_path, digest, dist_root, tmp_path / "public")
    assert result.state == AssetState.PROD_MISMATCH
    assert "not found" in result.reason


def test_local_build_public_path_outside_public_dir_yields_prod_mismatch(tmp_path):
    outside_dir = tmp_path / "somewhere-else"
    outside_dir.mkdir()
    stray_path = outside_dir / "hero.jpg"
    stray_path.write_bytes(b"x")

    result = verify_against_local_build(stray_path, sha256_bytes(b"x"), tmp_path / "dist", tmp_path / "public")
    assert result.state == AssetState.PROD_MISMATCH
    assert "not inside" in result.reason


# ---- verify_against_live_url (dependency-injected fetcher, no real network) ----

def test_live_url_matching_bytes_yields_prod_verified():
    content = b"live served bytes"
    digest = sha256_bytes(content)
    result = verify_against_live_url("https://nestandnook.org/winnie/hero.jpg", digest,
                                      fetcher=lambda url: content)
    assert result.state == AssetState.PROD_VERIFIED


def test_live_url_mismatched_bytes_yields_prod_mismatch():
    content = b"live served bytes"
    result = verify_against_live_url("https://nestandnook.org/winnie/hero.jpg", sha256_bytes(b"expected"),
                                      fetcher=lambda url: content)
    assert result.state == AssetState.PROD_MISMATCH


def test_live_url_fetch_failure_yields_prod_mismatch_not_a_crash():
    def broken_fetcher(url):
        raise ConnectionError("simulated network failure")

    result = verify_against_live_url("https://nestandnook.org/winnie/hero.jpg", "deadbeef",
                                      fetcher=broken_fetcher)
    assert result.state == AssetState.PROD_MISMATCH
    assert "could not fetch" in result.reason


# ---- verify_production dispatch ----

def test_verify_production_requires_one_mode(tmp_path):
    with pytest.raises(ValueError):
        verify_production(tmp_path / "x.jpg", "deadbeef")


def test_verify_production_rejects_both_modes_at_once(tmp_path):
    with pytest.raises(ValueError):
        verify_production(tmp_path / "x.jpg", "deadbeef", dist_root=tmp_path, public_root=tmp_path,
                           live_url="https://x/y.jpg")


def test_verify_production_dist_root_without_public_root_raises(tmp_path):
    with pytest.raises(ValueError):
        verify_production(tmp_path / "x.jpg", "deadbeef", dist_root=tmp_path)


def test_verify_production_routes_to_live_url_mode():
    content = b"routed bytes"
    digest = sha256_bytes(content)
    result = verify_production(Path("/unused"), digest, live_url="https://x/y.jpg",
                                fetcher=lambda url: content)
    assert result.state == AssetState.PROD_VERIFIED
