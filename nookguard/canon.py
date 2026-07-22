"""Canonical source registry + stale-source scan (Commit 4). Reads the REAL
canon files that already govern Winnie/room consistency in this project —
does not restate or duplicate their content, only hashes and tracks them, per
the master checklist's explicit instruction: 'without restating or changing
Winnie canon.' If these files move, update CANON_FILES here — don't let a
prompt silently keep citing a path that no longer exists."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .hashing import sha256_canonical_json, sha256_file

# Paths relative to the project root (the parent of the `site/` repo this
# package lives in). See docs/nookguard/SPEC.md and the main project
# CLAUDE.md's "Critical rules" section for why each of these is canon.
CANON_FILES: list[str] = [
    "brand-assets/Winnie-Image-Generation-Rules.md",
    "brand-assets/winnie/Winnie-Identity-Source-of-Truth.md",
    "brand-assets/winnie/Winnies-Home-Room-Bible.md",
    "brand-assets/winnie/Character-Bible.md",
    "brand-assets/winnie/Winnie-Image-Lexicon-2026-07-16.md",
]


@dataclass(frozen=True)
class CanonEntry:
    relative_path: str
    exists: bool
    sha256: Optional[str] = None


class CanonRegistry:
    def __init__(self, project_root: str | Path, files: Optional[list[str]] = None):
        self.project_root = Path(project_root)
        self.files = files if files is not None else list(CANON_FILES)

    def build_manifest(self) -> list[CanonEntry]:
        entries = []
        for rel in self.files:
            full = self.project_root / rel
            if full.exists():
                entries.append(CanonEntry(rel, True, sha256_file(full)))
            else:
                entries.append(CanonEntry(rel, False, None))
        return entries

    def missing_canon_files(self) -> list[str]:
        """Files listed as canon that don't exist on disk right now — a hard
        problem, not a warning: a prompt compiler that silently proceeds
        without a canon file it thinks it's honoring is exactly the failure
        mode this registry exists to prevent."""
        return [e.relative_path for e in self.build_manifest() if not e.exists]

    def bundle_sha256(self) -> str:
        """This is what AssetContract.canonical_reference_bundle_sha256 should
        be set to at spec-lock time — a single hash over every canon file's
        current content, so any canon edit changes every future spec's bundle
        hash and makes drift visible."""
        manifest = self.build_manifest()
        payload = {e.relative_path: e.sha256 for e in manifest}
        return sha256_canonical_json(payload)

    def check_bundle_is_current(self, referenced_bundle_sha256: str) -> bool:
        """H007: 'prompt compile includes superseded source -> fail compile'.
        A contract/prompt built against an older canon bundle hash is stale —
        the canon may have changed underneath it (e.g. a room-bible fix) since
        the spec was locked. Returns True only if the referenced hash matches
        the CURRENT on-disk canon exactly."""
        return referenced_bundle_sha256 == self.bundle_sha256()
