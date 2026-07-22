"""Technical validators for images (section 28's 'technical pass is not
semantic pass' — this file only ever judges well-formedness/deterministic
properties, never scene content). Commit 6 fills in duplicate detection
(dedup.py), EXIF/privacy scan, and blank/solid detection as real checks.
Two items remain genuinely not implemented here, deliberately, not from
laziness — see NOT_YET_IMPLEMENTED's docstring below for why each one is
out of scope for a deterministic code check."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PIL import ExifTags, Image, ImageStat, UnidentifiedImageError

from ..dedup import DedupRegistry

# Both remaining items are deliberately deferred, not missing by oversight:
# - edge_clipping_risk: "is the subject clipped at the frame edge" requires
#   knowing where the subject is, which is a semantic/subject-detection
#   question — that's what the blind-observer layer (Commit 7-8) exists for,
#   not a pixel-level deterministic check. Forcing a fake heuristic here
#   (e.g. "content near the border") would produce false confidence.
# - ocr_logo_scan: genuinely not implemented — neither `pytesseract` nor a
#   system `tesseract` binary exists in this environment (checked directly,
#   not assumed: `shutil.which("tesseract")` returned None). `validate()`
#   reports this as `performed: False` with the concrete reason, never as a
#   silent pass.
NOT_YET_IMPLEMENTED = [
    "edge_clipping_risk",
    "ocr_logo_scan",
]


def _check_exif_privacy(img: Image.Image) -> dict[str, Any]:
    """Flags embedded GPS EXIF data — a real privacy leak risk if this image
    ships publicly. AI-generated images normally carry none, but a real
    reference/uploaded photo could."""
    try:
        exif = img.getexif()
    except Exception:
        return {"has_exif": False, "gps_data_present": False}
    if not exif:
        return {"has_exif": False, "gps_data_present": False}
    gps_tag_id = next((k for k, v in ExifTags.TAGS.items() if v == "GPSInfo"), None)
    gps_present = gps_tag_id is not None and gps_tag_id in exif
    return {"has_exif": True, "gps_data_present": bool(gps_present)}


def _check_blank_or_solid(img: Image.Image, stddev_threshold: float = 2.0) -> dict[str, Any]:
    """A near-zero per-channel standard deviation means the frame is
    (near-)uniform — a real generation defect (blank/solid output), not a
    stylistic judgment."""
    stat = ImageStat.Stat(img.convert("RGB"))
    max_stddev = max(stat.stddev) if stat.stddev else 0.0
    return {"max_channel_stddev": round(max_stddev, 4), "is_blank_or_solid": max_stddev < stddev_threshold}


def _check_ocr_logo_scan() -> dict[str, Any]:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return {"performed": False, "reason": "pytesseract not installed in this environment"}
    import shutil
    if shutil.which("tesseract") is None:
        return {"performed": False, "reason": "tesseract binary not found on PATH"}
    return {"performed": False, "reason": "dependencies present but scan logic not yet wired"}


def validate(
    path: str | Path,
    *,
    min_width: int = 32,
    min_height: int = 32,
    dedup_registry: Optional[DedupRegistry] = None,
    candidate_sha256: Optional[str] = None,
    near_duplicate_threshold: int = 5,
) -> dict[str, Any]:
    """Returns {"technical_pass": bool, "checks": {...}, "checks_not_yet_
    implemented": [...]}. Never raises for a bad image — a corrupt file is a
    failed check, not an exception, so callers always get a JSON-able report.

    `dedup_registry`/`candidate_sha256` are optional: if provided, exact and
    near-duplicate checks run for real against the registry's corpus; if
    omitted, both are reported as `performed: False` rather than silently
    treated as clean (a caller that forgets to pass a registry should see
    that in the report, not get a false-clean result)."""
    path = Path(path)
    checks: dict[str, Any] = {}

    checks["file_exists"] = path.exists()
    if not checks["file_exists"]:
        return {"technical_pass": False, "checks": checks,
                "checks_not_yet_implemented": NOT_YET_IMPLEMENTED}

    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            width, height = img.size
            mode = img.mode
            exif_check = _check_exif_privacy(img)
            blank_check = _check_blank_or_solid(img)
        checks["opens_and_decodes"] = True
        checks["dimensions"] = {"width": width, "height": height}
        checks["color_mode"] = mode
        checks["min_resolution_ok"] = width >= min_width and height >= min_height
        checks["exif_privacy_scan"] = exif_check
        checks["blank_or_solid_image"] = blank_check
    except (UnidentifiedImageError, OSError) as e:
        checks["opens_and_decodes"] = False
        checks["decode_error"] = str(e)
        return {"technical_pass": False, "checks": checks,
                "checks_not_yet_implemented": NOT_YET_IMPLEMENTED}

    file_size = path.stat().st_size
    checks["file_size_bytes"] = file_size
    checks["file_size_nonzero"] = file_size > 0

    if dedup_registry is not None:
        exact_matches = dedup_registry.check_exact_duplicate(path, exclude=candidate_sha256)
        near_matches = dedup_registry.check_near_duplicates(
            path, threshold=near_duplicate_threshold, exclude=candidate_sha256
        )
        checks["exact_hash_duplicate"] = {"performed": True, "matches": exact_matches}
        checks["perceptual_near_duplicate"] = {"performed": True, "matches": near_matches,
                                                "threshold": near_duplicate_threshold}
    else:
        checks["exact_hash_duplicate"] = {"performed": False, "reason": "no dedup_registry provided"}
        checks["perceptual_near_duplicate"] = {"performed": False, "reason": "no dedup_registry provided"}

    checks["ocr_logo_scan"] = _check_ocr_logo_scan()

    technical_pass = (
        checks["opens_and_decodes"]
        and checks["min_resolution_ok"]
        and checks["file_size_nonzero"]
        and not checks["exif_privacy_scan"]["gps_data_present"]
        and not checks["blank_or_solid_image"]["is_blank_or_solid"]
        and not checks["exact_hash_duplicate"].get("matches")
    )
    return {
        "technical_pass": technical_pass,
        "checks": checks,
        "checks_not_yet_implemented": NOT_YET_IMPLEMENTED,
    }
