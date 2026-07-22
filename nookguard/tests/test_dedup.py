import tempfile
from pathlib import Path

from PIL import Image

from nookguard.dedup import DedupRegistry, average_hash, hamming_distance


def _make_image(path: Path, color: tuple[int, int, int], size=(32, 32)) -> None:
    Image.new("RGB", size, color=color).save(path)


def _make_gradient_image(path: Path, size=(32, 32), invert: bool = False) -> None:
    """aHash thresholds each pixel against the image's OWN mean, so a
    perfectly solid-color image always hashes to the same all-1s pattern
    regardless of its actual color (every pixel equals the mean by
    definition) -- that's expected aHash behavior (it captures texture/
    gradient structure, not absolute color), not a bug, but it makes solid
    fixtures useless for testing 'different images -> different hash'.
    Gradients give aHash real structure to distinguish."""
    img = Image.new("RGB", size)
    for y in range(size[1]):
        for x in range(size[0]):
            v = int(255 * (x / size[0]))
            if invert:
                v = 255 - v
            img.putpixel((x, y), (v, v, v))
    img.save(path)


def test_average_hash_identical_images_have_zero_distance():
    d = Path(tempfile.mkdtemp())
    p1, p2 = d / "a.png", d / "b.png"
    _make_image(p1, (100, 150, 200))
    _make_image(p2, (100, 150, 200))
    assert hamming_distance(average_hash(p1), average_hash(p2)) == 0


def test_average_hash_very_different_images_have_large_distance():
    d = Path(tempfile.mkdtemp())
    p1, p2 = d / "a.png", d / "b.png"
    _make_gradient_image(p1, invert=False)
    _make_gradient_image(p2, invert=True)  # mirror-image gradient: genuinely different structure
    assert hamming_distance(average_hash(p1), average_hash(p2)) > 20


def test_registry_check_exact_duplicate_finds_registered_match():
    d = Path(tempfile.mkdtemp())
    registry = DedupRegistry(d / "registry.json")
    original = d / "original.png"
    _make_image(original, (10, 20, 30))
    registry.register("cand-1", original)

    duplicate = d / "duplicate.png"
    _make_image(duplicate, (10, 20, 30))  # byte-identical content
    matches = registry.check_exact_duplicate(duplicate)
    assert matches == ["cand-1"]


def test_registry_check_exact_duplicate_excludes_self():
    d = Path(tempfile.mkdtemp())
    registry = DedupRegistry(d / "registry.json")
    original = d / "original.png"
    _make_image(original, (10, 20, 30))
    registry.register("cand-1", original)

    matches = registry.check_exact_duplicate(original, exclude="cand-1")
    assert matches == []


def test_registry_check_near_duplicates_finds_similar_but_not_identical():
    d = Path(tempfile.mkdtemp())
    registry = DedupRegistry(d / "registry.json")
    base = d / "base.png"
    _make_image(base, (100, 100, 100))
    registry.register("cand-1", base)

    # A very slightly different shade should still register as near-duplicate
    # at a generous threshold.
    similar = d / "similar.png"
    _make_image(similar, (105, 100, 100))
    matches = registry.check_near_duplicates(similar, threshold=10)
    assert any(m["candidate_sha256"] == "cand-1" for m in matches)


def test_registry_check_near_duplicates_empty_for_unrelated_images():
    d = Path(tempfile.mkdtemp())
    registry = DedupRegistry(d / "registry.json")
    base = d / "base.png"
    _make_gradient_image(base, invert=False)
    registry.register("cand-1", base)

    unrelated = d / "unrelated.png"
    _make_gradient_image(unrelated, invert=True)
    matches = registry.check_near_duplicates(unrelated, threshold=5)
    assert matches == []


def test_registry_persists_across_instances():
    d = Path(tempfile.mkdtemp())
    registry_path = d / "registry.json"
    original = d / "original.png"
    _make_image(original, (50, 60, 70))

    DedupRegistry(registry_path).register("cand-1", original)
    # Fresh instance, same path -- must read what was written, not hold state in memory.
    second = DedupRegistry(registry_path)
    assert second.check_exact_duplicate(original) == ["cand-1"]
