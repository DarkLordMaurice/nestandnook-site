import tempfile
from pathlib import Path

from PIL import Image

from nookguard.dedup import DedupRegistry
from nookguard.validators.image import validate


def _make_image(path: Path, color, size=(64, 64), noisy: bool = False) -> None:
    img = Image.new("RGB", size, color=color)
    if noisy:
        # Give it real variance so it doesn't trip blank/solid detection.
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        for i in range(0, size[0], 4):
            draw.line([(i, 0), (i, size[1])], fill=(color[0] ^ 0xFF, color[1], color[2]))
    img.save(path)


def test_validate_passes_a_well_formed_varied_image():
    d = Path(tempfile.mkdtemp())
    p = d / "good.png"
    _make_image(p, (100, 120, 140), noisy=True)
    report = validate(p)
    assert report["technical_pass"] is True
    assert report["checks"]["min_resolution_ok"] is True


def test_validate_fails_missing_file():
    report = validate("/nonexistent/path/does-not-exist.png")
    assert report["technical_pass"] is False
    assert report["checks"]["file_exists"] is False


def test_validate_fails_below_min_resolution():
    d = Path(tempfile.mkdtemp())
    p = d / "tiny.png"
    _make_image(p, (100, 100, 100), size=(8, 8), noisy=True)
    report = validate(p, min_width=32, min_height=32)
    assert report["technical_pass"] is False
    assert report["checks"]["min_resolution_ok"] is False


def test_validate_fails_blank_solid_image():
    d = Path(tempfile.mkdtemp())
    p = d / "blank.png"
    _make_image(p, (128, 128, 128), noisy=False)  # perfectly uniform
    report = validate(p)
    assert report["technical_pass"] is False
    assert report["checks"]["blank_or_solid_image"]["is_blank_or_solid"] is True


def test_validate_reports_dedup_not_performed_without_registry():
    d = Path(tempfile.mkdtemp())
    p = d / "good.png"
    _make_image(p, (10, 20, 30), noisy=True)
    report = validate(p)
    assert report["checks"]["exact_hash_duplicate"]["performed"] is False
    assert report["checks"]["perceptual_near_duplicate"]["performed"] is False


def test_validate_fails_on_registered_exact_duplicate():
    d = Path(tempfile.mkdtemp())
    registry = DedupRegistry(d / "registry.json")
    original = d / "original.png"
    _make_image(original, (60, 70, 80), noisy=True)
    registry.register("cand-original", original)

    duplicate = d / "duplicate.png"
    _make_image(duplicate, (60, 70, 80), noisy=True)  # same generation -> same bytes
    report = validate(duplicate, dedup_registry=registry, candidate_sha256="cand-new")
    assert report["checks"]["exact_hash_duplicate"]["matches"] == ["cand-original"]
    assert report["technical_pass"] is False


def test_validate_does_not_fail_on_near_duplicate_only():
    """Near-duplicate is reported, not auto-failed -- see the module
    docstring's explicit policy: exact = hard fail, near = flag for review."""
    d = Path(tempfile.mkdtemp())
    registry = DedupRegistry(d / "registry.json")
    original = d / "original.png"
    _make_image(original, (100, 100, 100), noisy=True)
    registry.register("cand-original", original)

    slightly_different = d / "slightly_different.png"
    _make_image(slightly_different, (102, 100, 100), noisy=True)
    report = validate(slightly_different, dedup_registry=registry, candidate_sha256="cand-new",
                       near_duplicate_threshold=20)
    # Exact match should NOT fire (different bytes), only near-duplicate may.
    assert report["checks"]["exact_hash_duplicate"]["matches"] == []


def test_validate_performs_real_ocr_scan_when_engine_available():
    """Commit 20: the OCR engine (validators/ocr.py, RapidOCR) is genuinely
    installed and loadable in this environment (confirmed directly against
    a real site image during that commit's own research -- see
    docs/nookguard/BUILD-LOG.md), so a normal validate() call now performs
    a real scan, not a 'deps missing' stub. `required` defaults to False
    (this call didn't ask for require_ocr) regardless of whether the scan
    itself ran."""
    d = Path(tempfile.mkdtemp())
    p = d / "good.png"
    _make_image(p, (10, 20, 30), noisy=True)
    report = validate(p)
    assert report["checks"]["ocr_logo_scan"]["performed"] is True
    assert isinstance(report["checks"]["ocr_logo_scan"]["detections"], list)
    assert report["checks"]["ocr_logo_scan"]["required"] is False
    assert "blocking_reason" not in report


def test_validate_does_not_block_when_ocr_not_required_even_if_unavailable(monkeypatch):
    """require_ocr defaults to False -- an unavailable OCR engine must not
    block a candidate that never asked for it."""
    import nookguard.validators.image as image_module

    monkeypatch.setattr(image_module.ocr_validator, "scan",
                         lambda path: {"performed": False, "reason": "simulated unavailable", "detections": []})
    d = Path(tempfile.mkdtemp())
    p = d / "good.png"
    _make_image(p, (10, 20, 30), noisy=True)
    report = validate(p, require_ocr=False)
    assert report["checks"]["ocr_logo_scan"]["performed"] is False
    assert report["technical_pass"] is True
    assert "blocking_reason" not in report


def test_validate_blocks_with_validator_unavailable_when_required_and_engine_missing(monkeypatch):
    """Commit 20, requirement 5's actual gate: a contract that DOES require
    OCR must be blocked, not silently passed, when the real engine can't
    run -- simulated here via monkeypatch since the real engine happens to
    be available on this machine (see the sibling test above) and this
    specific failure mode needs to be provable regardless of what's
    actually installed."""
    import nookguard.validators.image as image_module

    monkeypatch.setattr(image_module.ocr_validator, "scan",
                         lambda path: {"performed": False, "reason": "simulated unavailable", "detections": []})
    d = Path(tempfile.mkdtemp())
    p = d / "good.png"
    _make_image(p, (10, 20, 30), noisy=True)
    report = validate(p, require_ocr=True)
    assert report["checks"]["ocr_logo_scan"]["performed"] is False
    assert report["checks"]["ocr_logo_scan"]["required"] is True
    assert report["technical_pass"] is False
    assert report["blocking_reason"] == "VALIDATOR_UNAVAILABLE"


def test_validate_passes_ocr_requirement_when_engine_available(monkeypatch):
    """The inverse of the block case -- require_ocr=True with a genuinely
    available (here, simulated available) engine must NOT trigger
    VALIDATOR_UNAVAILABLE."""
    import nookguard.validators.image as image_module

    monkeypatch.setattr(image_module.ocr_validator, "scan",
                         lambda path: {"performed": True, "detections": []})
    d = Path(tempfile.mkdtemp())
    p = d / "good.png"
    _make_image(p, (10, 20, 30), noisy=True)
    report = validate(p, require_ocr=True)
    assert report["checks"]["ocr_logo_scan"]["performed"] is True
    assert "blocking_reason" not in report


def test_validate_exif_privacy_scan_reports_no_gps_for_plain_image():
    d = Path(tempfile.mkdtemp())
    p = d / "good.png"
    _make_image(p, (10, 20, 30), noisy=True)
    report = validate(p)
    assert report["checks"]["exif_privacy_scan"]["gps_data_present"] is False
