"""Real Claude Code project-hook enforcement logic (Commit 11, Appendix G).
Structured as pure functions taking (tool_name, tool_input, project_root) so
the actual policy is unit-testable without a live Claude Code hook
invocation -- the thin `.claude/hooks/pretooluse.py` wrapper (not covered by
pytest, since it only reads stdin/writes stdout) is deliberately just glue
around `evaluate_pretooluse()`, matching this project's existing cli.py /
cmd_* split.

Schema and blocking mechanics were verified directly against the real
Claude Code hooks reference (code.claude.com/docs/en/hooks) before writing
this -- not guessed. PreToolUse hooks receive `tool_name` + `tool_input` on
stdin; a hook blocks the call by printing, on stdout with exit 0:
    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                             "permissionDecision": "deny",
                             "permissionDecisionReason": "..."}}
Silence (exit 0, no output) means no decision -- the tool call proceeds.

Covers hooks H001-H004, H008, H009 from Appendix G's table. H005, H006,
H007, H010 are NOT implemented as new hook code here -- see this module's
docstring notes on each and docs/nookguard/BUILD-LOG.md's Commit 11 entry
for why each is out of scope or already satisfied elsewhere."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from .public_media_guard import is_published_media_path

# ---- H001: Write/Edit to protected path -> deny; return required mediactl
# command. "Protected path" = NookGuard's own store -- content-addressed and
# state-machine-owned by store.py. A raw Write/Edit into it bypasses every
# hash/state check every mediactl command performs.
PROTECTED_STORE_DIRNAME = "nookguard_store"

# ---- H002: Bash calls a generation endpoint directly -> deny; only the
# adapter command (`mediactl generate`) may reach a real model. Paired
# markers (both must appear) rather than a bare package/URL name, so a
# benign `pip install gradio_client` or `pip show anthropic` is never
# false-flagged -- only an actual invocation-shaped command is.
_GENERATION_INVOCATION_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("gradio_client", ".predict("), "a gradio_client .predict() call"),
    (("gradio_client", ".submit("), "a gradio_client .submit() call"),
    (("huggingface.co/spaces", "curl"), "a direct curl to a Hugging Face Space"),
    (("huggingface.co/spaces", "wget"), "a direct wget to a Hugging Face Space"),
    (("anthropic.Anthropic(", ".messages.create("), "a direct Anthropic Messages API call"),
]
_SANCTIONED_BASH_MARKERS = ("mediactl", "pytest")

# ---- H003: Bash uses blanket git staging -> deny. Matches the standing
# CLAUDE.md rule ("never git add -A/.") as a mechanically enforced hook
# instead of a prose instruction the main project's own history shows gets
# skipped when it isn't enforced.
_BLANKET_GIT_ADD_RE = re.compile(r"git\s+add\s+(-A\b|--all\b|\.\s*$|\.\s+&&|\.\s*;)")

# ---- H004: Bash targets the production branch -> deny (the "unless CI
# release role token" exception from Appendix G is Commit 12 territory -- no
# release-role concept exists yet, so this hook denies unconditionally for
# now; see BUILD-LOG's Commit 11 entry).
_PRODUCTION_BRANCH_RE = re.compile(r"\b(checkout|push(\s+\S+)?|merge|branch\s+-[dD])\s+.*\bproduction\b")

# ---- H008: any Write to a published media path -> deny. Scoped to Write
# (Write always fully replaces file content -- "Creates or overwrites a
# file" per the real tool schema). Strengthened in Commit 21 (public-media
# containment): originally this only blocked overwriting an ALREADY-
# EXISTING file at a published path -- a brand-new file at a published
# path (e.g. a freshly content-hashed filename a Claude session wrote
# directly instead of going through `mediactl release`) sailed straight
# through, which is exactly the gap Commit 21's real containment work
# closed. Media-path/extension rules now live in public_media_guard.py
# (imported above) as the single source of truth, rather than duplicated
# here -- `mediactl media-audit`'s repository-validation layer and this
# live Claude-tool hook must never define "published media" differently.


def _is_protected_store_path(file_path: str) -> bool:
    parts = Path(file_path.replace("\\", "/")).parts
    return PROTECTED_STORE_DIRNAME in parts


def check_write_edit_protected_path(tool_input: dict[str, Any]) -> Optional[str]:
    file_path = tool_input.get("file_path", "")
    if _is_protected_store_path(file_path):
        return (
            f"H001: '{file_path}' is inside the NookGuard store "
            f"('{PROTECTED_STORE_DIRNAME}/'), which is content-addressed and "
            "state-machine-owned. Direct Write/Edit bypasses the hash and "
            "state checks every mediactl command performs. Use the matching "
            "mediactl subcommand (spec-lock, register, observe, judge, "
            "integrate, preview-capture, preview-review, etc.) instead."
        )
    return None


def check_bash_generation_endpoint(command: str) -> Optional[str]:
    if any(marker in command for marker in _SANCTIONED_BASH_MARKERS):
        return None
    for markers, description in _GENERATION_INVOCATION_PATTERNS:
        if all(marker in command for marker in markers):
            return (
                f"H002: this Bash command looks like {description}, reaching "
                "a real generation endpoint directly instead of through "
                "`mediactl generate`. Direct calls skip contract, prompt, "
                "and candidate registration entirely."
            )
    return None


def check_bash_blanket_git_add(command: str) -> Optional[str]:
    if _BLANKET_GIT_ADD_RE.search(command):
        return (
            "H003: blanket git staging ('git add -A' / '--all' / '.') is "
            "denied project-wide -- this repo has real stray untracked "
            "files (see main CLAUDE.md) that must never be swept into a "
            "commit. Stage the specific files you changed, by name."
        )
    return None


def check_bash_production_branch(command: str) -> Optional[str]:
    if _PRODUCTION_BRANCH_RE.search(command):
        return (
            "H004: this Bash command targets the 'production' branch. No "
            "CI release-role token concept exists yet (Commit 12 territory), "
            "so production-branch operations are denied unconditionally for "
            "now. If this is genuinely a release action, it needs Maurice's "
            "own access, not an automated session."
        )
    return None


def check_bash(command: str) -> Optional[str]:
    """Runs every Bash-scoped rule (H003, H004, H002, in that order --
    staging/branch-safety checks are cheaper and more common than the
    generation-endpoint check, so they run first), returning the first
    violation found."""
    for check in (check_bash_blanket_git_add, check_bash_production_branch,
                  check_bash_generation_endpoint):
        reason = check(command)
        if reason:
            return reason
    return None


def check_write_to_published_media(tool_input: dict[str, Any], project_root: Path) -> Optional[str]:
    """H008 (strengthened Commit 21). Denies ANY Write targeting a
    published media path -- new file or existing overwrite alike. A new
    file at a published path is exactly as much a containment bypass as
    overwriting one (requirement 1: 'block all NEW and modified public
    media'); the pre-Commit-21 version only caught the overwrite case."""
    file_path = tool_input.get("file_path", "")
    if not is_published_media_path(file_path):
        return None
    is_new = not (Path(file_path) if Path(file_path).is_absolute()
                  else project_root / file_path).exists()
    return (
        f"H008: '{file_path}' targets a published media path"
        f"{' (new file)' if is_new else ' (already-published, existing file)'}. "
        "Direct Write bypasses the release pipeline and public-media "
        "containment (mediactl media-audit would flag this). Generate a "
        "real candidate through the NookGuard pipeline (mediactl generate "
        "-> ... -> mediactl release) instead of writing bytes directly to "
        "a published path."
    )


def check_content_lint_on_edit(tool_name: str, tool_input: dict[str, Any], project_root: Path) -> Optional[str]:
    """H009. Simulates the hypothetical post-edit file content -- the
    current on-disk content with the Edit's old_string/new_string applied,
    or the Write's content directly -- and runs the real
    off_the_clock_schema lint against it. This catches a legacy-component
    regression (or a broken photo-strip count) BEFORE it lands, not after a
    separate `mediactl content-lint` run notices it."""
    file_path = tool_input.get("file_path", "")
    if not file_path.replace("\\", "/").lower().endswith(".md"):
        return None

    from .off_the_clock_schema import (
        OFF_THE_CLOCK_CATEGORIES,
        extract_category,
        lint_off_the_clock_page,
        split_frontmatter,
    )

    if tool_name == "Write":
        new_text = tool_input.get("content", "")
    elif tool_name == "Edit":
        path = Path(file_path)
        if not path.is_absolute():
            path = project_root / file_path
        if not path.exists():
            return None  # nothing on disk yet -- not this hook's concern
        current_text = path.read_text(encoding="utf-8")
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        if old_string not in current_text:
            return None  # Edit itself will fail on its own; not a lint matter
        count = -1 if tool_input.get("replace_all") else 1
        new_text = current_text.replace(old_string, new_string, count)
    else:
        return None

    try:
        frontmatter_text, body = split_frontmatter(new_text)
    except ValueError:
        return None  # not a frontmatter'd content file -- out of scope

    category = extract_category(frontmatter_text)
    if category not in OFF_THE_CLOCK_CATEGORIES:
        return None  # out of this lint's scope (Guides, recipes, etc.)

    report = lint_off_the_clock_page(body, category)
    if not report.passed:
        return (
            f"H009: this edit would leave '{file_path}' failing content-lint "
            f"({category}): {'; '.join(report.reasons)}. Fix the layout "
            "before writing -- see nookguard/off_the_clock_schema.py."
        )
    return None


def evaluate_pretooluse(tool_name: str, tool_input: dict[str, Any], project_root: Path) -> Optional[str]:
    """Single entry point the `.claude/hooks/pretooluse.py` wrapper calls.
    Returns a deny reason string, or None to allow. The FIRST violation
    found wins -- one decision per invocation, matching the reference
    example's shape (a hook either prints a decision or stays silent)."""
    if tool_name == "Bash":
        return check_bash(tool_input.get("command", ""))

    if tool_name in ("Write", "Edit"):
        reason = check_write_edit_protected_path(tool_input)
        if reason:
            return reason
        if tool_name == "Write":
            reason = check_write_to_published_media(tool_input, project_root)
            if reason:
                return reason
        reason = check_content_lint_on_edit(tool_name, tool_input, project_root)
        if reason:
            return reason

    return None
