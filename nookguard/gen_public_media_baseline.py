"""Generates nookguard/public_media_baseline.json (Commit 21) -- a real,
one-time snapshot of every published media file's (relative_path, sha256)
pair at the moment public-media containment was introduced. This is the
"grandfather" list `public_media_guard.audit_public_media()` checks
against: a file matching its baseline entry exactly is legacy content that
predates NookGuard and is not itself a new finding; anything new or
changed from here forward must be an approved NookGuard release instead.

Run directly (`python -m nookguard.gen_public_media_baseline`) only when
deliberately re-baselining (e.g. after a real, reviewed bulk legacy-image
migration) -- NOT as a routine step, since re-running this after an
unapproved write would silently grandfather it in rather than flag it,
defeating the whole point of this commit."""

from __future__ import annotations

from .public_media_guard import DEFAULT_BASELINE_PATH, DEFAULT_SITE_ROOT, snapshot_public_media, write_baseline


def main() -> None:
    snapshot = snapshot_public_media(DEFAULT_SITE_ROOT)
    write_baseline(snapshot, DEFAULT_BASELINE_PATH)
    print(f"wrote {len(snapshot)} entries to {DEFAULT_BASELINE_PATH}")


if __name__ == "__main__":
    main()
