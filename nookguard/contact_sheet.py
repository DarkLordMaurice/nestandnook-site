"""Page contact sheets (Commit 10) -- combines multiple screenshots (e.g.
desktop + mobile of the same page) into a single labeled grid image, which
is what the page-reviewer session actually looks at. Self-contained on
Pillow, no new dependency, same pattern as the main project's own
scripts/make_contact_sheets.py but owned inside this package rather than
imported from outside it."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

LABEL_HEIGHT = 28
CELL_PADDING = 8
THUMB_MAX_HEIGHT = 900  # cap so a very tall full-page screenshot doesn't blow up the sheet


def _load_font():
    try:
        return ImageFont.load_default(size=16)
    except TypeError:
        return ImageFont.load_default()  # older Pillow: no size kwarg


def build_contact_sheet(
    image_paths: list[str],
    output_path: str | Path,
    columns: int = 2,
    labels: Optional[list[str]] = None,
) -> str:
    if not image_paths:
        raise ValueError("build_contact_sheet requires at least one image")
    if labels is not None and len(labels) != len(image_paths):
        raise ValueError("labels, if provided, must be the same length as image_paths")

    images = [Image.open(p).convert("RGB") for p in image_paths]

    # Scale each image down to a shared thumbnail width so the grid is
    # regular, preserving aspect ratio and capping height for very tall
    # full-page screenshots.
    thumb_width = min(img.width for img in images)
    thumbs = []
    for img in images:
        scale = thumb_width / img.width
        new_height = min(int(img.height * scale), THUMB_MAX_HEIGHT)
        thumbs.append(img.resize((thumb_width, new_height)))

    rows = (len(thumbs) + columns - 1) // columns
    cell_width = thumb_width + 2 * CELL_PADDING
    cell_height = max(t.height for t in thumbs) + LABEL_HEIGHT + 2 * CELL_PADDING

    sheet = Image.new("RGB", (cell_width * columns, cell_height * rows), color=(245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    font = _load_font()

    for i, thumb in enumerate(thumbs):
        col, row = i % columns, i // columns
        x = col * cell_width + CELL_PADDING
        y = row * cell_height + CELL_PADDING
        label = labels[i] if labels else Path(image_paths[i]).stem
        draw.text((x, y), label, fill=(20, 20, 20), font=font)
        sheet.paste(thumb, (x, y + LABEL_HEIGHT))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, "PNG")
    return str(output_path)
