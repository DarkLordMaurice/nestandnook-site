from nookguard.manifest import ReleaseManifestEntry, content_hashed_filename


def test_content_hashed_filename_embeds_hash_prefix():
    name = content_hashed_filename("home-office-hero", "abcdef0123456789", ".jpg")
    assert name == "home-office-hero-abcdef012345.jpg"


def test_content_hashed_filename_adds_dot_if_extension_missing_it():
    name = content_hashed_filename("hero", "abcdef0123456789", "jpg")
    assert name.endswith(".jpg")


def test_content_hashed_filename_different_hashes_never_collide():
    a = content_hashed_filename("hero", "aaaaaaaaaaaaaaaa", ".jpg")
    b = content_hashed_filename("hero", "bbbbbbbbbbbbbbbb", ".jpg")
    assert a != b


def test_content_hashed_filename_same_candidate_is_deterministic():
    a = content_hashed_filename("hero", "aaaaaaaaaaaaaaaa", ".jpg")
    b = content_hashed_filename("hero", "aaaaaaaaaaaaaaaa", ".jpg")
    assert a == b


def test_content_hashed_filename_strips_slashes_from_hint():
    name = content_hashed_filename("/hero/", "aaaaaaaaaaaaaaaa", ".jpg")
    assert not name.startswith("/")


def _entry(**overrides) -> ReleaseManifestEntry:
    base = dict(
        release_id="r1", run_id="run1", asset_id="a1", candidate_sha256="c1" * 16,
        public_path="/proj/public/winnie/hero-abcdef012345.jpg",
        public_url="/winnie/hero-abcdef012345.jpg",
    )
    base.update(overrides)
    return ReleaseManifestEntry(**base)


def test_release_manifest_entry_rejects_unknown_fields():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ReleaseManifestEntry(
            release_id="r1", run_id="run1", asset_id="a1", candidate_sha256="c1",
            public_path="x", public_url="y", extra_field_not_in_schema=True,
        )


def test_release_manifest_sha256_is_deterministic_for_identical_entry():
    e1 = _entry(released_at="2026-07-22T00:00:00+00:00")
    e2 = _entry(released_at="2026-07-22T00:00:00+00:00")
    assert e1.release_manifest_sha256 == e2.release_manifest_sha256


def test_release_manifest_sha256_changes_with_candidate():
    e1 = _entry(candidate_sha256="c1" * 16, released_at="2026-07-22T00:00:00+00:00")
    e2 = _entry(candidate_sha256="c2" * 16, released_at="2026-07-22T00:00:00+00:00")
    assert e1.release_manifest_sha256 != e2.release_manifest_sha256
