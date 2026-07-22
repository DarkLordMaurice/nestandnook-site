"""Minimal real technical validators for images (section 28's 'technical pass
is not semantic pass' — this file only ever judges well-formedness, never
content). Commit 6 expands this with duplicate detection, EXIF/privacy scan,
blank/solid detection, and OCR/logo scan — those are NOT here yet, and
`validate()`'s report says so via `checks_not_yet_implemented` rather than
silently passing on checks it doesn't perform."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

NOT_YET_IMPLEMENTED = [
    "exact_hash_duplicate",
    "perceptual_near_duplicate",
    "exif_privacy_scan",
    "blank_or_solid_image",
    "edge_clipping_risk",
    "ocr_logo_scan",
]


def validate(path: str | Path, *, min_width: int = 32, min_height: int = 32) -> dict[str, Any]:
    """Returns {"technical_pass": bool, "checks": {...}, "checks_not_yet_
    implemented": [...]}. Never raises for a bad image — a corrupt file is a
    failed check, not an exception, so callers always get a JSON-able report."""
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
        checks["opens_and_decodes"] = True
        checks["dimensions"] = {"width": width, "height": height}
        checks["color_mode"] = mode
        checks["min_resolution_ok"] = width >= min_width and height >= min_height
    except (UnidentifiedImageError, OSError) as e:
        checks["opens_and_decodes"] = False
        checks["decode_error"] = str(e)
        return {"technical_pass": False, "checks": checks,
                "checks_not_yet_implemented": NOT_YET_IMPLEMENTED}

    file_size = path.stat().st_size
    checks["file_size_bytes"] = file_size
    checks["file_size_nonzero"] = file_size > 0

    technical_pass = (
        checks["opens_and_decodes"]
        and checks["min_resolution_ok"]
        and checks["file_size_nonzero"]
    )
    return {
        "technical_pass": technical_pass,
        "checks": checks,
        "checks_not_yet_implemented": NOT_YET_IMPLEMENTED,
    }
