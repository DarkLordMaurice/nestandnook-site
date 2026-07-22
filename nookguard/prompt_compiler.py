"""Prompt compiler — minimal real version for Commit 3. Commit 4 replaces the
body of `compile_prompt` with a canon-aware version (module registry, stale-
source scan, room-bible/style-module injection) but keeps this signature, so
nothing calling it needs to change. COMPILER_VERSION bumps whenever the
compilation logic changes, since it flows into prompt_sha256 indirectly via
the text it produces."""

from __future__ import annotations

from .schemas import AssetContract

COMPILER_VERSION = "0.1.0-minimal"


def compile_prompt(contract: AssetContract) -> str:
    lines = [
        f"Subject: {contract.subject}",
        f"Action: {contract.action}",
        f"Scene: {contract.scene}",
    ]
    if contract.allowed_objects:
        lines.append("Allowed objects: " + ", ".join(contract.allowed_objects))
    if contract.forbidden_objects:
        lines.append("Forbidden objects (must not appear): " + ", ".join(contract.forbidden_objects))
    for req in contract.requirements:
        marker = "CRITICAL" if req.critical else "requirement"
        lines.append(f"[{marker}:{req.requirement_id}] {req.statement}")
    return "\n".join(lines)
