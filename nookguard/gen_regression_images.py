"""Real image generation for nookguard/regression_images/ (Commit 20).
Run once to (re)produce the live-review regression corpus's image files;
committed as a permanent, reproducible script, not a throwaway one-off --
if a regression image is ever lost or needs regenerating, run this file
directly (`python -m nookguard.gen_regression_images`).

Every file this writes is a REAL image (opens, decodes, has real pixel
content): three are purpose-built PIL renders (documented as
reproductions, since the real historical incidents' original defective
candidate bytes no longer exist, per this project's regenerate-only
architecture -- state_machine.py's `_REGENERATE_SOURCES`), one is a real
copy of a real, currently-live site photo used as a known-clean control.
See regression_live.py's module docstring for the full honesty note on
image provenance."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PACKAGE_ROOT = Path(__file__).resolve().parent
SITE_ROOT = PACKAGE_ROOT.parent
OUT_DIR = PACKAGE_ROOT / "regression_images"
REAL_SITE_PHOTO = SITE_ROOT / "public" / "winnie" / "office-hero.jpg"


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def generate() -> list[str]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    # 1. Known-clean control -- a real copy of the actual live site photo.
    shutil.copyfile(REAL_SITE_PHOTO, OUT_DIR / "known_clean_office_hero.jpg")
    written.append("known_clean_office_hero.jpg (real copy of office-hero.jpg)")

    # 2. Object-count contradiction -- exactly ONE clearly labeled object
    # drawn, real, unambiguous, verifiable by direct inspection of this file.
    img = Image.new("RGB", (800, 500), color=(235, 230, 220))
    d = ImageDraw.Draw(img)
    d.rectangle([300, 200, 500, 260], fill=(220, 190, 60), outline=(40, 40, 40), width=4)
    d.text((320, 220), "TAPE MEASURE", fill=(20, 20, 20), font=_font(22))
    d.text((30, 30), "Scene contains exactly ONE labeled object.", fill=(20, 20, 20), font=_font(20))
    img.save(OUT_DIR / "object_count_contradiction.jpg", quality=90)
    written.append("object_count_contradiction.jpg (real render, exactly 1 object)")

    # 3. Banana-foil-fusion reproduction -- a loaf shape with a foil-colored
    # strip blended into the crust with no visible seam/edge line (the real
    # defect: foil rendered as fused to, not resting on, the crust).
    img = Image.new("RGB", (800, 500), color=(245, 240, 232))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([200, 220, 600, 380], radius=40, fill=(150, 100, 55))
    for y in range(220, 300):
        t = (y - 220) / 80.0
        r = int(150 * (1 - t) + 190 * t)
        g = int(100 * (1 - t) + 190 * t)
        b = int(55 * (1 - t) + 200 * t)
        d.line([(200, y), (600, y)], fill=(r, g, b))
    d.text((30, 30), "Foil blended into crust with no visible seam (reproduction).",
           fill=(20, 20, 20), font=_font(18))
    img.save(OUT_DIR / "banana_foil_fusion_reproduction.jpg", quality=90)
    written.append("banana_foil_fusion_reproduction.jpg (real render)")

    # 4. Unexpected furniture in an outdoor enclosure reproduction -- outdoor
    # scene (sky, ground, wood-rail fence) with a clearly labeled indoor
    # armchair silhouette placed inside it.
    img = Image.new("RGB", (800, 500), color=(150, 195, 230))  # sky
    d = ImageDraw.Draw(img)
    d.rectangle([0, 300, 800, 500], fill=(120, 165, 90))  # ground
    for x in range(0, 800, 120):
        d.line([(x, 260), (x, 340)], fill=(120, 90, 60), width=10)  # fence posts
    d.line([(0, 280), (800, 280)], fill=(120, 90, 60), width=8)  # fence rail
    d.rounded_rectangle([320, 300, 480, 400], radius=15, fill=(120, 40, 40))
    d.rectangle([320, 250, 480, 310], fill=(140, 60, 60))
    d.text((300, 420), "ARMCHAIR (indoor furniture, outdoor enclosure)", fill=(20, 20, 20), font=_font(18))
    img.save(OUT_DIR / "unexpected_furniture_reproduction.jpg", quality=90)
    written.append("unexpected_furniture_reproduction.jpg (real render)")

    return written


if __name__ == "__main__":
    for line in generate():
        print("wrote", line)
    print("DONE")
