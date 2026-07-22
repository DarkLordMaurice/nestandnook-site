"""Production verifier (Commit 12, Appendix A + regression fixture
"Repository replacement differs from Cloudflare-served bytes -> FAIL |
Production hash mismatch"). Two real, independently-usable checks:

  - verify_against_local_build(): compares a released public file's bytes
    against the equivalent file inside a real `astro build` output
    (dist/). Genuinely runnable and checkable in this environment today --
    no network dependency, nothing mocked. Astro copies public/ into dist/
    verbatim at the same relative path, so this is a real, meaningful
    parity check, not a placeholder.
  - verify_against_live_url(): fetches the actual bytes being served at a
    live production URL and compares. Uses dependency injection (a
    `fetcher` callable) for testability, matching this project's standing
    pattern for every other network-touching component (the HF adapter,
    Anthropic review sessions) -- the real default fetcher is unverified
    live in this session for lack of network access to the real domain,
    same standing caveat as those.

Either check returning a hash mismatch, or failing to read/fetch at all,
resolves to PROD_MISMATCH -- "could not verify" is never silently treated
as "verified." No third state exists for that ambiguity on purpose."""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .hashing import sha256_bytes
from .state_machine import AssetState

Fetcher = Callable[[str], bytes]


@dataclass
class VerificationResult:
    state: AssetState
    reason: str


def _default_fetcher(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 - deliberate, real HTTP GET
        return resp.read()


def verify_against_local_build(
    public_path: Path, expected_sha256: str, dist_root: Path, public_root: Path,
) -> VerificationResult:
    """public_path is the file under the site's public/ tree that
    publish_candidate() just wrote; dist_root is a real `astro build`
    output directory; public_root is the site's actual `public/` directory
    itself (the parent Astro mirrors wholesale into dist/ -- NOT the
    specific leaf subdirectory a given release was written into, e.g.
    `site/public/`, not `site/public/winnie/`), used here to compute the
    file's path relative to that root so the equivalent dist/ location
    (which preserves the same subdirectory structure) can be found."""
    public_path, dist_root, public_root = Path(public_path), Path(dist_root), Path(public_root)
    try:
        relative = public_path.resolve().relative_to(public_root.resolve())
    except ValueError:
        return VerificationResult(
            AssetState.PROD_MISMATCH,
            f"{public_path} is not inside the given public_root {public_root}",
        )

    dist_path = dist_root / relative
    if not dist_path.exists():
        return VerificationResult(
            AssetState.PROD_MISMATCH,
            f"expected built file not found at {dist_path} -- run a real "
            "`astro build` before verifying",
        )

    actual = sha256_bytes(dist_path.read_bytes())
    if actual != expected_sha256:
        return VerificationResult(
            AssetState.PROD_MISMATCH,
            f"dist bytes at {dist_path} hash to {actual}, expected {expected_sha256}",
        )
    return VerificationResult(AssetState.PROD_VERIFIED, f"dist bytes at {dist_path} match expected hash")


def verify_against_live_url(
    url: str, expected_sha256: str, *, fetcher: Fetcher = _default_fetcher,
) -> VerificationResult:
    try:
        content = fetcher(url)
    except Exception as e:  # noqa: BLE001 - any fetch failure is a real mismatch, not a crash
        return VerificationResult(AssetState.PROD_MISMATCH, f"could not fetch {url}: {e}")

    actual = sha256_bytes(content)
    if actual != expected_sha256:
        return VerificationResult(
            AssetState.PROD_MISMATCH,
            f"live bytes at {url} hash to {actual}, expected {expected_sha256}",
        )
    return VerificationResult(AssetState.PROD_VERIFIED, f"live bytes at {url} match expected hash")


def verify_production(
    public_path: Path,
    expected_sha256: str,
    *,
    dist_root: Optional[Path] = None,
    public_root: Optional[Path] = None,
    live_url: Optional[str] = None,
    fetcher: Fetcher = _default_fetcher,
) -> VerificationResult:
    """Orchestrator: pick local-build or live-URL verification based on
    which arguments were supplied. Exactly one mode must be requested --
    silently preferring one over the other if both were passed would hide
    a caller mistake."""
    if dist_root is not None and live_url is not None:
        raise ValueError("verify_production accepts either dist_root or live_url, not both")
    if dist_root is not None:
        if public_root is None:
            raise ValueError("public_root is required alongside dist_root")
        return verify_against_local_build(public_path, expected_sha256, dist_root, public_root)
    if live_url is not None:
        return verify_against_live_url(live_url, expected_sha256, fetcher=fetcher)
    raise ValueError("verify_production requires either dist_root (+public_root) or live_url")
