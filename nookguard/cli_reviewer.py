r"""ClaudeCodeCliReviewer -- Commit 19. Replaces the direct Anthropic
Messages API transport (`agent_runner._default_executor`) as the DEFAULT
transport for observer/judge/preview-reviewer sessions, using fresh,
non-interactive `claude -p` (Claude Code CLI) processes instead of a raw
Messages API call.

Why this is now the default, not the direct-API adapter (kept, opt-in
only -- see agent_runner.py's `executor=` parameter):

- Uses the operator's own authenticated Claude subscription (OAuth via
  `claude setup-token`, or `CLAUDE_CODE_OAUTH_TOKEN`) instead of requiring
  a separate `ANTHROPIC_API_KEY`, which this environment has never had --
  see docs/nookguard/BUILD-LOG.md's Commit 18 entry, the real live-canary
  finding that started this commit.
- `--no-session-persistence` plus a freshly generated `--session-id` per
  call is a REAL, CLI-enforced "never resumable" guarantee -- there is no
  session file on disk a future call could even accidentally continue,
  stronger than "just don't pass --continue."
- `--tools` (an explicit allowlist; empty string disables ALL tools) plus
  no `--mcp-config` gives each role a real, process-enforced capability
  restriction, not just a documented convention a prompt is trusted to
  follow.

Real, confirmed facts this module is built against (checked directly on
this machine 2026-07-23, not assumed from memory):
- The bundled Claude Code CLI is real and present at
  `%APPDATA%\Claude\claude-code\{version}\claude.exe` -- NOT on PATH by
  default in a fresh shell (same "exists but isn't inherited" pattern as
  HF_TOKEN, documented in the main project CLAUDE.md).
- `claude auth status` on this machine returns
  `{"loggedIn": false, "authMethod": "none", ...}` -- genuinely
  unauthenticated, not a guess.
- A real `claude -p ... --output-format json` call against that
  unauthenticated state returns EXIT CODE 1 and a real, well-formed JSON
  envelope on stdout:
  `{"type":"result","subtype":"success","is_error":true,
    "result":"Not logged in · Please run /login", ...}`
  -- i.e. even an auth failure is still valid JSON with `is_error: true`
  and a human-readable `result` string, not a crash or empty stdout. This
  module's auth-failure detection is built on that real, observed shape,
  not a guess about what an error might look like.
- `--tools ''` (an empty string) as a literal PowerShell single-quoted
  argument was rejected as "argument missing" by the CLI's own arg
  parser in one manual test -- but that is a PowerShell quoting artifact,
  not a Python subprocess one (`subprocess.run([..., "--tools", "", ...])`
  passes a real empty-string argv element with no shell involved). Still
  flagged here in case it resurfaces: if it does, the fix is to omit
  `--tools` entirely for the "no tools" case rather than pass an empty
  string.

What is explicitly NOT verified, because every real call in this
environment fails at the auth step before reaching it: whether an image
file handed to the CLI via `--add-dir` + a Read-tool instruction is
actually fed to the model's real vision input, or whether (as
agent_runner.py's own Commit 7 docstring warned) the Read tool treats a
local image file as text. This module is built on the more-likely-correct
design for a current Claude Code version, but this is a real, open
question that MUST be confirmed empirically the first time real
credentials exist -- see docs/nookguard/BUILD-LOG.md's Commit 19 entry.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from .exceptions import NookGuardError

# Real, observed markers from the actual unauthenticated response on this
# machine (2026-07-23) -- see module docstring. Matched case-insensitively
# against the envelope's own `result` text.
_AUTH_FAILURE_MARKERS = (
    "not logged in",
    "please run /login",
    "please run `claude setup-token`",
    "please run claude setup-token",
)

DEFAULT_TIMEOUT_SECONDS = 120.0
MODEL = "claude-opus-4-8"


class ClaudeCliError(NookGuardError):
    """Raised for every real failure mode this transport can hit. `reason`
    is always one of a fixed, checkable set of category strings (never a
    free-form guess) so a caller (or a test) can branch on it reliably:
    'cli_not_found', 'spawn_failed', 'timeout', 'nonzero_exit',
    'malformed_json', 'auth_unavailable', 'cli_reported_error'."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"Claude Code CLI transport failed ({reason})" + (f": {detail}" if detail else ""))


