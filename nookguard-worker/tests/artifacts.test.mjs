import test from 'node:test';
import assert from 'node:assert/strict';
import { FakeR2Bucket } from './fakeR2.mjs';
import { putArtifact, getArtifact, headArtifact } from '../src/artifacts.mjs';

async function realSha256Of(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

const SAMPLE_BYTES = new TextEncoder().encode('winnie measuring a shelf, allegedly');

test('putArtifact: stores bytes when the claimed hash matches the real hash', async () => {
  const bucket = new FakeR2Bucket();
  const sha256 = await realSha256Of(SAMPLE_BYTES);
  const result = await putArtifact(bucket, sha256, SAMPLE_BYTES, 'image/jpeg');
  assert.equal(result.ok, true);
  assert.equal(result.status, 201);
  assert.equal(result.sha256, sha256);
  assert.equal(result.size, SAMPLE_BYTES.byteLength);
});

test('putArtifact: rejects with 422 when the claimed hash does not match the real hash of the bytes, and stores nothing', async () => {
  const bucket = new FakeR2Bucket();
  const wrongSha256 = '1'.repeat(64);
  const result = await putArtifact(bucket, wrongSha256, SAMPLE_BYTES);
  assert.equal(result.ok, false);
  assert.equal(result.status, 422);
  assert.match(result.error, /refusing to store under a false name/);

  const fetched = await getArtifact(bucket, wrongSha256);
  assert.equal(fetched.ok, false);
  assert.equal(fetched.status, 404);
});

test('putArtifact: rejects a malformed sha256 (wrong length / not hex) with 400 before touching the bucket', async () => {
  const bucket = new FakeR2Bucket();
  const tooShort = await putArtifact(bucket, 'abc123', SAMPLE_BYTES);
  assert.equal(tooShort.ok, false);
  assert.equal(tooShort.status, 400);

  const notHex = await putArtifact(bucket, 'z'.repeat(64), SAMPLE_BYTES);
  assert.equal(notHex.ok, false);
  assert.equal(notHex.status, 400);

  const uppercase = await putArtifact(bucket, 'A'.repeat(64), SAMPLE_BYTES);
  assert.equal(uppercase.ok, false, 'uppercase hex is rejected -- Python hashlib.hexdigest() always produces lowercase, so this stays strict rather than normalizing');
});

test('putArtifact: rejects an empty body with 400', async () => {
  const bucket = new FakeR2Bucket();
  const sha256 = await realSha256Of(new Uint8Array(0));
  const result = await putArtifact(bucket, sha256, new Uint8Array(0));
  assert.equal(result.ok, false);
  assert.equal(result.status, 400);
  assert.match(result.error, /empty/);
});

test('putArtifact: re-uploading the identical bytes under the same hash is idempotent, not an error', async () => {
  const bucket = new FakeR2Bucket();
  const sha256 = await realSha256Of(SAMPLE_BYTES);
  const first = await putArtifact(bucket, sha256, SAMPLE_BYTES);
  const second = await putArtifact(bucket, sha256, SAMPLE_BYTES);
  assert.equal(first.ok, true);
  assert.equal(second.ok, true, 'content-addressed storage: the same bytes under the same hash is a no-op success, not a conflict');
});

test('getArtifact: round trips the exact bytes and content type that were stored', async () => {
  const bucket = new FakeR2Bucket();
  const sha256 = await realSha256Of(SAMPLE_BYTES);
  await putArtifact(bucket, sha256, SAMPLE_BYTES, 'image/jpeg');

  const fetched = await getArtifact(bucket, sha256);
  assert.equal(fetched.ok, true);
  const bytesBack = new Uint8Array(await fetched.object.arrayBuffer());
  assert.deepEqual(bytesBack, SAMPLE_BYTES);
  assert.equal(fetched.object.httpMetadata.contentType, 'image/jpeg');
});

test('getArtifact: 404s for a well-formed hash that was never stored', async () => {
  const bucket = new FakeR2Bucket();
  const result = await getArtifact(bucket, '9'.repeat(64));
  assert.equal(result.ok, false);
  assert.equal(result.status, 404);
});

test('headArtifact: reports exists=true with size and content type, without needing arrayBuffer()', async () => {
  const bucket = new FakeR2Bucket();
  const sha256 = await realSha256Of(SAMPLE_BYTES);
  await putArtifact(bucket, sha256, SAMPLE_BYTES, 'image/png');

  const result = await headArtifact(bucket, sha256);
  assert.equal(result.ok, true);
  assert.equal(result.exists, true);
  assert.equal(result.size, SAMPLE_BYTES.byteLength);
  assert.equal(result.contentType, 'image/png');
});

test('headArtifact: reports a clean 404/exists=false for bytes never stored', async () => {
  const bucket = new FakeR2Bucket();
  const result = await headArtifact(bucket, '8'.repeat(64));
  assert.equal(result.ok, false);
  assert.equal(result.status, 404);
  assert.equal(result.exists, false);
});
