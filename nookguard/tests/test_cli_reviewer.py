"""Commit 19: ClaudeCodeCliReviewer transport tests. Every test injects a
fake `subprocess_runner` (and, where needed, `claude_path`) -- no real CLI
or credential is ever required to run this suite, matching the same
dependency-injection convention used for adapters/huggingface.py's
`client_factory` and agent_runner.py's `executor`."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any

import pytest

from nookguard.cli_reviewer import (
    ClaudeCliError,
    check_claude_cli_auth,
    resolve_claude_cli_path,
    run_claude_cli,
)


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def _ok_envelope(result: str = "OK") -> str:
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "result": result, "session_id": "fake-session", "uuid": "fake-uuid",
    })


def _auth_failure_envelope() -> str:
    # The real, observed shape from this machine (see cli_reviewer.py's
    # module docstring) -- exit code 1, is_error true, a human-readable
    # 'Not logged in' result string.
    return json.dumps({
        "type": "result", "subtype": "success", "is_error": True,
        "result": "Not logged in · Please run /login",
        "session_id": "fake-session", "uuid": "fake-uuid",
    })


@dataclass
class _Runner:
    """A callable object (not just a function) so tests can inspect what
    args it was actually invoked with after the call."""
    result: FakeCompletedProcess
    raise_exc: Exception | None = None
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, args: list[str], **kwargs: Any) -> FakeCompletedProcess:
        self.calls.append(args)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.result


def test_successful_cli_review_returns_result_text():
    runner = _Runner(FakeCompletedProcess(returncode=0, stdout=_ok_envelope("hello from claude")))
    text = run_claude_cli(
        system_prompt="be helpful", prompt_text="say hi", tools="",
        claude_path="C:/fake/claude.exe", subprocess_runner=runner,
        session_id_factory=lambda: "fixed-session-id",
    )
    assert text == "hello from claude"
    # Isolation contract: fresh session id, no-session-persistence, explicit
    # --tools even for the empty-tools case.
    args = runner.calls[0]
    assert "--no-session-persistence" in args
    assert "--session-id" in args and args[args.index("--session-id") + 1] == "fixed-session-id"
    assert "--tools" in args and args[args.index("--tools") + 1] == ""
    assert "--system-prompt" in args and args[args.index("--system-prompt") + 1] == "be helpful"


def test_missing_authentication_raises_auth_unavailable():
    runner = _Runner(FakeCompletedProcess(returncode=1, stdout=_auth_failure_envelope()))
    with pytest.raises(ClaudeCliError) as exc_info:
        run_claude_cli(system_prompt="x", prompt_text="y", tools="",
                        claude_path="C:/fake/claude.exe", subprocess_runner=runner)
    assert exc_info.value.reason == "auth_unavailable"
    assert "not logged in" in exc_info.value.detail.lower()


def test_malformed_json_raises_malformed_json():
    runner = _Runner(FakeCompletedProcess(returncode=0, stdout="this is not json at all"))
    with pytest.raises(ClaudeCliError) as exc_info:
        run_claude_cli(system_prompt="x", prompt_text="y", tools="",
                        claude_path="C:/fake/claude.exe", subprocess_runner=runner)
    assert exc_info.value.reason == "malformed_json"


def test_timeout_raises_timeout():
    runner = _Runner(FakeCompletedProcess(), raise_exc=subprocess.TimeoutExpired(cmd=["claude"], timeout=5))
    with pytest.raises(ClaudeCliError) as exc_info:
        run_claude_cli(system_prompt="x", prompt_text="y", tools="",
                        claude_path="C:/fake/claude.exe", subprocess_runner=runner, timeout_seconds=5)
    assert exc_info.value.reason == "timeout"


def test_nonzero_exit_without_auth_marker_raises_nonzero_exit():
    runner = _Runner(FakeCompletedProcess(returncode=1, stdout=_ok_envelope("some other real error"),
                                           stderr="boom"))
    with pytest.raises(ClaudeCliError) as exc_info:
        run_claude_cli(system_prompt="x", prompt_text="y", tools="",
                        claude_path="C:/fake/claude.exe", subprocess_runner=runner)
    assert exc_info.value.reason == "nonzero_exit"


def test_cli_reported_error_without_auth_marker():
    envelope = json.dumps({"type": "result", "subtype": "success", "is_error": True,
                            "result": "some unrelated failure", "session_id": "s", "uuid": "u"})
    runner = _Runner(FakeCompletedProcess(returncode=0, stdout=envelope))
    with pytest.raises(ClaudeCliError) as exc_info:
        run_claude_cli(system_prompt="x", prompt_text="y", tools="",
                        claude_path="C:/fake/claude.exe", subprocess_runner=runner)
    assert exc_info.value.reason == "cli_reported_error"


def test_cli_not_found_when_no_path_resolves(monkeypatch):
    monkeypatch.delenv("NOOKGUARD_CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.delenv("APPDATA", raising=False)
    with pytest.raises(ClaudeCliError) as exc_info:
        run_claude_cli(system_prompt="x", prompt_text="y", tools="",
                        subprocess_runner=_Runner(FakeCompletedProcess()))
    assert exc_info.value.reason == "cli_not_found"


def test_resolve_claude_cli_path_prefers_explicit_override():
    assert resolve_claude_cli_path("C:/explicit/claude.exe") == "C:/explicit/claude.exe"


def test_spawn_failed_raises_on_os_error():
    runner = _Runner(FakeCompletedProcess(), raise_exc=OSError("no such file"))
    with pytest.raises(ClaudeCliError) as exc_info:
        run_claude_cli(system_prompt="x", prompt_text="y", tools="",
                        claude_path="C:/fake/claude.exe", subprocess_runner=runner)
    assert exc_info.value.reason == "spawn_failed"


# ---- check_claude_cli_auth -------------------------------------------------

def test_check_claude_cli_auth_success():
    runner = _Runner(FakeCompletedProcess(returncode=0, stdout=_ok_envelope("OK")))
    result = check_claude_cli_auth(claude_path="C:/fake/claude.exe", subprocess_runner=runner)
    assert result == {"authenticated": True, "claude_cli_path": "C:/fake/claude.exe",
                       "smoke_test_result": "OK"}


def test_check_claude_cli_auth_reports_instructions_on_auth_failure():
    runner = _Runner(FakeCompletedProcess(returncode=1, stdout=_auth_failure_envelope()))
    result = check_claude_cli_auth(claude_path="C:/fake/claude.exe", subprocess_runner=runner)
    assert result["authenticated"] is False
    assert result["reason"] == "auth_unavailable"
    assert "claude setup-token" in result["instructions"]
    assert "CLAUDE_CODE_OAUTH_TOKEN" in result["instructions"]


def test_check_claude_cli_auth_cli_not_found(monkeypatch):
    monkeypatch.delenv("NOOKGUARD_CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.delenv("APPDATA", raising=False)
    result = check_claude_cli_auth(subprocess_runner=_Runner(FakeCompletedProcess()))
    assert result["authenticated"] is False
    assert result["reason"] == "cli_not_found"
    assert result["claude_cli_path"] is None
