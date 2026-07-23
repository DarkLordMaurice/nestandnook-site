"""Commit 21, requirement 5: write-path audit tests. Real filesystem, real
files with deliberately-crafted lines -- checking the marker-pair matching
discipline (both a write-call marker AND a path marker must appear on the
SAME line) actually behaves as documented, not just that it runs."""

from __future__ import annotations

from pathlib import Path

from nookguard.write_path_audit import (
    DEFAULT_SITE_ROOT,
    report_to_dict,
    run_write_path_audit,
)


def test_finds_real_media_write_line_with_both_markers(tmp_path):
    f = tmp_path / "gen_thing.py"
    f.write_text(
        "def save():\n"
        "    img.save('public/winnie/thing.jpg')\n",
        encoding="utf-8",
    )
    report = run_write_path_audit(tmp_path)
    assert len(report.media_write_findings) == 1
    finding = report.media_write_findings[0]
    assert finding.file == "gen_thing.py"
    assert finding.line_number == 2


def test_ignores_line_with_only_path_marker_no_write_call(tmp_path):
    f = tmp_path / "notes.py"
    f.write_text(
        "# see public/winnie/thing.jpg for the reference image\n",
        encoding="utf-8",
    )
    report = run_write_path_audit(tmp_path)
    assert report.media_write_findings == []


def test_ignores_line_with_only_write_call_no_path_marker(tmp_path):
    f = tmp_path / "unrelated.py"
    f.write_text(
        "def save():\n"
        "    data.save('some/other/path.json')\n",
        encoding="utf-8",
    )
    report = run_write_path_audit(tmp_path)
    assert report.media_write_findings == []


def test_finds_real_deploy_invocation_line(tmp_path):
    f = tmp_path / "deploy.sh"
    f.write_text("wrangler pages deploy dist --project-name nestandnook-site\n", encoding="utf-8")
    report = run_write_path_audit(tmp_path)
    assert len(report.deploy_findings) == 1
    assert report.deploy_findings[0].file == "deploy.sh"


def test_excluded_directories_are_skipped(tmp_path):
    excluded = tmp_path / "node_modules" / "pkg"
    excluded.mkdir(parents=True)
    (excluded / "write.js").write_text(
        "fs.write('public/winnie/thing.jpg', data);\n", encoding="utf-8",
    )
    report = run_write_path_audit(tmp_path)
    assert report.findings == []
    assert report.files_scanned == 0


def test_files_scanned_counts_only_scannable_extensions(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.jpg").write_bytes(b"not code")
    (tmp_path / "c.md").write_text("# doc\n", encoding="utf-8")
    report = run_write_path_audit(tmp_path)
    assert report.files_scanned == 1


def test_report_to_dict_shape():
    from nookguard.write_path_audit import WritePathAuditFinding, WritePathAuditReport

    report = WritePathAuditReport(
        findings=[
            WritePathAuditFinding(file="x.py", line_number=3, line_text="img.save('public/winnie/x.jpg')",
                                   category="media_write", matched_markers=(".save(", "public/winnie")),
        ],
        files_scanned=5,
    )
    d = report_to_dict(report)
    assert d["files_scanned"] == 5
    assert d["media_write_count"] == 1
    assert d["deploy_invocation_count"] == 0
    assert d["media_write_findings"][0]["file"] == "x.py"


def test_real_site_tree_has_zero_media_write_findings():
    """Regression guard matching the real, already-verified result from
    Commit 21 development: this repository currently has no code path that
    writes bytes directly to a published media directory. If this ever
    starts failing, it means either a real legacy generation script showed
    up in the tree (requirement 3's exact concern) or the marker set is
    now too broad -- either way, worth a human look, not a silent skip."""
    report = run_write_path_audit(DEFAULT_SITE_ROOT)
    assert report.files_scanned > 0
    assert report.media_write_findings == []
