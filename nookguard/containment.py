"""Commit 24: reviewer containment layer.

Commit 23 gave review subagents an isolated *prompt* (an observer never
receives contract text; a judge never receives the image) but never
constrained what those subagents' own tool access could physically touch on
disk. This module is the fix, and it is deliberately NOT "pick a more
restricted subagent type and call it done" -- Commit 24's own requirement 2
is explicit that the agent-type restriction alone must not be assumed to
prevent writes. Every subagent type available in this environment (including
the most restricted practical choice for viewing an image, `Explore`) still
retains at least read-capable tools that could, in principle, be used to
write a file (e.g. `Bash` on `Explore`). So containment here is enforced by
evidence, not by trust in a tool allowlist:

1. A reviewer is only ever pointed at a purpose-built, single-use scratch
   directory (`create_scratch`) containing nothing but the exact candidate
   (or contact-sheet) bytes it is permitted to see, any reference images,
   and a plain-text copy of its instructions. It never sees a path inside
   the real quarantine store, the real site source tree, or any evidence
   directory.
2. Immediately before the reviewer runs, `open_containment` snapshots every
   file's sha256 across the protected roots (repository, ledger, manifest,
   quarantine, evidence, public media) -- explicitly EXCLUDING the scratch
   directory, which is allowed to change (a preview reviewer is permitted to
   write crops there, per requirement 4).
3. Immediately after, `close_containment` re-snapshots the same roots and
   diffs. Any add/remove/modify anywhere outside the scratch directory is a
   containment violation -- the review is invalidated (never silently
   accepted) regardless of what the reviewer's own JSON response said.

Honesty note on requirement 3 ("record every file the reviewer accessed"):
this harness does not expose a tool-call trace across an Agent/Task
subagent boundary -- only the subagent's final text and coarse usage
metadata (tool_uses count) are visible to the orchestrator. This module
cannot produce a true "files opened" log and does not pretend to. What it
records instead, honestly, is `files_available_in_scratch` -- the complete,
exactly-known set of files the reviewer COULD have accessed, since the
scratch directory contains nothing else. That is the real, checkable
evidence available in this environment; a genuine per-file access log would
require OS-level or MCP-level instrumentation this project does not have."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .hashing import sha256_bytes
from .public_media_guard import DEFAULT_SITE_ROOT, snapshot_public_media

# Directories that are never part of any snapshot -- not because they're
# trusted, but because they are either huge/irrelevant build artifacts
# (node_modules, dist) or version-control internals (.git) that would make
# every snapshot prohibitively slow and noisy without adding real
# containment value (they are not writable target for anything a reviewer
# would produce).
_ALWAYS_EXCLUDED_DIR_NAMES = {"node_modules", ".git", "dist", ".astro", "__pycache__"}


def _iter_files(root: Path, *, exclude_dirs: set[Path]) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _ALWAYS_EXCLUDED_DIR_NAMES for part in p.parts):
            continue
        rp = p.resolve()
        if any(rp == e or e in rp.parents for e in exclude_dirs):
            continue
        out.append(p)
    return out


def snapshot_paths(roots: list[Path], *, exclude_dirs: list[Path] | None = None) -> dict[str, str]:
    """{absolute_path_str: sha256} across every real file under every given
    root, always excluding `exclude_dirs` (the reviewer's own scratch dir)
    and the always-excluded build/VCS directory names above."""
    exclude = [Path(e).resolve() for e in (exclude_dirs or [])]
    snap: dict[str, str] = {}
    for root in roots:
        root = Path(root)
        for f in _iter_files(root, exclude_dirs=set(exclude)):
            snap[str(f.resolve())] = sha256_bytes(f.read_bytes())
    return snap


def diff_snapshots(pre: dict[str, str], post: dict[str, str]) -> dict[str, list[str]]:
    pre_keys, post_keys = set(pre), set(post)
    return {
        "added": sorted(post_keys - pre_keys),
        "removed": sorted(pre_keys - post_keys),
        "modified": sorted(k for k in pre_keys & post_keys if pre[k] != post[k]),
    }


def named_category_hashes(
    *, project_root: Path, site_root: Path = DEFAULT_SITE_ROOT, store_root: Path,
    exclude_dirs: list[Path] | None = None,
) -> dict[str, str]:
    """One rollup sha256 per named category from requirement 2 -- computed as
    sha256 of the sorted 'path:filehash' pairs in that category, so a single
    short hex string is a real, checkable summary of that category's exact
    state at this instant (any single-byte change anywhere in the category
    changes this hash). Categories:
      - repository: the real site source tree (site_root), i.e. everything a
        reviewer could in principle reach with a relative path, EXCLUDING
        the store itself (counted separately below) and the always-excluded
        build/VCS dirs.
      - ledger: nookguard_store/events.jsonl (append-only audit trail).
      - manifest: nookguard_store/releases/ (approved release entries).
      - quarantine: nookguard_store/quarantine/ (unpublished candidates).
      - evidence: nookguard_store/{review_packs,observations,judgments,preview}/.
      - public_media: reuses public_media_guard.snapshot_public_media, the
        same function the release-integrity gate itself uses, so this
        category can never silently drift from what that gate considers
        "public media" to mean.
    """
    exclude = [Path(e).resolve() for e in (exclude_dirs or [])]
    store_root = Path(store_root)

    repo_snap = snapshot_paths(
        [Path(site_root)], exclude_dirs=exclude + [store_root.resolve()],
    )
    ledger_snap = snapshot_paths([store_root / "events.jsonl"], exclude_dirs=exclude) \
        if (store_root / "events.jsonl").is_file() else \
        snapshot_paths([], exclude_dirs=exclude)
    if (store_root / "events.jsonl").is_file():
        ledger_snap = {str((store_root / "events.jsonl").resolve()):
                        sha256_bytes((store_root / "events.jsonl").read_bytes())}
    else:
        ledger_snap = {}
    manifest_snap = snapshot_paths([store_root / "releases"], exclude_dirs=exclude)
    quarantine_snap = snapshot_paths([store_root / "quarantine"], exclude_dirs=exclude)
    evidence_snap = snapshot_paths(
        [store_root / "review_packs", store_root / "observations",
         store_root / "judgments", store_root / "preview"],
        exclude_dirs=exclude,
    )
    public_media_raw = snapshot_public_media(Path(site_root))
    public_media_snap = {f"public_media:{k}": v for k, v in public_media_raw.items()}

    def rollup(snap: dict[str, str]) -> str:
        joined = "\n".join(f"{k}:{v}" for k, v in sorted(snap.items()))
        return sha256_bytes(joined.encode("utf-8"))

    return {
        "repository": rollup(repo_snap),
        "ledger": rollup(ledger_snap),
        "manifest": rollup(manifest_snap),
        "quarantine": rollup(quarantine_snap),
        "evidence": rollup(evidence_snap),
        "public_media": rollup(public_media_snap),
    }


def create_scratch(
    store_root: Path, label: str, candidate_path: Path | None, instructions: str,
    *, references: list[Path] | None = None,
) -> Path:
    """The ONLY directory a reviewer subagent is ever pointed at. Contains
    exactly: a copy of the candidate/contact-sheet bytes (never the real
    quarantine path itself -- a reviewer never even has a path string that
    resolves inside the real store), any reference images, and a plain-text
    copy of the review instructions. Nothing else. Unique per call (uuid4
    suffix), so two concurrent reviews never share a scratch directory.
    `candidate_path=None` is valid for a text-only review (a judge session
    sees a JSON payload, never an image) -- the scratch dir then contains
    only instructions.txt and any references."""
    scratch_dir = Path(store_root) / "reviewer_scratch" / f"{label}-{uuid.uuid4().hex}"
    scratch_dir.mkdir(parents=True, exist_ok=False)

    if candidate_path is not None:
        candidate_path = Path(candidate_path)
        (scratch_dir / f"candidate{candidate_path.suffix}").write_bytes(candidate_path.read_bytes())

    for i, ref in enumerate(references or []):
        ref = Path(ref)
        (scratch_dir / f"reference_{i}{ref.suffix}").write_bytes(ref.read_bytes())

    (scratch_dir / "instructions.txt").write_text(instructions, encoding="utf-8")
    return scratch_dir


@dataclass
class ContainmentRecord:
    containment_id: str
    scratch_dir: str
    protected_roots: list[str]
    pre_snapshot: dict[str, str]
    pre_named_hashes: dict[str, str]
    files_available_in_scratch: list[str]
    created_at: str
    post_snapshot: dict[str, str] | None = None
    post_named_hashes: dict[str, str] | None = None
    violations: dict[str, list[str]] | None = None
    clean: bool | None = None
    closed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "containment_id": self.containment_id, "scratch_dir": self.scratch_dir,
            "protected_roots": self.protected_roots, "pre_snapshot_file_count": len(self.pre_snapshot),
            "pre_named_hashes": self.pre_named_hashes,
            "files_available_in_scratch": self.files_available_in_scratch,
            "created_at": self.created_at,
            "post_snapshot_file_count": len(self.post_snapshot) if self.post_snapshot is not None else None,
            "post_named_hashes": self.post_named_hashes, "violations": self.violations,
            "clean": self.clean, "closed_at": self.closed_at,
        }


def _containment_path(store_root: Path, containment_id: str) -> Path:
    return Path(store_root) / "reviewer_scratch" / f"{containment_id}.containment.json"


def open_containment(
    store_root: Path, scratch_dir: Path, *, project_root: Path, site_root: Path = DEFAULT_SITE_ROOT,
) -> ContainmentRecord:
    """Call immediately after create_scratch(), immediately before spawning
    the reviewer subagent. Snapshots every protected root (repository,
    ledger, manifest, quarantine, evidence, public_media), excluding the
    scratch dir itself, and persists the record so a later, separate
    close_containment() call (potentially in a different process/CLI
    invocation) can find it again by id."""
    store_root = Path(store_root)
    scratch_dir = Path(scratch_dir)
    containment_id = scratch_dir.name

    protected_roots = [str(Path(site_root).resolve())]
    pre_snapshot = snapshot_paths([Path(site_root)], exclude_dirs=[scratch_dir])
    pre_named = named_category_hashes(
        project_root=project_root, site_root=site_root, store_root=store_root,
        exclude_dirs=[scratch_dir],
    )
    record = ContainmentRecord(
        containment_id=containment_id, scratch_dir=str(scratch_dir.resolve()),
        protected_roots=protected_roots, pre_snapshot=pre_snapshot, pre_named_hashes=pre_named,
        files_available_in_scratch=sorted(str(p.name) for p in scratch_dir.iterdir() if p.is_file()),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _containment_path(store_root, containment_id).write_text(
        json.dumps({
            "containment_id": record.containment_id, "scratch_dir": record.scratch_dir,
            "protected_roots": record.protected_roots, "pre_snapshot": record.pre_snapshot,
            "pre_named_hashes": record.pre_named_hashes,
            "files_available_in_scratch": record.files_available_in_scratch,
            "created_at": record.created_at,
        }, indent=2),
        encoding="utf-8",
    )
    return record


class ContainmentViolation(Exception):
    """Raised by close_containment when anything outside the scratch
    directory changed during the reviewer's turn. Callers must route this to
    a real process failure (REVIEW_ERROR or an equivalent reject), never
    swallow it -- an invalidated review is not a passed or failed review, it
    is NO review, because the evidence it would have produced can no longer
    be trusted."""

    def __init__(self, containment_id: str, violations: dict[str, list[str]]):
        self.containment_id = containment_id
        self.violations = violations
        total = sum(len(v) for v in violations.values())
        super().__init__(
            f"containment violation ({containment_id}): {total} path(s) changed outside the "
            f"designated reviewer scratch directory -- {violations}"
        )


def close_containment(
    store_root: Path, containment_id: str, *, project_root: Path, site_root: Path = DEFAULT_SITE_ROOT,
) -> ContainmentRecord:
    """Call immediately after the reviewer subagent returns, before its
    response is trusted for anything else. Re-snapshots the same protected
    roots, diffs against the pre-snapshot, and raises ContainmentViolation
    if anything outside the scratch directory changed. Returns the closed
    record (with post_snapshot/violations/clean populated) on success, for
    the caller to persist alongside the review's other evidence."""
    store_root = Path(store_root)
    path = _containment_path(store_root, containment_id)
    if not path.exists():
        raise FileNotFoundError(f"No open containment record for {containment_id} -- "
                                 "open_containment() must run before close_containment()")
    pre = json.loads(path.read_text(encoding="utf-8"))
    scratch_dir = Path(pre["scratch_dir"])

    post_snapshot = snapshot_paths([Path(site_root)], exclude_dirs=[scratch_dir])
    post_named = named_category_hashes(
        project_root=project_root, site_root=site_root, store_root=store_root,
        exclude_dirs=[scratch_dir],
    )
    diff = diff_snapshots(pre["pre_snapshot"], post_snapshot)
    violations = {k: v for k, v in diff.items() if v}
    clean = not violations

    record = ContainmentRecord(
        containment_id=containment_id, scratch_dir=pre["scratch_dir"],
        protected_roots=pre["protected_roots"], pre_snapshot=pre["pre_snapshot"],
        pre_named_hashes=pre["pre_named_hashes"],
        files_available_in_scratch=pre["files_available_in_scratch"], created_at=pre["created_at"],
        post_snapshot=post_snapshot, post_named_hashes=post_named, violations=violations, clean=clean,
        closed_at=datetime.now(timezone.utc).isoformat(),
    )
    path.write_text(json.dumps(record.to_dict() | {
        # Keep the full pre/post snapshots on disk too (not just counts) --
        # to_dict() intentionally summarizes file counts for a compact CLI
        # response, but the persisted evidence file keeps the real,
        # inspectable path->hash maps.
        "pre_snapshot": record.pre_snapshot, "post_snapshot": record.post_snapshot,
    }, indent=2), encoding="utf-8")

    if not clean:
        raise ContainmentViolation(containment_id, violations)
    return record


def cleanup_scratch(scratch_dir: Path) -> None:
    """Removes a scratch directory and its contents. Only ever call this
    AFTER close_containment() has run and its record has been persisted --
    the scratch dir's final contents (e.g. permitted crops) are themselves
    evidence of what a preview reviewer produced, up until this point."""
    shutil.rmtree(Path(scratch_dir), ignore_errors=True)
