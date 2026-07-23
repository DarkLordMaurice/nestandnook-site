"""Controlled Cloudflare release (Commit 21, requirements 6-8). Real,
buildable now: `check_cloudflare_credentials()` (a genuine, multi-scope
credential probe, same honesty discipline as `cli_reviewer.
check_claude_cli_auth()` and `adapters.huggingface._resolve_hf_token()`)
and `run_wrangler_deploy()` (a real, injectable subprocess wrapper around
`wrangler pages deploy`, parsing the REAL deployment ID and URL out of
wrangler's own output rather than fabricating one).

What this module does NOT do, and cannot do from this environment, honestly
documented rather than silently assumed away: it does not disable
Cloudflare Pages' automatic "deploy on push to main" GitHub integration
(requirement 7) -- that is a Cloudflare *dashboard* setting (Pages project
-> Settings -> Builds & deployments -> Automatic deployments), reachable
only via Maurice's own Cloudflare account, with no API token available in
this environment to do it programmatically either (see
docs/nookguard/BUILD-LOG.md's Commit 21 entry for the real, confirmed-
absent credential check). `cmd_deploy` (cli.py) refuses to run at all until
real credentials are present, specifically so this module can never be the
thing that silently starts double-deploying (NookGuard AND the still-
active GitHub auto-deploy) if that manual step hasn't happened yet."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

CLOUDFLARE_ENV_VARS = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")


def _persistent_env_value(key: str, subprocess_runner: Callable[..., Any]) -> Optional[str]:
    """Real, multi-scope (Process/User/Machine) Windows env-var check --
    same pattern this project's main CLAUDE.md documents for HF_TOKEN
    (a var can exist as a persistent User-level value while a fresh
    process, including this one, never inherits it). Checked here rather
    than trusted from `os.environ` alone, since a false "not set" would
    misdirect Maurice with instructions to set something that's already
    set but not reaching this process."""
    ps = (
        f"$v = [System.Environment]::GetEnvironmentVariable('{key}','User'); "
        f"if (-not $v) {{ $v = [System.Environment]::GetEnvironmentVariable('{key}','Machine') }}; "
        f"if ($v) {{ Write-Output $v }}"
    )
    try:
        result = subprocess_runner(["powershell.exe", "-Command", ps],
                                    capture_output=True, text=True, timeout=15)
    except Exception:  # noqa: BLE001 -- a probe failure is "unknown", not a crash
        return None
    value = (result.stdout or "").strip()
    return value or None


def check_cloudflare_credentials(
    *,
    env: Optional[dict[str, str]] = None,
    subprocess_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Returns {"available": bool, "missing": [...], "instructions": str}.
    Checks both the current process environment AND real persistent
    Windows User/Machine scopes for CLOUDFLARE_API_TOKEN and
    CLOUDFLARE_ACCOUNT_ID -- never raises, matching this codebase's
    'classify, don't crash' convention for missing-credential checks."""
    import os
    env = env if env is not None else os.environ

    missing = []
    for key in CLOUDFLARE_ENV_VARS:
        if env.get(key):
            continue
        if _persistent_env_value(key, subprocess_runner):
            continue
        missing.append(key)

    if missing:
        return {
            "available": False,
            "missing": missing,
            "instructions": (
                "Set " + " and ".join(missing) + " (a Cloudflare API token scoped to Pages:Edit "
                "for the nestandnook-site project, and the Cloudflare account ID) as persistent "
                "Windows User-level environment variables under the same identity the deploy "
                "command runs as, then re-run `mediactl deploy`. Create the token at "
                "https://dash.cloudflare.com/profile/api-tokens -- use a scoped Pages-only token, "
                "not the Global API Key, per this project's own restricted-credential requirement "
                "(Commit 21, requirement 6)."
            ),
        }
    return {"available": True, "missing": [], "instructions": ""}


class WranglerDeployError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"wrangler deploy failed ({reason})" + (f": {detail}" if detail else ""))



