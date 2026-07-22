"""Hashing utilities. SHA-256 everywhere per the spec (candidate_sha256,
prompt_sha256, spec_sha256, payload_sha256, etc.) — one algorithm, no mixing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    """Hex-digest SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """Hex-digest SHA-256 of a file's contents, streamed (safe for large media)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_canonical_json(obj: Any) -> str:
    """Hex-digest SHA-256 of an object's canonical JSON form: sorted keys, no
    whitespace ambiguity, UTF-8. Used for spec_sha256 / payload_sha256 style
    hashes where the hash must be reproducible across processes."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(canonical.encode("utf-8"))


def content_addressed_path(directory: str | Path, file_bytes: bytes, suffix: str) -> Path:
    """Build a content-addressed path: {directory}/{sha256}{suffix}. This is how
    candidate files avoid filename reuse (section 27: 'no filename reuse')."""
    digest = sha256_bytes(file_bytes)
    return Path(directory) / f"{digest}{suffix}"
