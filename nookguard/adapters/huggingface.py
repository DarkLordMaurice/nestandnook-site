"""Real Hugging Face Z-Image-Turbo adapter (Commit 5). Mirrors the exact,
already-working call pattern from the main project's production scripts
(e.g. scripts/gen_offtheclock_backlog_images.py) rather than inventing a new
one: same model (Tongyi-MAI/Z-Image-Turbo), same gradio_client.predict()
kwargs, same gallery-item parsing. This adapter does not decide identity-lock
policy (Winnie's face is ChatGPT-only, per the main project's standing rule)
-- it only wraps the free/cheap non-Winnie generation path.

Section 27 rules this file exists to satisfy:
- bounded retry with backoff, never an infinite loop
- exhausted retries raise AdapterGenerationBlockedError, and the error
  reason is never asserted as "quota exceeded" unless a real, authenticated
  API response actually said so -- an unauthenticated call hitting the
  anonymous tier's limit is a DIFFERENT failure and must be reported as one
  (this is the exact documented 2026-07-11 incident from the main project
  CLAUDE.md's "HARD RULE -- HF_TOKEN location" section: a missing token was
  once misreported to Maurice as "quota exhausted").
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..exceptions import NookGuardError

ADAPTER_VERSION = "hf-zimage-turbo-0.1.0"
MODEL_ID = "Tongyi-MAI/Z-Image-Turbo"

DEFAULT_RESOLUTION = "1024x1024 ( 1:1 )"
DEFAULT_STEPS = 8
DEFAULT_SHIFT = 3.0
DEFAULT_BACKOFF_SECONDS = (1.0, 2.0, 4.0)  # bounded — 3 retries, never unbounded

_QUOTA_SIGNAL_SUBSTRINGS = ("quota", "gpu duration", "zerogpu", "usage limit")


class AdapterGenerationBlockedError(NookGuardError):
    """Retries exhausted. `reason` is a classified, evidence-based category —
    never a guess dressed up as certainty."""

    def __init__(self, reason: str, attempts: int, last_error: str):
        self.reason = reason
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Generation blocked after {attempts} attempt(s): {reason} "
            f"(last error: {last_error})"
        )


@dataclass
class _ErrorClassification:
    reason: str


def _resolve_hf_token(explicit: Optional[str] = None) -> Optional[str]:
    """The documented gotcha: a fresh process does not reliably inherit the
    persistent Windows User-level HF_TOKEN env var. os.environ is checked
    first (works when the caller sourced it correctly); if that's empty and
    we're on Windows, fall back to reading the real persistent value
    directly, so this adapter can't silently run unauthenticated just
    because the launching shell forgot to source it."""
    if explicit:
        return explicit
    token = os.environ.get("HF_TOKEN")
    if token:
        return token
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[System.Environment]::GetEnvironmentVariable('HF_TOKEN','User')"],
                capture_output=True, text=True, timeout=10,
            )
            value = result.stdout.strip()
            return value or None
        except Exception:
            return None
    return None


def _classify_error(exc: Exception, had_token: bool) -> _ErrorClassification:
    if not had_token:
        return _ErrorClassification(
            reason="no_token — no HF_TOKEN could be resolved (checked process env and "
            "the persistent Windows User env var); refusing to report this as a quota "
            "failure since an anonymous-tier call and a real quota-exhausted PRO call "
            "look identical from the outside"
        )
    message = str(exc).lower()
    if any(sig in message for sig in _QUOTA_SIGNAL_SUBSTRINGS):
        return _ErrorClassification(reason=f"rate_limited — authenticated call reported: {exc}")
    return _ErrorClassification(reason=f"unknown_error — authenticated call failed: {exc}")


def _parse_gallery_item(item: Any) -> str:
    if isinstance(item, dict):
        inner = item.get("image", item)
        return inner["path"] if isinstance(inner, dict) else inner
    elif isinstance(item, (list, tuple)):
        first = item[0]
        return first["path"] if isinstance(first, dict) else first
    return item


def _default_client_factory(token: Optional[str]):
    from gradio_client import Client
    return Client(MODEL_ID, token=token)


def generate(
    prompt_text: str,
    *,
    resolution: str = DEFAULT_RESOLUTION,
    steps: int = DEFAULT_STEPS,
    shift: float = DEFAULT_SHIFT,
    seed: int = 42,
    token: Optional[str] = None,
    client: Optional[Any] = None,
    client_factory: Callable[[Optional[str]], Any] = _default_client_factory,
    max_retries: int = 3,
    backoff_seconds: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bytes:
    """Generates one image via Z-Image-Turbo and returns JPEG bytes. Never
    writes to disk itself — the caller (store.quarantine_candidate) owns
    where bytes land, per section 27's 'no filename reuse, content-addressed
    path' rule. `client`/`client_factory` are injection points for tests;
    real callers never need to pass them."""
    resolved_token = _resolve_hf_token(token)
    real_client = client if client is not None else client_factory(resolved_token)

    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            result = real_client.predict(
                prompt=prompt_text,
                resolution=resolution,
                seed=seed,
                steps=steps,
                shift=shift,
                random_seed=True,
                gallery_images=[],
                api_name="/generate",
            )
            src = _parse_gallery_item(result[0][0])
            from PIL import Image
            img = Image.open(src).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=88)
            return buf.getvalue()
        except Exception as e:  # noqa: BLE001 — classified below, not swallowed
            last_exc = e
            if attempt < max_retries:
                delay = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
                sleep_fn(delay)

    classification = _classify_error(last_exc, had_token=bool(resolved_token))
    raise AdapterGenerationBlockedError(
        reason=classification.reason, attempts=max_retries, last_error=str(last_exc)
    )
