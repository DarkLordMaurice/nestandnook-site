"""Real release action (Commit 12): copies quarantined candidate bytes to a
content-hashed public path. This is the ONLY code path allowed to write
public media bytes -- Hook H008 (nookguard/hooks.py) denies any Claude-tool
Write from doing the same thing, and this module's own filename scheme
(manifest.content_hashed_filename) makes an accidental overwrite
structurally impossible: two different candidates can never produce the
same filename, and the same candidate always produces the same filename,
so re-releasing it is naturally idempotent rather than destructive."""

from __future__ import annotations

import shutil
from pathlib import Path

from .hashing import sha256_bytes
from .manifest import content_hashed_filename


class ReleaseIntegrityError(Exception):
    """Raised when bytes don't match an expected hash at a point where they
    structurally should -- either the candidate itself was tampered with
    between quarantine and release, or something wrote over a content-
    addressed public path with different bytes. Either case is real
    corruption to surface loudly, not a name collision to route around."""


def publish_candidate(
    candidate_path: Path,
    candidate_sha256: str,
    public_dir: Path,
    public_url_prefix: str,
    name_hint: str,
) -> tuple[Path, str]:
    """Copies candidate_path's bytes to a content-hashed filename under
    public_dir. Returns (public_path, public_url).

    If the target file already exists, verifies it is genuinely the same
    release (identical hash) before treating the call as a no-op -- this
    should be structurally impossible to fail (the filename IS derived
    from the hash), so hitting the mismatch branch means something else
    wrote to that exact path outside this function."""
    candidate_bytes = Path(candidate_path).read_bytes()
    actual_hash = sha256_bytes(candidate_bytes)
    if actual_hash != candidate_sha256:
        raise ReleaseIntegrityError(
            f"candidate bytes at {candidate_path} hash to {actual_hash}, not "
            f"the expected {candidate_sha256} -- refusing to release"
        )

    filename = content_hashed_filename(name_hint, candidate_sha256, Path(candidate_path).suffix)
    public_dir = Path(public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)
    public_path = public_dir / filename

    if public_path.exists():
        existing_hash = sha256_bytes(public_path.read_bytes())
        if existing_hash != candidate_sha256:
            raise ReleaseIntegrityError(
                f"public path {public_path} already exists with different "
                f"content (hash {existing_hash}, expected {candidate_sha256})"
            )
        # Identical bytes already published under this exact name -- an
        # idempotent no-op release, not an error.
    else:
        shutil.copyfile(candidate_path, public_path)

    public_url = f"{public_url_prefix.rstrip('/')}/{filename}"
    return public_path, public_url
