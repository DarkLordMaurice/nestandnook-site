"""Tests use a temp project root with fake canon files, not the real project's
brand-assets — keeps this test deterministic and independent of anyone editing
real canon content later."""

import tempfile
from pathlib import Path

from nookguard.canon import CanonRegistry


def _make_root(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for rel, content in files.items():
        full = root / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return root


def test_missing_canon_files_reports_gaps():
    root = _make_root({"a.md": "hello"})
    registry = CanonRegistry(root, files=["a.md", "b.md"])
    assert registry.missing_canon_files() == ["b.md"]


def test_missing_canon_files_empty_when_all_present():
    root = _make_root({"a.md": "hello", "b.md": "world"})
    registry = CanonRegistry(root, files=["a.md", "b.md"])
    assert registry.missing_canon_files() == []


def test_bundle_sha256_changes_when_canon_content_changes():
    root = _make_root({"a.md": "v1"})
    registry = CanonRegistry(root, files=["a.md"])
    first = registry.bundle_sha256()

    (root / "a.md").write_text("v2", encoding="utf-8")
    second = registry.bundle_sha256()

    assert first != second


def test_bundle_sha256_stable_for_unchanged_content():
    root = _make_root({"a.md": "stable content"})
    registry = CanonRegistry(root, files=["a.md"])
    assert registry.bundle_sha256() == registry.bundle_sha256()


def test_check_bundle_is_current_true_only_for_matching_hash():
    root = _make_root({"a.md": "v1"})
    registry = CanonRegistry(root, files=["a.md"])
    current = registry.bundle_sha256()
    assert registry.check_bundle_is_current(current) is True
    assert registry.check_bundle_is_current("stale-hash") is False


def test_check_bundle_is_current_false_after_canon_edit():
    """This is the H007 scenario: a spec was locked against `locked_hash`,
    then canon changed underneath it — compile must be able to detect this."""
    root = _make_root({"a.md": "v1"})
    registry = CanonRegistry(root, files=["a.md"])
    locked_hash = registry.bundle_sha256()

    (root / "a.md").write_text("v2 — room bible correction", encoding="utf-8")

    assert registry.check_bundle_is_current(locked_hash) is False
