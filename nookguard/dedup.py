"""Duplicate detection registry (Commit 6). Two distinct checks, per section
28: exact-hash duplicate (byte-identical — a hard technical fail, since
section 27 already promises 'no filename reuse' and a byte-identical output
from a DIFFERENT generation attempt means something is actually wrong, e.g. a
cached/stale adapter response) and perceptual near-duplicate (visually
similar but not identical — reported for review, not auto-failed, since a
consistent brand style can legitimately produce similar-looking shots).

Perceptual hashing is implemented directly on PIL (average hash / aHash) —
no `imagehash` dependency, since it isn't installed in this environment and
aHash is ~15 lines of real, well-understood, verifiable code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PIL import Image

from .hashing import sha256_file

PHASH_SIZE = 8  # 8x8 -> 64-bit hash, standard aHash size


def average_hash(path: str | Path, hash_size: int = PHASH_SIZE) -> str:
    """Real aHash: grayscale, downscale to hash_size x hash_size, threshold
    each pixel against the mean, pack into a hex string. Two images with a
    small Hamming distance between their hashes look visually similar."""
    with Image.open(path) as img:
        small = img.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
        # Pillow >=12 deprecates getdata() in favor of get_flattened_data();
        # fall back for older Pillow so this doesn't hard-depend on a very
        # recent version.
        if hasattr(small, "get_flattened_data"):
            pixels = list(small.get_flattened_data())
        else:
            pixels = list(small.getdata())
    mean = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= mean else "0" for p in pixels)
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"


def hamming_distance(hash_a: str, hash_b: str) -> int:
    int_a, int_b = int(hash_a, 16), int(hash_b, 16)
    return bin(int_a ^ int_b).count("1")


class DedupRegistry:
    """Persists to a single JSON file: {candidate_sha256: {"exact": sha256,
    "phash": "..."}}. Loaded fresh each call site — this is a small, slow-
    growing corpus (one entry per released/quarantined candidate), not a
    high-throughput store, so simplicity wins over a real DB here."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def register(self, candidate_sha256: str, image_path: str | Path) -> None:
        data = self._load()
        data[candidate_sha256] = {
            "exact": sha256_file(image_path),
            "phash": average_hash(image_path),
        }
        self._save(data)

    def check_exact_duplicate(self, image_path: str | Path,
                               exclude: Optional[str] = None) -> list[str]:
        target = sha256_file(image_path)
        data = self._load()
        return [cid for cid, entry in data.items()
                if entry["exact"] == target and cid != exclude]

    def check_near_duplicates(self, image_path: str | Path, threshold: int = 5,
                               exclude: Optional[str] = None) -> list[dict[str, object]]:
        target_phash = average_hash(image_path)
        data = self._load()
        matches = []
        for cid, entry in data.items():
            if cid == exclude:
                continue
            distance = hamming_distance(target_phash, entry["phash"])
            if distance <= threshold:
                matches.append({"candidate_sha256": cid, "hamming_distance": distance})
        return matches
