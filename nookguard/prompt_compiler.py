"""Prompt compiler — Commit 4: canon-aware version. Replaces Commit 3's plain
concatenation with (1) a hard check that every canon file the registry expects
actually exists, (2) H007 enforcement — a spec locked against an older canon
bundle hash fails compile rather than silently drifting, and (3) prompt-module
injection through ModuleRegistry, whose whole point is to make the real
'STYLE_LIFESTYLE_SCENE hallucinating furniture into outdoor scenes' incident
(main project CLAUDE.md, 2026-07-18) structurally impossible to repeat: the
indoor and outdoor style modules are registered as mutually exclusive and
selected by a scene heuristic, never both.

Signature is unchanged from Commit 3 (`compile_prompt(contract) -> str`) so
nothing calling it needs to change; project_root/canon_registry/module_registry
are optional overrides for testing."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .canon import CanonRegistry
from .exceptions import MissingCanonError, StaleCanonError
from .modules import ModuleRegistry, PromptModule
from .schemas import AssetContract

COMPILER_VERSION = "0.2.0-canon-aware"

# nookguard/prompt_compiler.py -> nookguard -> site -> project root
_DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Real incident this encodes (main CLAUDE.md, 2026-07-18): a "lifestyle scene"
# style module written assuming an indoor, curated background reliably
# hallucinated furniture into genuinely outdoor scenes (a goat pen, an otter
# pond, a hilltop trail). Fix there was a separate outdoor-only module with an
# explicit no-furniture clause — never a flag on one shared module.
_STYLE_LIFESTYLE_SCENE_INDOOR = PromptModule(
    name="style_lifestyle_scene_indoor",
    version="1.0.0",
    text=(
        "Style: warm, lived-in indoor lifestyle photography. A curated, "
        "believable background consistent with the room is expected and "
        "encouraged."
    ),
    source_note="main CLAUDE.md — original STYLE_LIFESTYLE_SCENE constant",
)
_STYLE_LIFESTYLE_SCENE_OUTDOOR = PromptModule(
    name="style_lifestyle_scene_outdoor",
    version="1.0.0",
    text=(
        "Style: warm, candid outdoor/nature/public-venue lifestyle "
        "photography. Do not introduce indoor furniture, upholstery, or "
        "home decor of any kind into this scene."
    ),
    source_note="main CLAUDE.md 2026-07-18 fix — STYLE_LIFESTYLE_SCENE_OUTDOOR",
)

_OUTDOOR_SCENE_KEYWORDS = {
    "outdoor", "patio", "trail", "yard", "garden", "park", "hilltop",
    "campsite", "zoo", "pond", "aviary", "pen", "enclosure", "smoker",
    "overlook", "hiking",
}
_INDOOR_SCENE_KEYWORDS = {
    "office", "kitchen", "garage", "living room", "hallway", "entry",
    "bedroom", "indoor", "duplex", "studio",
}


def default_module_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(_STYLE_LIFESTYLE_SCENE_INDOOR)
    registry.register(_STYLE_LIFESTYLE_SCENE_OUTDOOR)
    return registry


def _select_scene_style_modules(scene: str) -> list[str]:
    """Heuristic module selection from the contract's free-text `scene`
    field. Deliberately conservative: only selects a module when the scene
    text gives an actual signal, and never selects both — the incompatible
    pair check in ModuleRegistry is a second, structural line of defense on
    top of this, not the only one."""
    scene_lower = scene.lower()
    if any(kw in scene_lower for kw in _OUTDOOR_SCENE_KEYWORDS):
        return ["style_lifestyle_scene_outdoor"]
    if any(kw in scene_lower for kw in _INDOOR_SCENE_KEYWORDS):
        return ["style_lifestyle_scene_indoor"]
    return []


def compile_prompt(
    contract: AssetContract,
    project_root: Optional[str | Path] = None,
    canon_registry: Optional[CanonRegistry] = None,
    module_registry: Optional[ModuleRegistry] = None,
) -> str:
    registry = canon_registry or CanonRegistry(project_root or _DEFAULT_PROJECT_ROOT)

    missing = registry.missing_canon_files()
    if missing:
        raise MissingCanonError(missing)

    if contract.canonical_reference_bundle_sha256:
        if not registry.check_bundle_is_current(contract.canonical_reference_bundle_sha256):
            raise StaleCanonError(
                referenced=contract.canonical_reference_bundle_sha256,
                current=registry.bundle_sha256(),
            )

    modules = module_registry or default_module_registry()
    selected = _select_scene_style_modules(contract.scene)
    violations = modules.check_compatibility(selected)
    if violations:
        raise ValueError("; ".join(violations))

    lines = [
        f"Canon bundle: {registry.bundle_sha256()}",
        f"Subject: {contract.subject}",
        f"Action: {contract.action}",
        f"Scene: {contract.scene}",
    ]
    if selected:
        lines.append(modules.compile_modules(selected))
    if contract.allowed_objects:
        lines.append("Allowed objects: " + ", ".join(contract.allowed_objects))
    if contract.forbidden_objects:
        lines.append("Forbidden objects (must not appear): " + ", ".join(contract.forbidden_objects))
    for req in contract.requirements:
        marker = "CRITICAL" if req.critical else "requirement"
        lines.append(f"[{marker}:{req.requirement_id}] {req.statement}")
    return "\n".join(lines)
