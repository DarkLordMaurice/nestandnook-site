"""Real OCR validator (Commit 20, requirement 5) -- backed by RapidOCR
(rapidocr-onnxruntime), a pure-Python, ONNX-based OCR engine with no
external system-binary dependency.

Why RapidOCR and not pytesseract's usual system-Tesseract pairing, decided
after a real, documented installation attempt on this machine, not a
guess: `pytesseract` (the Python wrapper) installed cleanly via pip, but
Tesseract-OCR's own system binary installer (winget, id
UB-Mannheim.TesseractOCR) requires interactive UAC elevation this
automation channel cannot supply -- confirmed via a real `winget install`
attempt that failed with `0x800704c7 : The operation was canceled by the
user` (winget's real error for a declined/unavailable elevation prompt),
and `--scope user` has no applicable installer for this package ("No
applicable installer found"). `rapidocr-onnxruntime` installed and loaded
with zero elevation and was confirmed working against a REAL site image in
the same session (see docs/nookguard/BUILD-LOG.md's Commit 20 entry) -- it
correctly transcribed the real "MAKE BEAUTIFUL THINGS" wall-sign fixture
out of `public/winnie/office-hero.jpg`, unprompted, at ~86% confidence.

`pytesseract` remains installed and would work as an alternate backend the
moment Maurice runs the one-time elevated Tesseract-OCR install himself --
this module's `available()`/`scan()` contract does not depend on which
backend is present, only on being truthful about whichever is (or isn't)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

_ENGINE: Optional[Any] = None
_ENGINE_LOAD_ERROR: Optional[str] = None
_ENGINE_LOAD_ATTEMPTED = False


def _get_engine() -> tuple[Optional[Any], Optional[str]]:
    """Lazily constructs and caches the real RapidOCR engine instance --
    loading model weights is real, measurable work (a first real call in
    this session took ~2.3s wall time including model load), so this
    happens at most once per process, not once per validate() call.
    Returns (engine, error) -- never raises; a failed import/load is
    reported, not crashed on, matching this codebase's 'classify, don't
    crash' convention (see adapters/huggingface.py's `_resolve_hf_token`,
    cli_reviewer.py's `resolve_claude_cli_path`)."""
    global _ENGINE, _ENGINE_LOAD_ERROR, _ENGINE_LOAD_ATTEMPTED
    if _ENGINE_LOAD_ATTEMPTED:
        return _ENGINE, _ENGINE_LOAD_ERROR
    _ENGINE_LOAD_ATTEMPTED = True
    try:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    except Exception as e:  # noqa: BLE001 -- any import/load failure is a real "unavailable" state
        _ENGINE_LOAD_ERROR = f"{type(e).__name__}: {e}"
    return _ENGINE, _ENGINE_LOAD_ERROR


def reset_engine_cache_for_tests() -> None:
    """Test-only escape hatch -- lets a test force `_get_engine()` to
    re-attempt loading (e.g. to simulate an unavailable engine) instead of
    trusting the real process-wide cache, which would otherwise leak
    between test cases in the same pytest process."""
    global _ENGINE, _ENGINE_LOAD_ERROR, _ENGINE_LOAD_ATTEMPTED
    _ENGINE, _ENGINE_LOAD_ERROR, _ENGINE_LOAD_ATTEMPTED = None, None, False


def available() -> bool:
    """True only if the real engine actually loaded -- never a guess based
    on whether the package is merely importable."""
    engine, _ = _get_engine()
    return engine is not None


def scan(path: str | Path) -> dict[str, Any]:
    """Runs real OCR against a real image file. Returns
    `{"performed": bool, "detections": [{"text": str, "confidence": float,
    "box": [[x, y], ...]}], "reason": str}` -- `reason` is only present
    when `performed` is False. Never raises: a real per-image OCR failure
    (corrupt file, engine error) is reported as `performed: False` with the
    real exception message, never silently swallowed into a false-clean
    result."""
    engine, load_error = _get_engine()
    if engine is None:
        return {"performed": False, "reason": load_error or "OCR engine unavailable", "detections": []}

    try:
        result, _elapse = engine(str(path))
    except Exception as e:  # noqa: BLE001 -- real, unexpected per-call failure, still classified not crashed
        return {"performed": False, "reason": f"{type(e).__name__}: {e}", "detections": []}

    detections: list[dict[str, Any]] = []
    for box, text, confidence in (result or []):
        try:
            confidence_f = float(confidence)
        except (TypeError, ValueError):
            confidence_f = 0.0
        detections.append({"text": text, "confidence": confidence_f, "box": box})

    return {"performed": True, "detections": detections}