def resolve_claude_cli_path(explicit: Optional[str] = None) -> Optional[str]:
    """Resolution order: an explicit override (tests / callers), the
    `NOOKGUARD_CLAUDE_CLI_PATH` env var, a real PATH lookup, then the
    real, confirmed bundled-desktop-app install location. Returns None
    (never raises) if nothing is found -- the caller decides how to
    report that, matching the rest of this codebase's "classify, don't
    crash" convention (see adapters/huggingface.py's `_resolve_hf_token`,
    the same pattern applied to a different missing-credential problem)."""
    if explicit:
        return explicit
    env_override = os.environ.get("NOOKGUARD_CLAUDE_CLI_PATH")
    if env_override:
        return env_override
    on_path = shutil.which("claude")
    if on_path:
        return on_path

    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    base = Path(appdata) / "Claude" / "claude-code"
    if not base.is_dir():
        return None
    candidates = sorted(
        (d for d in base.iterdir() if d.is_dir() and (d / "claude.exe").exists()),
        key=lambda d: d.name,
        reverse=True,
    )
    return str(candidates[0] / "claude.exe") if candidates else None


def _try_parse_envelope(stdout: str) -> Optional[dict[str, Any]]:
    try:
        parsed = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _looks_like_auth_failure(envelope: dict[str, Any]) -> bool:
    result_text = str(envelope.get("result", "")).lower()
    return any(marker in result_text for marker in _AUTH_FAILURE_MARKERS)


