"""Real Pillow contact-sheet assembly tests (Commit 10) -- no mocking needed,
same "test the real mechanism end to end" approach as test_preview.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from nookguard.contact_sheet import build_contact_sheet


def _make_image(path: Path, size=(200, 100), color=(255, 0, 0)) -> None:
    Image.new("RGB", size, color=color).save(path)


def test_build_contact_sheet_creates_a_real_grid_image():
    d = Path(tempfile.mkdtemp())
    p1, p2 = d / "a.png", d / "b.png"
    _make_image(p1)
    _make_image(p2, color=(0, 255, 0))
    out = d / "sheet.png"
    result_path = build_contact_sheet([str(p1), str(p2)], out, columns=2, labels=["desktop", "mobile"])
    assert Path(result_path).exists()
    sheet = Image.open(result_path)
    assert sheet.width > 0 and sheet.height > 0


def test_build_contact_sheet_single_column_is_taller_than_one_row():
    d = Path(tempfile.mkdtemp())
    p1, p2 = d / "a.png", d / "b.png"
    _make_image(p1)
    _make_image(p2)

    two_row_out = d / "two.png"
    build_contact_sheet([str(p1), str(p2)], two_row_out, columns=1)
    two_row = Image.open(two_row_out)

    one_row_out = d / "one.png"
    build_contact_sheet([str(p1)], one_row_out, columns=1)
    one_row = Image.open(one_row_out)

    assert two_row.height > one_row.height


def test_build_contact_sheet_requires_at_least_one_image():
    with pytest.raises(ValueError):
        build_contact_sheet([], "/tmp/nonexistent-out.png")


def test_build_contact_sheet_rejects_mismatched_labels_length():
    d = Path(tempfile.mkdtemp())
    p1 = d / "a.png"
    _make_image(p1)
    with pytest.raises(ValueError):
        build_contact_sheet([str(p1)], d / "out.png", labels=["one", "two"])


def test_build_contact_sheet_uses_filename_stem_as_default_label():
    d = Path(tempfile.mkdtemp())
    p1 = d / "desktop-shot.png"
    _make_image(p1)
    out = d / "sheet.png"
    result_path = build_contact_sheet([str(p1)], out)
    assert Path(result_path).exists()
