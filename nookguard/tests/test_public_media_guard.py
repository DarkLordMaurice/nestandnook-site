"""Commit 21: public-media containment tests. Real filesystem operations
throughout (real files, real hashes, real ReleaseManifestEntry records) --
no synthetic hash comparisons, since this module's entire job is comparing
real bytes against real approvals."""

from __future__ import annotations

import json
from pathlib import Path

from nookguard.hashing import sha256_bytes
from nookguard.manifest import ReleaseManifestEntry
from nookguard.public_media_guard import (
    MEDIA_EXTENSIONS,
    PUBLISHED_MEDIA_DIRS,
    audit_public_media,
    collect_approved_hashes,
    is_published_media_path,
    load_baseline,
    snapshot_public_media,
    write_baseline,
)


def test_is_published_media_path_matches_real_dirs_and_extensions():
    assert is_published_media_path("/x/site/public/winnie/hero.jpg") is True
    assert is_published_media_path(r"C:\proj\site\public\products\thing.png") is True
    assert is_published_media_path("/x/site/public/winnie/notes.txt") is False
    assert is_published_media_path("/x/site/src/components/hero.jpg") is False


def test_media_extensions_and_dirs_are_real_nonempty_tuples():
    assert len(MEDIA_EXTENSIONS) > 0
    assert len(PUBLISHED_MEDIA_DIRS) > 0


def _make_media_file(root: Path, rel: str, content: bytes) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def test_snapshot_public_media_finds_real_files_with_real_hashes(tmp_path):
    p = _make_media_file(tmp_path, "public/winnie/hero.jpg", b"real-bytes-1")
    snapshot = snapshot_public_media(tmp_path)
    assert "public/winnie/hero.jpg" in snapshot
    assert snapshot["public/winnie/hero.jpg"] == sha256_bytes(p.read_bytes())


def test_snapshot_public_media_ignores_non_media_and_outside_dirs(tmp_path):
    _make_media_file(tmp_path, "public/winnie/notes.txt", b"not media")
    _make_media_file(tmp_path, "src/components/hero.jpg", b"not published")
    snapshot = snapshot_public_media(tmp_path)
    assert snapshot == {}


