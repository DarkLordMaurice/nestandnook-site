#!/usr/bin/env python
"""Claude Code PreToolUse hook wrapper (Commit 11). Deliberately thin: all
real policy logic lives in nookguard/hooks.py (unit-tested there, see
nookguard/tests/test_hooks.py); this script only implements the stdin /
stdout / exit-code contract Claude Code expects from a command hook, per
the real Claude Code hooks reference (code.claude.com/docs/en/hooks),
verified before writing this rather than guessed:

  - JSON with `tool_name` and `tool_input` arrives on stdin.
  - Exit 0 with no stdout means "no decision, proceed as normal."
  - Exit 0 with a `{"hookSpecificOutput": {...permissionDecision: "deny"...}}`
    JSON object on stdout blocks the tool call and shows the reason to Claude.

Registered in .claude/settings.json for the Bash|Write|Edit matcher group."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# .claude/hooks/pretooluse.py -> .claude -> site (this project's real root,
# where the nookguard package lives).
_SITE_ROOT = Path(__file__).resolve().parents[2]

try:
    from nookguard.hooks import evaluate_pretooluse
except ImportError:
    # nookguard may not be pip-installed in whatever environment spawned
    # this hook process -- fall back to importing it directly off disk
    # rather than assuming an editable install is always active.
    sys.path.insert(0, str(_SITE_ROOT))
    from nookguard.hooks import evaluate_pretooluse


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Malformed input from the caller -- fail open (no decision) rather
        # than block on something this script can't even parse. Matches the
        # docs' own "if the command can't be parsed, don't block" guidance
        # for the analogous `if`-filter case.
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    project_root = Path(payload.get("cwd") or _SITE_ROOT)

    reason = evaluate_pretooluse(tool_name, tool_input, project_root)
    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
