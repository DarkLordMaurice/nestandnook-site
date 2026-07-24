"""PARSER / EVIDENCE-FLOW TEST FIXTURES ONLY -- NOT OPERATIONAL PROOF.

Relabeled 2026-07-23 (Commit 25, requirement 10). Every image this module
writes is a synthetic PIL render (a labeled rectangle, a captioned
gradient, a drawn silhouette) OR a plain copy of an unrelated known-clean
site photo -- none of them are real historical defective bytes. They
exist solely to exercise this pipeline's parsing/schema/evidence-flow
plumbing (does a candidate get quarantined, does review-pack-build run,
does an observer/judge round trip through the CLI correctly) in cheap,
fast, deterministic CI/test contexts -- NOT to demonstrate that NookGuard
can actually detect real visual defects. A blind observer could trivially
solve every one of these fixtures by reading the literal caption text
baked into the image (e.g. "TAPE MEASURE", "ARMCHAIR (indoor furniture,
outdoor enclosure)") rather than by making a real visual judgment, which
is exactly why these must never be cited as evidence that the semantic
review pipeline works. That evidence is `real_regression_fixtures.py`'s
corpus instead: real historical defective/clean image bytes extracted
byte-for-byte from git history (see `regression_images_real/` and
docs/nookguard/BUILD-LOG.md's Commit 25 entry), reviewed blind (no
caption, no label, no hint) through the full real prepare/observe/judge/
aggregate pipeline. If you are looking for operational proof this
pipeline catches real defects, use that corpus, not this one.

Run once to (re)produce this test corpus's image files; committed as a
permanent, reproducible script, not a throwaway one-off -- if a fixture
image is ever lost or needs regenerating, run this file directly
(`python -m nookguard.gen_regression_images`).

See regression_live.py's module docstring for further context on this
distinction."""

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

    # 5. Goat-enclosure reference-mismatch reproduction -- outdoor enclosure
    # with a smooth, uniform chain-link/vinyl-look fence instead of the real
    # weathered wood rails/mesh the location's canon reference photography
    # requires (regression_corpus.py's synthetic fixture 4, given a real
    # image counterpart here, added 2026-07-23 for the live-subagent
    # operational proof). The defect is deliberately in the FENCE material/
    # pattern only -- clean, mechanically-uniform diamond mesh -- since that
    # is what a real observer can actually describe from pixels alone; the
    # judge-side continuity-constraint failure itself is evaluated from the
    # contract's continuity_constraints field (aggregator.py), not from
    # anything paintable into the image.
    img = Image.new("RGB", (800, 500), color=(160, 200, 225))  # sky
    d = ImageDraw.Draw(img)
    d.rectangle([0, 320, 800, 500], fill=(140, 175, 100))  # ground/pen floor
    # Smooth, uniform diamond-mesh chain-link fence -- clean and mechanical,
    # not the weathered rough-cut wood rails a real barn/pen reference would
    # show.
    fence_color = (190, 195, 200)
    for x in range(-20, 820, 30):
        d.line([(x, 260), (x + 60, 340)], fill=fence_color, width=3)
        d.line([(x + 60, 260), (x, 340)], fill=fence_color, width=3)
    d.line([(0, 260), (800, 260)], fill=(150, 155, 160), width=6)
    d.line([(0, 340), (800, 340)], fill=(150, 155, 160), width=6)
    for x in range(0, 801, 200):
        d.rectangle([x - 4, 250, x + 4, 350], fill=(170, 175, 180))
    d.ellipse([340, 300, 460, 400], fill=(235, 235, 230), outline=(60, 60, 60), width=3)  # goat body (simple)
    d.text((30, 30), "Smooth uniform chain-link fence (reproduction) -- reference photography "
                      "shows rough-cut wood rails, not this.", fill=(20, 20, 20), font=_font(16))
    img.save(OUT_DIR / "goat_enclosure_reference_mismatch_reproduction.jpg", quality=90)
    written.append("goat_enclosure_reference_mismatch_reproduction.jpg (real render)")

    return written


if __name__ == "__main__":
    for line in generate():
        print("wrote", line)
    print("DONE")
