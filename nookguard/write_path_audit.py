"""Write-path audit (Commit 21, requirement 5): "Add an audit that
searches for every code path capable of writing to public media or
invoking deployment." This is a static, textual search over the real repo
tree -- it does not execute anything, and it does not by itself block
anything (that's `public_media_guard.audit_public_media()`'s and
`hooks.py`'s job). Its purpose is enumeration: make every such code path
visible and named, so "nothing writes to public media except NookGuard's
own release path" is a checkable claim against a real list, not an
assumption resting on nobody having found a counterexample yet.

Scope, decided deliberately (documented here, not silently assumed): this
audit searches the SITE REPOSITORY tree only (everything under the project
root NookGuard actually lives in and can enforce against via real hooks/CI
-- .py/.mjs/.js/.ts/.ps1/.sh/.ts files). It does NOT search outside this
repository (e.g. C:\\Users\\weare\\Documents\\Claude\\Scheduled\\*, VoidCast,
or any other project) -- those are out of NookGuard's actual reach and a
real audit claim should not imply coverage it cannot back up. As of Commit
21, a real search of this repository found NO existing Python image-
generation scripts (the historical gen_garage_images.py / gen_product_
images.py / etc. scripts the parent CLAUDE.md documents as the live daily-
pipeline tooling are not present in this checked-out tree) -- see
docs/nookguard/BUILD-LOG.md's Commit 21 entry for the real, verified
absence and what that does and doesn't mean for containment.

`tests/` directories are excluded from scanning (added after this module's
own CLI-level test, test_write_path_audit_cli_real_site_tree, caught 5 real
matches against the live repo -- all of them this module's own test files,
e.g. `nookguard/tests/test_write_path_audit.py`, whose test fixtures
deliberately construct a synthetic write call against a fake published-
media path, in one crafted source line, purely to prove the marker-pair
matching logic actually fires. A test fixture proving the detector works
is not itself a real write path -- cli.py's own cmd_write_path_audit
docstring already flags "a legitimate test fixture" as an expected source
of false positives; excluding tests/ removes the most common, permanent
instance of exactly that instead of re-triaging it by hand every time a
new test is added to this module or public_media_guard's own test suite.
(NOTE for anyone editing this docstring further: avoid writing a write-
call marker and a media-path marker, e.g. a `.save(` call alongside a
`public/winnie`-style path, on the SAME line here -- this file is itself
inside the scanned tree, so a literal example in prose form can and once
did trigger its own detector.)"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# File extensions worth scanning for write/deploy-capable code. Binary/
# media/lockfile/build-output extensions are excluded by directory below,
# not by extension, since a .py file could live inside dist/ in principle.
_SCANNABLE_EXTENSIONS = (".py", ".mjs", ".js", ".ts", ".ps1", ".sh")

# Directories never worth scanning -- build output, dependencies, and the
# NookGuard store itself (which legitimately references these path
# fragments constantly as its own subject matter, not as a write target).
_EXCLUDED_DIR_PARTS = ("node_modules", "dist", ".git", "nookguard_store",
                       "__pycache__", ".astro", "tests")

# Requirement 5, part 1: code capable of writing to a published media
# path. Matched as (write-call marker, path marker) PAIRS -- both must
# appear on the same line, same discipline hooks.py's H002 already uses,
# so a benign comment mentioning "public/winnie" without any real write
# call is never false-flagged.
_MEDIA_WRITE_CALL_MARKERS = (
    ".save(", "shutil.copy", "shutil.copyfile", "write_bytes(", "open(",
    "writeFile", "copyFile", "fs.write", "Set-Content", "Out-File",
)
_MEDIA_PATH_MARKERS = ("public/winnie", "public/cursors", "public/pins",
                        "public/tools", "public/recipes", "public/products",
                        "public\\winnie", "public\\products")

# Requirement 5, part 2: code capable of invoking deployment.
_DEPLOY_MARKERS = (
    "wrangler pages deploy", "wrangler deploy", "cloudflare",
    "git push origin main", "git push origin production",
)


@dataclass
class WritePathAuditFinding:
    file: str
    line_number: int
    line_text: str
    category: str  # "media_write" | "deploy_invocation"
    matched_markers: tuple[str, ...]


@dataclass
class WritePathAuditReport:
    findings: list[WritePathAuditFinding] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def media_write_findings(self) -> list[WritePathAuditFinding]:
        return [f for f in self.findings if f.category == "media_write"]

    @property
    def deploy_findings(self) -> list[WritePathAuditFinding]:
        return [f for f in self.findings if f.category == "deploy_invocation"]


DEFAULT_SITE_ROOT = Path(__file__).resolve().parent.parent


def _is_excluded(path: Path) -> bool:
    return any(part in _EXCLUDED_DIR_PARTS for part in path.parts)


def _scan_file(path: Path, site_root: Path) -> list[WritePathAuditFinding]:
    findings: list[WritePathAuditFinding] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    rel = path.relative_to(site_root).as_posix()
    for line_number, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()

        media_call_hits = [m for m in _MEDIA_WRITE_CALL_MARKERS if m.lower() in lowered]
        media_path_hits = [m for m in _MEDIA_PATH_MARKERS if m.lower() in lowered]
        if media_call_hits and media_path_hits:
            findings.append(WritePathAuditFinding(
                file=rel, line_number=line_number, line_text=line.strip(), category="media_write",
                matched_markers=tuple(media_call_hits + media_path_hits),
            ))

        deploy_hits = [m for m in _DEPLOY_MARKERS if m.lower() in lowered]
        if deploy_hits:
            findings.append(WritePathAuditFinding(
                file=rel, line_number=line_number, line_text=line.strip(), category="deploy_invocation",
                matched_markers=tuple(deploy_hits),
            ))

    return findings


def run_write_path_audit(site_root: Path = DEFAULT_SITE_ROOT) -> WritePathAuditReport:
    """Walks the real repository tree (scope documented in this module's
    own docstring -- `site_root` here means the same real `site/`
    directory `public_media_guard.py`'s DEFAULT_SITE_ROOT means, NOT
    cli.py's differently-scoped `--project-root` default; see that
    module's comment for why the distinction is real, not pedantic) and
    returns every line that looks like it could write to published media
    or invoke deployment. Purely additive/enumerative -- never raises,
    never blocks; `ok`-style gating belongs to public_media_guard.
    audit_public_media() and the deploy command, not here."""
    site_root = Path(site_root)
    report = WritePathAuditReport()

    for path in sorted(site_root.rglob("*")):
        if not path.is_file():
            continue
        if not path.name.lower().endswith(_SCANNABLE_EXTENSIONS):
            continue
        if _is_excluded(path.relative_to(site_root)):
            continue
        report.files_scanned += 1
        report.findings.extend(_scan_file(path, site_root))

    return report


def report_to_dict(report: WritePathAuditReport) -> dict[str, Any]:
    return {
        "files_scanned": report.files_scanned,
        "media_write_count": len(report.media_write_findings),
        "deploy_invocation_count": len(report.deploy_findings),
        "media_write_findings": [
            {"file": f.file, "line": f.line_number, "text": f.line_text, "markers": list(f.matched_markers)}
            for f in report.media_write_findings
        ],
        "deploy_findings": [
            {"file": f.file, "line": f.line_number, "text": f.line_text, "markers": list(f.matched_markers)}
            for f in report.deploy_findings
        ],
    }
