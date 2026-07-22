// R2-backed candidate artifact byte storage. Content-addressed by SHA-256,
// the same "hash is the truth" philosophy as nookguard/hashing.py's
// content_addressed_path() (Python, Commit 2) and nookguard/manifest.py's
// content_hashed_filename() (Python, Commit 12) -- see hashing.py's own
// docstring: "no filename reuse... public filename is assigned only at
// release."
//
// R2 keys live under a flat `candidates/` prefix, keyed by the full raw
// SHA-256 (never truncated -- truncation is a Commit 12 concept for
// *public* release filenames, not for content-addressed storage identity).
// Content type is stored as R2 object metadata rather than baked into the
// key, since it isn't part of what makes two objects the same or
// different -- the hash is.

const KEY_PREFIX = 'candidates/';

function keyFor(sha256) {
  return `${KEY_PREFIX}${sha256}`;
}

const SHA256_HEX_RE = /^[0-9a-f]{64}$/;

async function sha256Hex(bytes) {
  // Web Crypto's subtle.digest is a real global in both Node (18.5+) and
  // the Cloudflare Workers runtime -- zero npm dependency needed, same
  // reasoning that led to node:sqlite/node:test in Commit 14.
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Store `bytes` under the content-addressed key for `sha256` -- but only
 * after verifying `bytes` actually hashes to `sha256`. An R2 PUT request
 * with a wrong or forged hash in its URL is exactly what content-addressed
 * storage exists to make impossible, so this check runs before
 * `bucket.put()` is ever called, not assumed from the caller's claim. This
 * is the R2-storage twin of Commit 12's release-integrity check
 * (`verify_against_local_build` proving released bytes match their
 * manifest hash) -- same invariant, checked at write time instead of at
 * verification time.
 */
export async function putArtifact(bucket, sha256, bytes, contentType) {
  if (!sha256 || !SHA256_HEX_RE.test(sha256)) {
    return { ok: false, status: 400, error: 'sha256 must be a 64-character lowercase hex string' };
  }
  if (!bytes || bytes.byteLength === 0) {
    return { ok: false, status: 400, error: 'request body is empty' };
  }
  const actualSha256 = await sha256Hex(bytes);
  if (actualSha256 !== sha256) {
    return {
      ok: false, status: 422,
      error: `uploaded bytes hash to ${actualSha256}, not the requested ${sha256} -- refusing to store under a false name`,
    };
  }
  await bucket.put(keyFor(sha256), bytes, {
    httpMetadata: contentType ? { contentType } : undefined,
  });
  return { ok: true, status: 201, sha256, size: bytes.byteLength };
}

/** Fetches the stored object for `sha256`. Returns the raw R2 object (or
 * fake-R2 equivalent) on success so the router can stream its bytes and
 * content type back without this function needing to know about HTTP. */
export async function getArtifact(bucket, sha256) {
  if (!sha256 || !SHA256_HEX_RE.test(sha256)) {
    return { ok: false, status: 400, error: 'sha256 must be a 64-character lowercase hex string' };
  }
  const object = await bucket.get(keyFor(sha256));
  if (!object) {
    return { ok: false, status: 404, error: `no artifact stored for ${sha256}` };
  }
  return { ok: true, status: 200, object };
}

/** Existence + size/content-type check, without transferring the bytes. */
export async function headArtifact(bucket, sha256) {
  if (!sha256 || !SHA256_HEX_RE.test(sha256)) {
    return { ok: false, status: 400, error: 'sha256 must be a 64-character lowercase hex string' };
  }
  const object = await bucket.head(keyFor(sha256));
  if (!object) {
    return { ok: false, status: 404, exists: false };
  }
  return {
    ok: true, status: 200, exists: true, size: object.size,
    contentType: object.httpMetadata ? object.httpMetadata.contentType : undefined,
  };
}
