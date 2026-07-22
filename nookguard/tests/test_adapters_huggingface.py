"""No real network/HF calls — every test injects a fake client via the
`client`/`client_factory` params generate() exposes for exactly this reason."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from nookguard.adapters.huggingface import (
    AdapterGenerationBlockedError,
    _classify_error,
    _resolve_hf_token,
    generate,
)


def _fake_image_path() -> str:
    p = Path(tempfile.mkdtemp()) / "fake.png"
    Image.new("RGB", (16, 16), color=(200, 100, 50)).save(p)
    return str(p)


class _FakeClientAlwaysSucceeds:
    def __init__(self):
        self.calls = 0

    def predict(self, **kwargs):
        self.calls += 1
        return [[{"image": {"path": _fake_image_path()}}]]


class _FakeClientFailsNTimes:
    def __init__(self, fail_count: int, error_message: str = "boom"):
        self.fail_count = fail_count
        self.error_message = error_message
        self.calls = 0

    def predict(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_count:
            raise RuntimeError(self.error_message)
        return [[{"image": {"path": _fake_image_path()}}]]


class _FakeClientAlwaysFails:
    def __init__(self, error_message: str = "boom"):
        self.error_message = error_message
        self.calls = 0

    def predict(self, **kwargs):
        self.calls += 1
        raise RuntimeError(self.error_message)


def test_generate_returns_valid_jpeg_bytes_on_first_success():
    client = _FakeClientAlwaysSucceeds()
    image_bytes = generate("a test prompt", client=client, sleep_fn=lambda s: None)
    assert image_bytes[:2] == b"\xff\xd8"  # JPEG magic bytes
    assert client.calls == 1


def test_generate_retries_and_succeeds_within_bound():
    client = _FakeClientFailsNTimes(fail_count=2)
    sleeps: list[float] = []
    image_bytes = generate("prompt", client=client, max_retries=3,
                            backoff_seconds=(0.0, 0.0, 0.0), sleep_fn=sleeps.append)
    assert image_bytes[:2] == b"\xff\xd8"
    assert client.calls == 3
    assert len(sleeps) == 2  # slept between attempts 1->2 and 2->3, not after final success


def test_generate_raises_after_exhausting_retries():
    client = _FakeClientAlwaysFails(error_message="persistent failure")
    with pytest.raises(AdapterGenerationBlockedError) as exc_info:
        generate("prompt", client=client, token="real-token", max_retries=2,
                  backoff_seconds=(0.0,), sleep_fn=lambda s: None)
    assert client.calls == 2
    assert exc_info.value.attempts == 2


def test_generate_never_sleeps_more_than_backoff_table_length():
    """Bounded backoff — never an infinite/unbounded retry loop."""
    client = _FakeClientAlwaysFails()
    sleeps: list[float] = []
    with pytest.raises(AdapterGenerationBlockedError):
        generate("prompt", client=client, token="x", max_retries=5,
                  backoff_seconds=(0.0, 0.0), sleep_fn=sleeps.append)
    assert len(sleeps) == 4  # slept between each of 5 attempts except the last


def test_classify_error_reports_no_token_when_unauthenticated():
    result = _classify_error(RuntimeError("some error"), had_token=False)
    assert result.reason.startswith("no_token")


def test_classify_error_reports_rate_limited_only_when_authenticated_and_signaled():
    result = _classify_error(RuntimeError("ZeroGPU quota exceeded"), had_token=True)
    assert result.reason.startswith("rate_limited")


def test_classify_error_does_not_claim_rate_limited_without_token():
    """The core regression test for the real 2026-07-11 incident: a missing
    token must never be reported as 'quota exceeded', even if the error text
    happens to mention quota-like language (anonymous-tier errors can look
    similar) — no_token always takes priority."""
    result = _classify_error(RuntimeError("quota exceeded"), had_token=False)
    assert result.reason.startswith("no_token")
    assert "quota" not in result.reason.split("—")[0]


def test_classify_error_reports_unknown_for_non_quota_authenticated_failure():
    result = _classify_error(RuntimeError("connection reset"), had_token=True)
    assert result.reason.startswith("unknown_error")


def test_resolve_hf_token_prefers_explicit_argument():
    assert _resolve_hf_token(explicit="explicit-token") == "explicit-token"


def test_resolve_hf_token_falls_back_to_environ(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "env-token")
    assert _resolve_hf_token() == "env-token"


def test_generate_uses_client_factory_when_no_client_given():
    """Confirms the injection seam works both ways — passing a factory
    instead of a ready client is also supported, for callers that need to
    construct the client lazily with a resolved token."""
    built = {}

    def factory(token):
        built["token"] = token
        return _FakeClientAlwaysSucceeds()

    generate("prompt", token="fixed-token", client_factory=factory, sleep_fn=lambda s: None)
    assert built["token"] == "fixed-token"
