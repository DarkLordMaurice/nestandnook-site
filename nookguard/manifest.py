"""Release manifest (Commit 12, Appendix A "manifest" + section 27's "no
filename reuse... public filename is assigned only at release" + Definition
of Done's "release manifest hash"). A release manifest entry is the durable
record of exactly which candidate bytes became which public, content-hashed
URL, and when -- the thing production_verifier.py checks reality against."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .hashing import sha256_canonical_json


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hashed_filename(name_hint: str, candidate_sha256: str, extension: str, hash_len: int = 12) -> str:
    """Section 27's "no filename reuse": the public filename always embeds
    enough of the real content hash that two different candidates can never
    collide on the same name, and the same candidate released twice always
    produces the identical name -- idempotent, never accidentally
    duplicated or overwritten in place."""
    stem = name_hint.strip().strip("/")
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{stem}-{candidate_sha256[:hash_len]}{ext}"


class ReleaseManifestEntry(BaseModel):
    """Appendix A's "versioned assets" -- one released candidate's public
    identity. Deliberately no pass/fail or verification field here --
    production_verifier.py computes PROD_VERIFIED/PROD_MISMATCH separately,
    against this record, the same "code decides, this schema just carries
    facts" pattern used throughout the rest of NookGuard."""

    release_id: str
    run_id: str
    asset_id: str
    candidate_sha256: str
    public_path: str  # filesystem path the bytes were actually copied to
    public_url: str  # the served URL path, e.g. "/winnie/hero-abc123ef0912.jpg"
    site_commit: Optional[str] = None
    released_at: str = Field(default_factory=utcnow_iso)

    model_config = ConfigDict(extra="forbid")

    @property
    def release_manifest_sha256(self) -> str:
        """Definition of Done: "every complete report includes ... release
        manifest hash." Computed from the entry's own current fields, never
        stored separately, so it can't silently drift out of sync with what
        it's supposed to represent."""
        return sha256_canonical_json(self.model_dump(mode="json"))
