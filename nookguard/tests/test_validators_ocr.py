"""Commit 20: real OCR validator tests. `available()`/`scan()` are tested
against the REAL RapidOCR engine actually installed on this machine (no
mock) to prove the real installation genuinely works end to end, plus
injected-failure tests for the unavailable path, using the module's own
`reset_engine_cache_for_tests()` escape hatch so tests don't leak the
process-wide engine cache into each other."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from nookguard.validators import ocr


@pytest.fixture(autouse=True)
def _reset_engine_cache():
    """Every test in this file gets a clean slate -- the real module-level
    cache in ocr.py is intentionally process-wide in production (avoid
    reloading model weights per call), but that same behavior would let one
    test's monkeypatch leak into the next test's real-engine assertions."""
    ocr.reset_engine_cache_for_tests()
    yield
    ocr.reset_engine_cache_for_tests()


def test_available_is_true_on_this_real_machine():
    """Confirms the real installation this commit performed (pip install
    rapidocr-onnxruntime, no admin rights needed) actually works -- not a
    mock, the genuine engine load."""
    assert ocr.available() is True


def test_scan_real_image_returns_real_detections():
    """Runs real OCR against a real image with real, known text content
    (rendered here, not reusing an external file, so the expected text is
    unambiguous) and confirms the real engine actually reads it."""
    d = Path(tempfile.mkdtemp())
    p = d / "text.png"
    img = Image.new("RGB", (400, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 50), "HELLO NOOKGUARD", fill=(0, 0, 0))
    img.save(p)

    result = ocr.scan(p)
    assert result["performed"] is True
    assert isinstance(result["detections"], list)
    combined_text = " ".join(det["text"].upper() for det in result["detections"])
    assert "NOOKGUARD" in combined_text or "HELLO" in combined_text


def test_scan_missing_file_reports_performed_false_not_a_crash():
    result = ocr.scan("/nonexistent/path/does-not-exist.png")
    assert result["performed"] is False
    assert "reason" in result
    assert result["detections"] == []


def test_scan_reports_unavailable_when_engine_fails_to_load(monkeypatch):
    """Simulates a genuinely broken/missing engine (the real scenario on a
    machine without rapidocr-onnxruntime installed, or the Tesseract-OCR
    binary elevation gap this commit's BUILD-LOG entry documents) by
    forcing _get_engine's real import to fail."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "rapidocr_onnxruntime":
            raise ImportError("simulated: rapidocr_onnxruntime not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert ocr.available() is False
    result = ocr.scan("/any/path.png")
    assert result["performed"] is False
    assert "simulated" in result["reason"]