def test_baseline_round_trip(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    write_baseline({"public/winnie/a.jpg": "abc123"}, baseline_path)
    loaded = load_baseline(baseline_path)
    assert loaded == {"public/winnie/a.jpg": "abc123"}
    assert json.loads(baseline_path.read_text())  # real, valid JSON on disk


def test_load_baseline_missing_file_returns_empty_dict(tmp_path):
    assert load_baseline(tmp_path / "does-not-exist.json") == {}


def test_collect_approved_hashes_reads_real_release_manifest_entries(tmp_path):
    store_root = tmp_path / "store1"
    releases_dir = store_root / "releases"
    releases_dir.mkdir(parents=True)
    entry = ReleaseManifestEntry(
        release_id="r1", run_id="run1", asset_id="asset1", candidate_sha256="deadbeef",
        public_path="/x/public/winnie/x.jpg", public_url="https://example.com/x.jpg",
    )
    (releases_dir / "deadbeef.json").write_text(entry.model_dump_json(), encoding="utf-8")

    approved = collect_approved_hashes([store_root])
    assert approved == {"deadbeef"}


def test_collect_approved_hashes_unions_multiple_store_roots(tmp_path):
    for i, sha in enumerate(["hash1", "hash2"]):
        store_root = tmp_path / f"store{i}"
        releases_dir = store_root / "releases"
        releases_dir.mkdir(parents=True)
        entry = ReleaseManifestEntry(
            release_id=f"r{i}", run_id="run1", asset_id="asset1", candidate_sha256=sha,
            public_path="/x/y.jpg", public_url="https://example.com/y.jpg",
        )
        (releases_dir / f"{sha}.json").write_text(entry.model_dump_json(), encoding="utf-8")

    approved = collect_approved_hashes([tmp_path / "store0", tmp_path / "store1"])
    assert approved == {"hash1", "hash2"}


def test_collect_approved_hashes_ignores_corrupt_entries_not_crash(tmp_path):
    store_root = tmp_path / "store1"
    releases_dir = store_root / "releases"
    releases_dir.mkdir(parents=True)
    (releases_dir / "bad.json").write_text("not valid json at all", encoding="utf-8")
    assert collect_approved_hashes([store_root]) == set()


def test_collect_approved_hashes_missing_store_root_returns_empty(tmp_path):
    assert collect_approved_hashes([tmp_path / "nonexistent"]) == set()


# ---- audit_public_media: the real containment gate ----

def test_audit_passes_when_file_matches_baseline_exactly(tmp_path):
    _make_media_file(tmp_path, "public/winnie/hero.jpg", b"legacy-content")
    baseline = snapshot_public_media(tmp_path)
    baseline_path = tmp_path / "baseline.json"
    write_baseline(baseline, baseline_path)

    report = audit_public_media(tmp_path, baseline_path=baseline_path)
    assert report["ok"] is True
    assert report["unapproved_count"] == 0
    assert report["baseline_unchanged_count"] == 1


def test_audit_flags_brand_new_file_not_in_baseline_or_manifest(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    write_baseline({}, baseline_path)  # empty baseline -- nothing pre-existing
    _make_media_file(tmp_path, "public/winnie/brand-new.jpg", b"new-content")

    report = audit_public_media(tmp_path, baseline_path=baseline_path)
    assert report["ok"] is False
    assert report["unapproved_count"] == 1
    assert report["unapproved"][0]["path"] == "public/winnie/brand-new.jpg"
    assert "new file" in report["unapproved"][0]["reason"]


def test_audit_flags_baseline_file_that_was_modified(tmp_path):
    _make_media_file(tmp_path, "public/winnie/hero.jpg", b"original-content")
    baseline = snapshot_public_media(tmp_path)
    baseline_path = tmp_path / "baseline.json"
    write_baseline(baseline, baseline_path)

    # Now modify the bytes in place -- simulating a raw overwrite that
    # bypassed the release pipeline.
    _make_media_file(tmp_path, "public/winnie/hero.jpg", b"TAMPERED-content")

    report = audit_public_media(tmp_path, baseline_path=baseline_path)
    assert report["ok"] is False
    assert report["unapproved_count"] == 1
    assert "modified since baseline" in report["unapproved"][0]["reason"]


def test_audit_approves_a_new_file_whose_hash_is_in_a_real_release_manifest(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    write_baseline({}, baseline_path)
    p = _make_media_file(tmp_path, "public/winnie/released-abc123.jpg", b"real-released-content")
    real_hash = sha256_bytes(p.read_bytes())

    store_root = tmp_path / "nookguard_store"
    releases_dir = store_root / "releases"
    releases_dir.mkdir(parents=True)
    entry = ReleaseManifestEntry(
        release_id="r1", run_id="run1", asset_id="asset1", candidate_sha256=real_hash,
        public_path=str(p), public_url="https://example.com/released-abc123.jpg",
    )
    (releases_dir / f"{real_hash}.json").write_text(entry.model_dump_json(), encoding="utf-8")

    report = audit_public_media(tmp_path, baseline_path=baseline_path)  # default store_roots -> tmp_path/nookguard_store
    assert report["ok"] is True
    assert report["approved_release_count"] == 1
    assert report["unapproved_count"] == 0


def test_audit_reports_files_removed_from_baseline(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    write_baseline({"public/winnie/gone.jpg": "somehash"}, baseline_path)
    # Nothing on disk matching that baseline entry.
    report = audit_public_media(tmp_path, baseline_path=baseline_path)
    assert report["removed_from_baseline"] == ["public/winnie/gone.jpg"]
