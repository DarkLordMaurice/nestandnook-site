"""Public-media containment (Commit 21, requirements 1-2). Single source of
truth for "what counts as published media" and "is this exact file/hash
approved" -- `hooks.py`'s H008 (the live Claude-tool gate) and
`cli.py`'s `mediactl media-audit` (the repository-validation gate) both
import from here rather than each keeping their own copy of the media-path
rules, which is how `_MEDIA_EXTENSIONS`/`_PUBLISHED_MEDIA_DIRS` ended up
defined only in `hooks.py` before this commit -- a real duplication risk
this module removes.

The containment rule (requirement 1): a public media file is allowed to
exist as-is if EITHER (a) its exact (relative_path, sha256) pair matches
the committed baseline snapshot taken when this containment was introduced
-- i.e. it is pre-existing, untouched legacy content, not something new or
modified -- OR (b) its real sha256 is present in a real NookGuard release
manifest entry (`store.releases_dir`, written only by `release.py`'s
`publish_candidate` via `mediactl release`). Anything else -- a brand new
file, or an existing baseline file whose bytes changed -- is UNAPPROVED
and must block."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hashing import sha256_bytes

MEDIA_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg")
PUBLISHED_MEDIA_DIRS = ("public/winnie", "public/cursors", "public/pins",
                         "public/tools", "public/recipes", "public/products")

DEFAULT_BASELINE_PATH = Path(__file__).resolve().parent / "public_media_baseline.json"

# IMPORTANT, real path-convention note (found and fixed during Commit 21's
# own wiring, not assumed correct on the first attempt): every OTHER
# `project_root`-taking function/argument in this codebase (canon.py's
# CanonRegistry, prompt_compiler.py, cli.py's own `--project-root`
# default) means the directory ABOVE `site/` -- `brand-assets/` lives
# there, confirmed directly on disk (`.../Amazon Drop Ship/brand-assets/`,
# a sibling of `site/`, not inside it). `public/winnie` etc., by contrast,
# genuinely live INSIDE `site/` (`.../Amazon Drop Ship/site/public/
# winnie/`). Passing cli.py's `--project-root` value straight into this
# module's path-walking functions would silently resolve to a directory
# that doesn't exist and scan zero files -- a dangerously EMPTY-BUT-
# PASSING audit, worse than no audit at all. This module therefore takes
# its own, separately-named `site_root` parameter (default: the real
# `site/` directory, `nookguard/`'s own parent) everywhere it resolves a
# real path on disk -- never `project_root` -- and cli.py wires a distinct
# `--site-root` flag (not `--project-root`) into the commands that call
# into this module. `is_published_media_path()` below is the one function
# that does NOT need this distinction: it does a plain substring check on
# whatever path string it's handed (always an absolute path in practice,
# from a live Claude tool call), so "public/winnie" matches correctly
# inside a full ".../site/public/winnie/..." path regardless of which
# root convention produced that string.
DEFAULT_SITE_ROOT = Path(__file__).resolve().parent.parent


def is_published_media_path(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/").lower()
    if not normalized.endswith(MEDIA_EXTENSIONS):
        return False
    return any(d in normalized for d in PUBLISHED_MEDIA_DIRS)


def snapshot_public_media(site_root: Path) -> dict[str, str]:
    """Walks every real file currently under `site_root`'s published
    media directories and returns {relative_posix_path: sha256}. Used both
    to GENERATE the committed baseline (once, at containment introduction)
    and to AUDIT the current tree against that baseline (every run) --
    same real function, so there is no risk of the two ever drifting apart
    in how a path is normalized or which files are in scope."""
    site_root = Path(site_root)
    snapshot: dict[str, str] = {}
    for rel_dir in PUBLISHED_MEDIA_DIRS:
        dir_path = site_root / rel_dir
        if not dir_path.is_dir():
            continue
        for file_path in sorted(dir_path.rglob("*")):
            if not file_path.is_file():
                continue
            if not file_path.name.lower().endswith(MEDIA_EXTENSIONS):
                continue
            rel = file_path.relative_to(site_root).as_posix()
            snapshot[rel] = sha256_bytes(file_path.read_bytes())
    return snapshot


def load_baseline(baseline_path: Path = DEFAULT_BASELINE_PATH) -> dict[str, str]:
    if not Path(baseline_path).exists():
        return {}
    return json.loads(Path(baseline_path).read_text(encoding="utf-8"))


def write_baseline(snapshot: dict[str, str], baseline_path: Path = DEFAULT_BASELINE_PATH) -> None:
    Path(baseline_path).write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def collect_approved_hashes(store_roots: list[Path]) -> set[str]:
    """Reads every real ReleaseManifestEntry (`{store_root}/releases/*.json`,
    written only by `mediactl release`) across one or more given NookGuard
    store roots and returns the set of approved `candidate_sha256` values.
    Multiple store roots are supported because different sessions/CI runs
    may use different `--store-root` values -- the approved set is the
    union of everything any of them has actually released."""
    from .manifest import ReleaseManifestEntry

    approved: set[str] = set()
    for root in store_roots:
        releases_dir = Path(root) / "releases"
        if not releases_dir.is_dir():
            continue
        for entry_path in releases_dir.glob("*.json"):
            try:
                entry = ReleaseManifestEntry.model_validate_json(entry_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 -- a corrupt/foreign file here is a real finding, not a crash
                continue
            approved.add(entry.candidate_sha256)
    return approved


def audit_public_media(
    site_root: Path = DEFAULT_SITE_ROOT,
    *,
    baseline_path: Path = DEFAULT_BASELINE_PATH,
    store_roots: list[Path] | None = None,
) -> dict[str, Any]:
    """The real containment check (requirement 1-2's 'repository
    validation' layer). Returns a structured, checkable report -- never
    just a bool -- so a caller (mediactl media-audit, or the deploy gate)
    can see exactly which files are the problem, not just that something
    failed.

    `store_roots` defaults to the single canonical local store
    (`<site_root>/nookguard_store`) if not given -- matching
    cli.py's own DEFAULT_STORE_ROOT convention (both are relative to
    `site/`, not the outer business-project root -- see this module's
    own DEFAULT_SITE_ROOT comment above)."""
    if store_roots is None:
        store_roots = [Path(site_root) / "nookguard_store"]

    baseline = load_baseline(baseline_path)
    approved_hashes = collect_approved_hashes(store_roots)
    current = snapshot_public_media(site_root)

    baseline_unchanged: list[str] = []
    approved_release: list[str] = []
    unapproved: list[dict[str, str]] = []

    for rel_path, current_hash in current.items():
        baseline_hash = baseline.get(rel_path)
        if baseline_hash is not None and baseline_hash == current_hash:
            baseline_unchanged.append(rel_path)
        elif current_hash in approved_hashes:
            approved_release.append(rel_path)
        else:
            reason = ("modified since baseline, not re-released through NookGuard"
                      if baseline_hash is not None else
                      "new file, not present in any NookGuard release manifest")
            unapproved.append({"path": rel_path, "sha256": current_hash, "reason": reason})

    removed_from_baseline = sorted(set(baseline) - set(current))

    return {
        "ok": len(unapproved) == 0,
        "total_files_scanned": len(current),
        "baseline_unchanged_count": len(baseline_unchanged),
        "approved_release_count": len(approved_release),
        "unapproved_count": len(unapproved),
        "unapproved": unapproved,
        "removed_from_baseline": removed_from_baseline,
    }