# Accepts BOTH real Cloudflare Pages URL shapes: a deployment-specific
# preview URL (two labels, e.g. https://<hash>.<project>.pages.dev) and the
# project's own production URL (one label, e.g. https://<project>.pages.dev)
# -- the original version of this regex required exactly two labels and
# would have silently failed to capture a real one-label production URL,
# caught by this module's own test_run_wrangler_deploy_missing_id_returns_
# none_not_guessed before it ever ran against real wrangler output.
_DEPLOYMENT_URL_RE = re.compile(r"https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.pages\.dev", re.IGNORECASE)
_DEPLOYMENT_ID_RE = re.compile(r"deployment[- ]?id[:\s]+([a-f0-9-]{8,})", re.IGNORECASE)


def run_wrangler_deploy(
    *,
    dist_dir: str,
    project_name: str,
    env_name: str = "production",
    subprocess_runner: Callable[..., Any] = subprocess.run,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    """Real `wrangler pages deploy` invocation (requirement 8: capture the
    REAL Cloudflare deployment ID and URL, never a fabricated one). Parses
    wrangler's own real stdout for its deployment URL and, if present, a
    deployment ID -- if wrangler's output format doesn't contain a
    recognizable ID, `deployment_id` comes back as None rather than a
    guess; a caller must not treat that as a failure, only as "not
    captured."

    Real bug found and fixed 2026-07-22 (Commit 23, once real Cloudflare
    credentials made an actual end-to-end run possible for the first time):
    `npm install -g wrangler` on Windows installs `wrangler.cmd`/
    `wrangler.ps1` wrapper scripts, not a bare `wrangler.exe`. Python's
    subprocess.run(["wrangler", ...], shell=False) does NOT do PATHEXT
    resolution the way a real shell (PowerShell/cmd.exe) does, so a literal
    "wrangler" argument raised FileNotFoundError even with wrangler
    correctly installed and confirmed working via `wrangler pages project
    list` run directly in PowerShell. Fixed via shutil.which("wrangler"),
    which DOES do PATHEXT-aware resolution on Windows (and is a correct
    no-op passthrough on POSIX). Only applied when subprocess_runner is the
    real subprocess.run -- injected fake runners in tests still receive the
    literal "wrangler" token, since its exact identity has no bearing on a
    test double."""
    wrangler_exe = "wrangler"
    if subprocess_runner is subprocess.run:
        wrangler_exe = shutil.which("wrangler") or "wrangler"
    args = [wrangler_exe, "pages", "deploy", dist_dir, "--project-name", project_name,
            "--branch", "main" if env_name == "production" else env_name]
    try:
        # encoding="utf-8", errors="replace": real finding from this same
        # Commit 23 test run -- wrangler emits UTF-8/emoji output (e.g. the
        # "⛅️ wrangler" banner) that a background subprocess reader thread
        # tried to decode with Windows' default cp1252 console codec and
        # crashed on (PytestUnhandledThreadExceptionWarning, non-fatal to
        # the run itself but a real latent reliability issue). Forcing
        # utf-8 with a replace fallback avoids depending on this machine's
        # console locale to correctly read wrangler's own real output.
        result = subprocess_runner(args, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace",
                                    timeout=timeout_seconds)
    except FileNotFoundError as e:
        raise WranglerDeployError("wrangler_not_found", str(e)) from e
    except subprocess.TimeoutExpired as e:
        raise WranglerDeployError("timeout", f"wrangler did not return within {timeout_seconds}s") from e

    if result.returncode != 0:
        raise WranglerDeployError("nonzero_exit",
                                   f"exit code {result.returncode}; stdout={result.stdout!r} "
                                   f"stderr={result.stderr!r}")

    url_match = _DEPLOYMENT_URL_RE.search(result.stdout)
    id_match = _DEPLOYMENT_ID_RE.search(result.stdout)
    return {
        "ok": True,
        "deployment_url": url_match.group(0) if url_match else None,
        "deployment_id": id_match.group(1) if id_match else None,
        "raw_stdout": result.stdout,
    }
