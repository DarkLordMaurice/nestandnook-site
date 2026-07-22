// An R2Bucket-shaped in-memory store, for tests only. Mirrors the exact
// three methods src/artifacts.mjs actually calls (put/get/head) with the
// same async signatures and return shapes Cloudflare's real R2 binding
// uses. Like tests/fakeD1.mjs, this proves the application logic in
// src/artifacts.mjs and the /artifacts routes in src/router.mjs is
// correct -- real hashing (Web Crypto, not a stub), real byte storage and
// retrieval, real 404-on-miss behavior. It does not exercise R2's real
// network, durability, or consistency behavior. See README.md's
// "Unresolved risks."

export class FakeR2Bucket {
  constructor() {
    this._objects = new Map(); // key -> { bytes: Uint8Array, httpMetadata }
  }

  async put(key, bytes, options = {}) {
    const stored = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    const entry = { bytes: stored, httpMetadata: options.httpMetadata };
    this._objects.set(key, entry);
    return { key, size: stored.byteLength, httpMetadata: entry.httpMetadata };
  }

  async get(key) {
    const entry = this._objects.get(key);
    if (!entry) return null;
    return {
      key,
      size: entry.bytes.byteLength,
      httpMetadata: entry.httpMetadata,
      arrayBuffer: async () => entry.bytes.buffer.slice(
        entry.bytes.byteOffset, entry.bytes.byteOffset + entry.bytes.byteLength,
      ),
    };
  }

  async head(key) {
    const entry = this._objects.get(key);
    if (!entry) return null;
    return { key, size: entry.bytes.byteLength, httpMetadata: entry.httpMetadata };
  }
}
