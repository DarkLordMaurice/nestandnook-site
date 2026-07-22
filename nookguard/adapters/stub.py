"""Stub adapter — produces a tiny, real, valid PNG so downstream technical
validation has something genuine to check. Not connected to any real model.
adapter_version is prefixed 'stub-' so nothing downstream can mistake this for
a real generation if a record ever leaks into a real review pack."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

ADAPTER_VERSION = "stub-0.1.0"


def generate(prompt_text: str, *, width: int = 64, height: int = 64) -> bytes:
    img = Image.new("RGB", (width, height), color=(230, 220, 205))
    draw = ImageDraw.Draw(img)
    draw.text((4, 4), "NOOKGUARD STUB", fill=(80, 40, 20))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