def run_claude_cli(
    *,
    system_prompt: str,
    prompt_text: str,
    tools: str = "",
    extra_args: Optional[list[str]] = None,
    claude_path: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    subprocess_runner: Callable[..., Any] = subprocess.run,
    session_id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> str:
    """The one real subprocess call site. Every argument that affects
    testability is injectable (subprocess_runner, session_id_factory,
    claude_path) -- same dependency-injection convention as
    adapters/huggingface.py's `client_factory` and agent_runner.py's
    `executor`, so this can be fully unit-tested without a real CLI or
    real credentials.

    Isolation contract enforced here, not just documented:
    - `--session-id` is freshly generated every call, never reused.
    - `--no-session-persistence` -- nothing is saved to disk to resume.
    - `--tools` is an explicit allowlist (empty string = no tools at all).
    - No `--mcp-config` is ever passed -- no MCP servers are reachable.
    - `--system-prompt` (full replace, not `--append-system-prompt`) --
      the role's instructions are the ENTIRE system prompt, never diluted
      by Claude Code's own default assistant framing.
    - `--dangerously-skip-permissions` is required for non-interactive
      unattended execution (no TTY exists to answer a permission prompt,
      which would otherwise hang forever) -- this is why the `--tools`
      allowlist is the real capability boundary here, not an interactive
      confirmation step.
    """
    resolved_path = resolve_claude_cli_path(claude_path)
    if not resolved_path:
        raise ClaudeCliError(
            "cli_not_found",
            "no Claude Code CLI executable could be located (checked "
            "NOOKGUARD_CLAUDE_CLI_PATH, PATH, and the bundled desktop app install directory)",
        )

    args = [
        resolved_path, "-p", prompt_text,
        "--output-format", "json",
        "--no-session-persistence",
        "--session-id", session_id_factory(),
        "--system-prompt", system_prompt,
        "--model", MODEL,
        "--dangerously-skip-permissions",
    ]
    # Per `claude --help`: '--tools <tools...> ... Use "" to disable all
    # tools'. Always pass --tools explicitly (never omit it) so "no tools"
    # is a real, enforced argument, not an assumed default -- confirmed
    # live 2026-07-23 that omitting/mis-passing this can itself produce a
    # CLI argument-parsing error rather than a clean "no tools" state.
    args.extend(["--tools", tools])
    if extra_args:
        args.extend(extra_args)

    try:
        result = subprocess_runner(
            args, capture_output=True, text=True, timeout=timeout_seconds, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeCliError("timeout", f"claude -p did not return within {timeout_seconds}s") from e
    except OSError as e:
        raise ClaudeCliError("spawn_failed", str(e)) from e

    envelope = _try_parse_envelope(result.stdout)

    if result.returncode != 0:
        if envelope is not None and _looks_like_auth_failure(envelope):
            raise ClaudeCliError("auth_unavailable", envelope.get("result", ""))
        raise ClaudeCliError(
            "nonzero_exit",
            f"exit code {result.returncode}; stdout={result.stdout!r} stderr={result.stderr!r}",
        )

    if envelope is None:
        raise ClaudeCliError("malformed_json", f"stdout was not a valid JSON result envelope: {result.stdout!r}")

    if envelope.get("is_error"):
        if _looks_like_auth_failure(envelope):
            raise ClaudeCliError("auth_unavailable", envelope.get("result", ""))
        raise ClaudeCliError("cli_reported_error", str(envelope.get("result", "")))

    return str(envelope.get("result", ""))


def claude_cli_executor(system_prompt: str, user_content: list[dict[str, Any]]) -> str:
    """The new DEFAULT `SessionExecutor` (agent_runner.py's type alias) --
    matches that exact `(system_prompt, user_content) -> str` contract so
    run_observer_session/run_judge_session/run_page_review_session need
    NO signature change, only their default `executor=` value changes
    (see agent_runner.py). The old direct-API transport
    (`agent_runner._default_executor`) remains fully available -- pass
    `executor=agent_runner._default_executor` explicitly to opt back in.

    An image content block (base64-encoded, the exact shape
    agent_runner._image_to_content_block already produces) is decoded
    back to real bytes and written to a real temp file, since the CLI
    takes a file path via its Read tool, not inline base64 -- there is no
    supported way to attach image bytes directly to a `-p` call. The judge
    role never receives an image at all (agent_runner.py's own contract),
    so this path is simply skipped for judge calls -- `tools` stays empty
    and no `--add-dir` is added, exactly matching "the judge session never
    sees the image."""
    image_blocks = [b for b in user_content if b.get("type") == "image"]
    text_blocks = [b for b in user_content if b.get("type") == "text"]
    instruction = "\n\n".join(
        b["text"] for b in text_blocks if isinstance(b.get("text"), str)
    )

    tmp_dir: Optional[str] = None
    prompt_text = instruction
    tools = ""
    extra_args: list[str] = []
    try:
        if image_blocks:
            source = image_blocks[0]["source"]
            image_bytes = base64.b64decode(source["data"])
            ext = ".jpg" if source.get("media_type") == "image/jpeg" else ".png"
            tmp_dir = tempfile.mkdtemp(prefix="nookguard-cli-review-")
            image_path = str(Path(tmp_dir) / f"review{ext}")
            Path(image_path).write_bytes(image_bytes)
            prompt_text = (
                f"Use the Read tool to open and view the image at exactly this path: "
                f"{image_path}\n\n{instruction}"
            )
            tools = "Read"
            extra_args = ["--add-dir", tmp_dir]

        return run_claude_cli(
            system_prompt=system_prompt,
            prompt_text=prompt_text,
            tools=tools,
            extra_args=extra_args,
        )
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def check_claude_cli_auth(
    *,
    claude_path: Optional[str] = None,
    timeout_seconds: float = 30.0,
    subprocess_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """`mediactl auth-check`'s real logic (Commit 19, requirement 7): a
    genuine, minimal, real `-p` smoke-test call with no tools at all --
    proves the CLI is installed AND authenticated for real, not just that
    a config file claims to be. Returns a plain dict (never raises) so the
    CLI command layer can turn it directly into the standard
    `{"ok": ..., ...}` contract; every field here is real, not narrated:
    `authenticated`, `reason` (only present when not authenticated, one of
    ClaudeCliError's own reason categories), `claude_cli_path`,
    `instructions` (only present on failure -- exactly what Maurice needs
    to run, per requirement 5's 'stop and instruct Maurice')."""
    resolved_path = resolve_claude_cli_path(claude_path)
    if not resolved_path:
        return {
            "authenticated": False,
            "reason": "cli_not_found",
            "claude_cli_path": None,
            "instructions": (
                "No Claude Code CLI executable was found (checked NOOKGUARD_CLAUDE_CLI_PATH, "
                "PATH, and the bundled desktop app install directory). Install Claude Code, "
                "then run `claude setup-token` to set up a long-lived authentication token, "
                "or set the CLAUDE_CODE_OAUTH_TOKEN environment variable."
            ),
        }

    try:
        result_text = run_claude_cli(
            system_prompt="Reply with exactly the text: OK",
            prompt_text="Reply with exactly the text: OK",
            tools="",
            claude_path=resolved_path,
            timeout_seconds=timeout_seconds,
            subprocess_runner=subprocess_runner,
        )
    except ClaudeCliError as e:
        instructions = (
            "Run `claude setup-token` under the same Windows identity the scheduled task runs "
            "as (this sets up a long-lived authentication token for a Claude subscription), or "
            "set the CLAUDE_CODE_OAUTH_TOKEN environment variable for that identity. Then re-run "
            "`mediactl auth-check`."
            if e.reason == "auth_unavailable"
            else f"Claude Code CLI transport error ({e.reason}): {e.detail}"
        )
        return {
            "authenticated": False,
            "reason": e.reason,
            "claude_cli_path": resolved_path,
            "instructions": instructions,
        }

    return {
        "authenticated": True,
        "claude_cli_path": resolved_path,
        "smoke_test_result": result_text,
    }
