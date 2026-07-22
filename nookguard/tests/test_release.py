from pathlib import Path

import pytest

from nookguard.hashing import sha256_bytes
from nookguard.release import ReleaseIntegrityError, publish_candidate


def _write_candidate(tmp_path: Path, content: bytes = b"fake-image-bytes") -> tuple[Path, str]:
    candidate_dir = tmp_path / "quarantine"
    candidate_dir.mkdir(exist_ok=True)
    digest = sha256_bytes(content)
    path = candidate_dir / f"{digest}.jpg"
    path.write_bytes(content)
    return path, digest


def test_publish_candidate_copies_bytes_to_content_hashed_path(tmp_path):
    candidate_path, digest = _write_candidate(tmp_path)
    public_dir = tmp_path / "public" / "winnie"

    public_path, public_url = publish_candidate(candidate_path, digest, public_dir, "/winnie", "hero")

    assert public_path.exists()
    assert public_path.read_bytes() == candidate_path.read_bytes()
    assert digest[:12] in public_path.name
    assert public_url == f"/winnie/hero-{digest[:12]}.jpg"


def test_publish_candidate_rejects_tampered_candidate_bytes(tmp_path):
    candidate_path, digest = _write_candidate(tmp_path)
    wrong_digest = "0" * 64
    public_dir = tmp_path / "public" / "winnie"

    with pytest.raises(ReleaseIntegrityError):
        publish_candidate(candidate_path, wrong_digest, public_dir, "/winnie", "hero")


def test_publish_candidate_is_idempotent_for_identical_rerelease(tmp_path):
    candidate_path, digest = _write_candidate(tmp_path)
    public_dir = tmp_path / "public" / "winnie"

    first_path, first_url = publish_candidate(candidate_path, digest, public_dir, "/winnie", "hero")
    second_path, second_url = publish_candidate(candidate_path, digest, public_dir, "/winnie", "hero")

    assert first_path == second_path
    assert first_url == second_url
    assert first_path.read_bytes() == candidate_path.read_bytes()


def test_publish_candidate_raises_on_corrupted_existing_target(tmp_path):
    candidate_path, digest = _write_candidate(tmp_path)
    public_dir = tmp_path / "public" / "winnie"
    public_dir.mkdir(parents=True)
    # Structurally-should-be-impossible case: something else already wrote
    # different bytes at the exact content-hashed path this release would use.
    collision_path = public_dir / f"hero-{digest[:12]}.jpg"
    collision_path.write_bytes(b"someone else's bytes")

    with pytest.raises(ReleaseIntegrityError):
        publish_candidate(candidate_path, digest, public_dir, "/winnie", "hero")


def test_publish_candidate_different_name_hints_produce_different_filenames(tmp_path):
    candidate_path, digest = _write_candidate(tmp_path)
    public_dir = tmp_path / "public" / "winnie"

    path_a, _ = publish_candidate(candidate_path, digest, public_dir, "/winnie", "hero-a")
    path_b, _ = publish_candidate(candidate_path, digest, public_dir, "/winnie", "hero-b")

    assert path_a != path_b
    assert path_a.exists() and path_b.exists()


def test_publish_candidate_two_different_candidates_never_collide(tmp_path):
    candidate_a, digest_a = _write_candidate(tmp_path, b"content A")
    candidate_b, digest_b = _write_candidate(tmp_path, b"content B")
    public_dir = tmp_path / "public" / "winnie"

    path_a, _ = publish_candidate(candidate_a, digest_a, public_dir, "/winnie", "hero")
    path_b, _ = publish_candidate(candidate_b, digest_b, public_dir, "/winnie", "hero")

    assert path_a != path_b
    assert path_a.read_bytes() == b"content A"
    assert path_b.read_bytes() == b"content B"
