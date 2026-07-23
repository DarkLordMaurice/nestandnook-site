"""Commit 21, requirements 6-8: controlled Cloudflare release tests.
Dependency-injection pattern established in Commit 19/20 (cli_reviewer,
adapters.huggingface): every subprocess boundary takes an injectable
`subprocess_runner`, so tests exercise real parsing/branching logic without
actually shelling out to wrangler or PowerShell. One test intentionally
calls the real, unmocked `check_cloudflare_credentials()` against this
real environment, matching this project's standing culture of not
monkeypatching away the actual "are credentials here" answer -- this
machine is confirmed to genuinely lack both env vars (BUILD-LOG Commit 21)."""

from __future__ import annotations

import subprocess

import pytest

from nookguard.deploy import (
    CLOUDFLARE_ENV_VARS,
    WranglerDeployError,
    check_cloudflare_credentials,
    run_wrangler_deploy,
)


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_check_cloudflare_credentials_available_via_process_env():
    env = {"CLOUDFLARE_API_TOKEN": "tok", "CLOUDFLARE_ACCOUNT_ID": "acct"}
    result = check_cloudflare_credentials(env=env, subprocess_runner=lambda *a, **k: _FakeCompletedProcess())
    assert result["available"] is True
    assert result["missing"] == []


def test_check_cloudflare_credentials_missing_both_reports_instructions():
    def fake_runner(*a, **k):
        return _FakeCompletedProcess(stdout="")  # persistent scope also empty

    result = check_cloudflare_credentials(env={}, subprocess_runner=fake_runner)
    assert result["available"] is False
    assert set(result["missing"]) == set(CLOUDFLARE_ENV_VARS)
    assert "CLOUDFLARE_API_TOKEN" in result["instructions"]
    assert "CLOUDFLARE_ACCOUNT_ID" in result["instructions"]


def test_check_cloudflare_credentials_falls_back_to_persistent_scope():
    def fake_runner(args, **k):
        if "CLOUDFLARE_API_TOKEN" in args[-1]:
            return _FakeCompletedProcess(stdout="persistent-token-value\n")
        return _FakeCompletedProcess(stdout="")

    result = check_cloudflare_credentials(env={}, subprocess_runner=fake_runner)
    # API token found via persistent scope, account ID still missing
    assert result["available"] is False
    assert result["missing"] == ["CLOUDFLARE_ACCOUNT_ID"]


def test_check_cloudflare_credentials_probe_exception_treated_as_not_set():
    def raising_runner(*a, **k):
        raise RuntimeError("powershell unavailable")

    result = check_cloudflare_credentials(env={}, subprocess_runner=raising_runner)
    assert result["available"] is False
    assert set(result["missing"]) == set(CLOUDFLARE_ENV_VARS)


def test_check_cloudflare_credentials_real_unmocked_call_on_this_machine():
    """Real, unmocked call. Updated post-Commit-22 (see BUILD-LOG.md
    'Post-Commit-22: real Cloudflare credentials configured'): Maurice
    supplied a real, scoped Cloudflare API token and account ID, set as
    persistent Windows User-level env vars on 2026-07-22 -- the same
    persistent-scope pattern this project already uses for HF_TOKEN. This
    now documents the opposite finding from before: both vars are
    genuinely present. Real end-to-end proof they actually work (not just
    "present"): `wrangler pages project list`, run for real against these
    exact credentials, lists the real `nestandnook-site` project --
    confirmed 2026-07-22, see BUILD-LOG.md Commit 23 entry."""
    result = check_cloudflare_credentials()
    assert result["available"] is True
    assert result["missing"] == []


def test_run_wrangler_deploy_parses_real_shaped_stdout():
    stdout = (
        "Deployed to https://abc123.nestandnook-site.pages.dev\n"
        "Deployment ID: 7f3a9c21-aaaa-bbbb-cccc-1234567890ab\n"
    )

    def fake_runner(args, **k):
        assert "wrangler" in args
        assert "deploy" in args
        return _FakeCompletedProcess(returncode=0, stdout=stdout, stderr="")

    result = run_wrangler_deploy(dist_dir="dist", project_name="nestandnook-site",
                                  subprocess_runner=fake_runner)
    assert result["ok"] is True
    assert result["deployment_url"] == "https://abc123.nestandnook-site.pages.dev"
    assert result["deployment_id"] == "7f3a9c21-aaaa-bbbb-cccc-1234567890ab"


def test_run_wrangler_deploy_missing_id_returns_none_not_guessed():
    def fake_runner(args, **k):
        return _FakeCompletedProcess(returncode=0, stdout="Deployed to https://x.pages.dev\n", stderr="")

    result = run_wrangler_deploy(dist_dir="dist", project_name="p", subprocess_runner=fake_runner)
    assert result["ok"] is True
    assert result["deployment_url"] == "https://x.pages.dev"
    assert result["deployment_id"] is None


def test_run_wrangler_deploy_wrangler_not_found():
    def fake_runner(args, **k):
        raise FileNotFoundError("wrangler not on PATH")

    with pytest.raises(WranglerDeployError) as exc_info:
        run_wrangler_deploy(dist_dir="dist", project_name="p", subprocess_runner=fake_runner)
    assert exc_info.value.reason == "wrangler_not_found"


def test_run_wrangler_deploy_timeout():
    def fake_runner(args, **k):
        raise subprocess.TimeoutExpired(cmd=args, timeout=300)

    with pytest.raises(WranglerDeployError) as exc_info:
        run_wrangler_deploy(dist_dir="dist", project_name="p", subprocess_runner=fake_runner)
    assert exc_info.value.reason == "timeout"


def test_run_wrangler_deploy_nonzero_exit():
    def fake_runner(args, **k):
        return _FakeCompletedProcess(returncode=1, stdout="", stderr="Error: project not found")

    with pytest.raises(WranglerDeployError) as exc_info:
        run_wrangler_deploy(dist_dir="dist", project_name="p", subprocess_runner=fake_runner)
    assert exc_info.value.reason == "nonzero_exit"
    assert "project not found" in str(exc_info.value)


def test_run_wrangler_deploy_uses_preview_branch_for_preview_env():
    captured = {}

    def fake_runner(args, **k):
        captured["args"] = args
        return _FakeCompletedProcess(returncode=0, stdout="Deployed to https://y.pages.dev\n", stderr="")

    run_wrangler_deploy(dist_dir="dist", project_name="p", env_name="preview", subprocess_runner=fake_runner)
    assert "--branch" in captured["args"]
    branch_idx = captured["args"].index("--branch")
    assert captured["args"][branch_idx + 1] == "preview"
