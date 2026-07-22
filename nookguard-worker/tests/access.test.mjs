import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyAccessJwt } from '../src/access.mjs';
import { generateTestKeypair, signTestJwt, fakeJwksFetcher } from './testJwt.mjs';

const AUDIENCE = 'test-access-application-aud-tag';

function requestWithToken(token) {
  const headers = token ? { 'Cf-Access-Jwt-Assertion': token } : {};
  return new Request('https://worker.example/owner_queue/abc/resolve', { headers });
}

test('verifyAccessJwt: skips verification entirely when no audience is configured (the un-provisioned default)', async () => {
  const result = await verifyAccessJwt(requestWithToken(undefined), { audience: undefined, jwksFetcher: async () => ({ keys: [] }) });
  assert.equal(result.ok, true);
  assert.equal(result.skipped, true);
});

test('verifyAccessJwt: rejects with 401 when configured but the request has no token header', async () => {
  const result = await verifyAccessJwt(requestWithToken(undefined), { audience: AUDIENCE, jwksFetcher: async () => ({ keys: [] }) });
  assert.equal(result.ok, false);
  assert.equal(result.status, 401);
  assert.match(result.error, /missing/);
});

test('verifyAccessJwt: accepts a real RS256-signed token with matching audience and unexpired exp', async () => {
  const { publicJwk, privateKey, kid } = await generateTestKeypair();
  const token = await signTestJwt(privateKey, kid, {
    aud: AUDIENCE, email: 'maurice@example.com', sub: 'user-123', exp: Math.floor(Date.now() / 1000) + 3600,
  });
  const result = await verifyAccessJwt(requestWithToken(token), { audience: AUDIENCE, jwksFetcher: fakeJwksFetcher(publicJwk) });
  assert.equal(result.ok, true);
  assert.equal(result.email, 'maurice@example.com');
  assert.equal(result.sub, 'user-123');
});

test('verifyAccessJwt: rejects a validly-signed token whose audience does not match this application', async () => {
  const { publicJwk, privateKey, kid } = await generateTestKeypair();
  const token = await signTestJwt(privateKey, kid, {
    aud: 'some-other-application', email: 'maurice@example.com', exp: Math.floor(Date.now() / 1000) + 3600,
  });
  const result = await verifyAccessJwt(requestWithToken(token), { audience: AUDIENCE, jwksFetcher: fakeJwksFetcher(publicJwk) });
  assert.equal(result.ok, false);
  assert.equal(result.status, 401);
  assert.match(result.error, /audience/);
});

test('verifyAccessJwt: rejects an expired token even with a valid signature and matching audience', async () => {
  const { publicJwk, privateKey, kid } = await generateTestKeypair();
  const token = await signTestJwt(privateKey, kid, {
    aud: AUDIENCE, email: 'maurice@example.com', exp: Math.floor(Date.now() / 1000) - 60,
  });
  const result = await verifyAccessJwt(requestWithToken(token), { audience: AUDIENCE, jwksFetcher: fakeJwksFetcher(publicJwk) });
  assert.equal(result.ok, false);
  assert.equal(result.status, 401);
  assert.match(result.error, /expired/);
});

test('verifyAccessJwt: rejects a token whose signature does not verify against the fetched JWKS (wrong key)', async () => {
  const real = await generateTestKeypair('kid-real');
  const impostor = await generateTestKeypair('kid-real'); // same kid, different actual key
  const token = await signTestJwt(impostor.privateKey, 'kid-real', {
    aud: AUDIENCE, exp: Math.floor(Date.now() / 1000) + 3600,
  });
  // The JWKS served to the verifier only knows about the REAL key, not the impostor's.
  const result = await verifyAccessJwt(requestWithToken(token), { audience: AUDIENCE, jwksFetcher: fakeJwksFetcher(real.publicJwk) });
  assert.equal(result.ok, false);
  assert.equal(result.status, 401);
  assert.match(result.error, /signature/);
});

test('verifyAccessJwt: rejects when no key in the JWKS matches the token\'s kid', async () => {
  const { publicJwk, privateKey } = await generateTestKeypair('kid-a');
  const token = await signTestJwt(privateKey, 'kid-b', { aud: AUDIENCE, exp: Math.floor(Date.now() / 1000) + 3600 });
  const result = await verifyAccessJwt(requestWithToken(token), { audience: AUDIENCE, jwksFetcher: fakeJwksFetcher(publicJwk) });
  assert.equal(result.ok, false);
  assert.equal(result.status, 401);
  assert.match(result.error, /no matching key/);
});

test('verifyAccessJwt: rejects a malformed token that is not a three-part JWT', async () => {
  const result = await verifyAccessJwt(requestWithToken('not-a-jwt'), { audience: AUDIENCE, jwksFetcher: async () => ({ keys: [] }) });
  assert.equal(result.ok, false);
  assert.equal(result.status, 401);
  assert.match(result.error, /malformed/);
});

test('verifyAccessJwt: rejects a token whose header claims an unsupported algorithm', async () => {
  const header = { alg: 'none', typ: 'JWT', kid: 'anything' };
  const payload = { aud: AUDIENCE, exp: Math.floor(Date.now() / 1000) + 3600 };
  const b64 = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url');
  const forgedToken = `${b64(header)}.${b64(payload)}.`;
  const result = await verifyAccessJwt(requestWithToken(forgedToken), { audience: AUDIENCE, jwksFetcher: async () => ({ keys: [] }) });
  assert.equal(result.ok, false);
  assert.equal(result.status, 401);
  assert.match(result.error, /alg/);
});
