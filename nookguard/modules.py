"""Prompt-module registry + source map + compatibility rules (Commit 4's other
half). Modeled directly on the real failure this is meant to prevent: the main
project's `scripts/image_style.py` has named style constants (e.g.
STYLE_LIFESTYLE_SCENE vs STYLE_LIFESTYLE_SCENE_OUTDOOR) that must NOT both be
applied to the same prompt — mixing them is exactly how the 'stray armchair in
an outdoor scene' defect happened (see main CLAUDE.md, 2026-07-18 finding).
This registry makes that an enforced compile-time check instead of something a
human has to remember."""

from __future__ import annotations

from dataclasses import dataclass

from .hashing import sha256_bytes


@dataclass(frozen=True)
class PromptModule:
    name: str
    version: str
    text: str
    source_note: str  # where this module's rule/finding came from

    @property
    def module_sha256(self) -> str:
        return sha256_bytes(f"{self.name}:{self.version}:{self.text}".encode("utf-8"))


# Real example pair from the main project's documented incident (2026-07-18):
# a "lifestyle scene" style module written for indoor settings reliably
# hallucinated furniture into outdoor/nature scenes when combined with an
# outdoor location. The fix there was a SEPARATE outdoor-specific module, not
# a flag — so the two must never both be selected for one prompt.
INCOMPATIBLE_PAIRS: set[frozenset[str]] = {
    frozenset({"style_lifestyle_scene_indoor", "style_lifestyle_scene_outdoor"}),
}


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, PromptModule] = {}

    def register(self, module: PromptModule) -> None:
        self._modules[module.name] = module

    def get(self, name: str) -> PromptModule:
        if name not in self._modules:
            raise KeyError(f"No registered prompt module named '{name}'")
        return self._modules[name]

    def list_names(self) -> list[str]:
        return sorted(self._modules.keys())

    def check_compatibility(self, module_names: list[str]) -> list[str]:
        """Returns human-readable violation strings; empty list = compatible.
        A prompt compile with any violation must fail (H007-adjacent rule) —
        this is a compiler-level check, never left to the generating session
        to notice on its own."""
        violations: list[str] = []
        chosen = set(module_names)
        for pair in INCOMPATIBLE_PAIRS:
            if pair.issubset(chosen):
                violations.append(f"Incompatible modules selected together: {sorted(pair)}")
        for name in module_names:
            if name not in self._modules:
                violations.append(f"Unknown module requested: '{name}'")
        return violations

    def compile_modules(self, module_names: list[str]) -> str:
        violations = self.check_compatibility(module_names)
        if violations:
            raise ValueError("; ".join(violations))
        return "\n".join(self.get(n).text for n in module_names)
