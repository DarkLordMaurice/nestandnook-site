import hashlib

from nookguard.hashing import sha256_bytes, sha256_canonical_json, content_addressed_path


def test_sha256_bytes_matches_stdlib_hashlib():
    # Don't hand-type hash constants from memory — compute the expected value
    # the same way hashlib would and compare, avoiding transcription errors.
    for data in (b"", b"hello", b"NookGuard"):
        assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()
        assert len(sha256_bytes(data)) == 64


def test_sha256_canonical_json_order_independent():
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert sha256_canonical_json(a) == sha256_canonical_json(b)


def test_sha256_canonical_json_value_sensitive():
    assert sha256_canonical_json({"a": 1}) != sha256_canonical_json({"a": 2})


def test_content_addressed_path_uses_hash():
    p = content_addressed_path("/tmp/quarantine", b"hello world", ".png")
    assert p.name == sha256_bytes(b"hello world") + ".png"
