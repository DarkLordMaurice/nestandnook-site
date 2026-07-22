import test from 'node:test';
import assert from 'node:assert/strict';
import { createMigratedFakeD1 } from './fakeD1.mjs';
import { FakeR2Bucket } from './fakeR2.mjs';
import { generateTestKeypair, signTestJwt, fakeJwksFetcher } from './testJwt.mjs';
import { routeRequest } from '../src/router.mjs';

// Real Request/Response objects (global in Node 22+) round-tripped through
// routeRequest -- this is the same object shape Cloudflare passes into
// `fetch(request, env)` in production; only the `env = { db, artifacts,
// accessAudience, jwksFetcher }` bindings (here, the fakeD1/fakeR2
// instances and, where a test needs it, real self-signed JWTs) differ from
// a real deployment. `accessAudience`/`jwksFetcher` are left undefined by
// makeEnv() by default, matching production's un-provisioned default (see
// src/access.mjs) -- tests that specifically exercise Access verification
// pass their own env with those two fields set.

function makeEnv(overrides = {}) {
  return { db: createMigratedFakeD1(), artifacts: new FakeR2Bucket(), ...overrides };
}

function postJson(url, body) {
  return new Request(url, { method: 'POST', body: JSON.stringify(body), headers: { 'content-type': 'application/json' } });
}

function sampleAttempt(overrides = {}) {
  return {
    candidate_sha256: 'cand-router-1',
    asset_id: 'asset-1',
    spec_sha256: 'spec-sha-1',
    prompt_sha256: 'prompt-sha-1',
    generator_session_id: 'session-generator',
    artifact_uri: 'file:///quarantine/cand-router-1.jpg',
    metadata_json: '{}',
    created_at: '2026-07-22T00:00:00Z',
    ...overrides,
  };
}

test('POST /events then GET /events?run_id= round trips through real HTTP Request/Response', async () => {
  const env = makeEnv();
  const event = {
    event_id: 'evt-router-1', run_id: 'run-router-1', event_type: 'spec_locked', actor_role: 'planner',
    payload_json: '{}', payload_sha256: 'payload-sha', created_at: '2026-07-22T00:00:00Z',
  };
  const postResponse = await routeRequest(postJson('https://worker.example/events', event), env);
  assert.equal(postResponse.status, 201);
  const postBody = await postResponse.json();
  assert.equal(postBody.ok, true);

  const getResponse = await routeRequest(new Request('https://worker.example/events?run_id=run-router-1'), env);
  assert.equal(getResponse.status, 200);
  const getBody = await getResponse.json();
  assert.equal(getBody.events.length, 1);
  assert.equal(getBody.events[0].event_id, 'evt-router-1');
});

test('GET /events without run_id returns 400, not a database error', async () => {
  const env = makeEnv();
  const response = await routeRequest(new Request('https://worker.example/events'), env);
  assert.equal(response.status, 400);
});

test('POST /generation_attempts then GET /generation_attempts/:sha round trips', async () => {
  const env = makeEnv();
  const postResponse = await routeRequest(
    postJson('https://worker.example/generation_attempts', sampleAttempt()), env,
  );
  assert.equal(postResponse.status, 201);

  const getResponse = await routeRequest(
    new Request('https://worker.example/generation_attempts/cand-router-1'), env,
  );
  assert.equal(getResponse.status, 200);
  const body = await getResponse.json();
  assert.equal(body.generation_attempt.candidate_sha256, 'cand-router-1');
});

test('GET /generation_attempts/:sha 404s for an unknown candidate', async () => {
  const env = makeEnv();
  const response = await routeRequest(new Request('https://worker.example/generation_attempts/nope'), env);
  assert.equal(response.status, 404);
});

test('POST /reviews with reviewer_session_id equal to the generator is rejected over real HTTP, end to end', async () => {
  const env = makeEnv();
  await routeRequest(
    postJson('https://worker.example/generation_attempts', sampleAttempt({ generator_session_id: 'same-session' })),
    env,
  );
  const reviewResponse = await routeRequest(
    postJson('https://worker.example/reviews', {
      review_id: 'review-router-1', candidate_sha256: 'cand-router-1', review_stage: 'observe_a',
      reviewer_session_id: 'same-session', context_bundle_sha256: 'ctx-sha', result_json: '{}',
      created_at: '2026-07-22T00:01:00Z',
    }),
    env,
  );
  assert.equal(reviewResponse.status, 409);
  const body = await reviewResponse.json();
  assert.match(body.error, /must differ/);
});

test('POST /reviews with a valid distinct reviewer session succeeds, then GET /reviews lists it', async () => {
  const env = makeEnv();
  await routeRequest(postJson('https://worker.example/generation_attempts', sampleAttempt()), env);
  const reviewResponse = await routeRequest(
    postJson('https://worker.example/reviews', {
      review_id: 'review-router-2', candidate_sha256: 'cand-router-1', review_stage: 'observe_a',
      reviewer_session_id: 'session-reviewer', context_bundle_sha256: 'ctx-sha', result_json: '{}',
      created_at: '2026-07-22T00:01:00Z',
    }),
    env,
  );
  assert.equal(reviewResponse.status, 201);

  const listResponse = await routeRequest(
    new Request('https://worker.example/reviews?candidate_sha256=cand-router-1'), env,
  );
  assert.equal(listResponse.status, 200);
  const body = await listResponse.json();
  assert.equal(body.reviews.length, 1);
});

test('malformed JSON body returns 400, not an unhandled exception', async () => {
  const env = makeEnv();
  const badRequest = new Request('https://worker.example/events', {
    method: 'POST', body: '{not valid json', headers: { 'content-type': 'application/json' },
  });
  const response = await routeRequest(badRequest, env);
  assert.equal(response.status, 400);
});

test('unknown route returns 404 with a descriptive error, not a crash', async () => {
  const env = makeEnv();
  const response = await routeRequest(new Request('https://worker.example/does-not-exist'), env);
  assert.equal(response.status, 404);
  const body = await response.json();
  assert.match(body.error, /no route/);
});

// ---- Commit 15: /artifacts routes (R2-backed) ----

const KNOWN_BYTES = new TextEncoder().encode('hello nookguard artifact bytes');

// The tests below compute the real SHA-256 of KNOWN_BYTES at run time via
// Web Crypto rather than hardcoding a precomputed digest -- this is
// deliberate: it proves src/artifacts.mjs's own hash check agrees with an
// independently-computed hash of the same bytes, not just that it's
// internally self-consistent with whatever it happened to compute.
async function realSha256Of(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

test('PUT /artifacts/:sha256 with the correct hash stores the bytes, then GET returns them byte-for-byte', async () => {
  const env = makeEnv();
  const realSha256 = await realSha256Of(KNOWN_BYTES);

  const putResponse = await routeRequest(
    new Request(`https://worker.example/artifacts/${realSha256}`, {
      method: 'PUT', body: KNOWN_BYTES, headers: { 'content-type': 'image/jpeg' },
    }),
    env,
  );
  assert.equal(putResponse.status, 201);
  const putBody = await putResponse.json();
  assert.equal(putBody.sha256, realSha256);
  assert.equal(putBody.size, KNOWN_BYTES.byteLength);

  const getResponse = await routeRequest(new Request(`https://worker.example/artifacts/${realSha256}`), env);
  assert.equal(getResponse.status, 200);
  assert.equal(getResponse.headers.get('content-type'), 'image/jpeg');
  const returnedBytes = new Uint8Array(await getResponse.arrayBuffer());
  assert.deepEqual(returnedBytes, KNOWN_BYTES);
});

test('PUT /artifacts/:sha256 with a hash that does not match the body is rejected with 422, and nothing is stored', async () => {
  const env = makeEnv();
  const wrongSha256 = '0'.repeat(64);
  const putResponse = await routeRequest(
    new Request(`https://worker.example/artifacts/${wrongSha256}`, { method: 'PUT', body: KNOWN_BYTES }),
    env,
  );
  assert.equal(putResponse.status, 422);
  const body = await putResponse.json();
  assert.match(body.error, /refusing to store/);

  const getResponse = await routeRequest(new Request(`https://worker.example/artifacts/${wrongSha256}`), env);
  assert.equal(getResponse.status, 404);
});

test('GET /artifacts/:sha256 404s for bytes that were never uploaded', async () => {
  const env = makeEnv();
  const response = await routeRequest(new Request(`https://worker.example/artifacts/${'f'.repeat(64)}`), env);
  assert.equal(response.status, 404);
});

test('HEAD /artifacts/:sha256 reports existence and size without a body, and 404s when absent', async () => {
  const env = makeEnv();
  const realSha256 = await realSha256Of(KNOWN_BYTES);
  await routeRequest(
    new Request(`https://worker.example/artifacts/${realSha256}`, { method: 'PUT', body: KNOWN_BYTES }),
    env,
  );

  const headHit = await routeRequest(new Request(`https://worker.example/artifacts/${realSha256}`, { method: 'HEAD' }), env);
  assert.equal(headHit.status, 200);
  assert.equal(headHit.headers.get('content-length'), String(KNOWN_BYTES.byteLength));
  assert.equal(await headHit.text(), '');

  const headMiss = await routeRequest(new Request(`https://worker.example/artifacts/${'e'.repeat(64)}`, { method: 'HEAD' }), env);
  assert.equal(headMiss.status, 404);
});

// ---- CORS ----

test('OPTIONS preflight returns 204 with CORS headers, on any path', async () => {
  const env = makeEnv();
  const response = await routeRequest(new Request('https://worker.example/owner_queue', { method: 'OPTIONS' }), env);
  assert.equal(response.status, 204);
  assert.equal(response.headers.get('access-control-allow-origin'), '*');
});

test('a normal JSON response also carries CORS headers, not just the OPTIONS preflight', async () => {
  const env = makeEnv();
  const response = await routeRequest(new Request('https://worker.example/does-not-exist'), env);
  assert.equal(response.headers.get('access-control-allow-origin'), '*');
});

// ---- Commit 16: /owner_queue routes (D1-backed) ----

function sampleOwnerQueueEntry(overrides = {}) {
  return {
    entry_id: 'oq-router-1',
    asset_id: 'asset-1',
    candidate_sha256: 'cand-router-1',
    question: 'Approve hero image for hub landing page, exact hash cand-router-1?',
    reasons: ['reviewer_disagreement'],
    risk_tier: 'tier_2',
    result_state: 'needs_owner',
    evidence: { candidate: 'cand-router-1.jpg' },
    queued_at: '2026-07-22T00:05:00Z',
    ...overrides,
  };
}

test('POST /owner_queue then GET /owner_queue lists it as pending, over real HTTP', async () => {
  const env = makeEnv();
  await routeRequest(postJson('https://worker.example/generation_attempts', sampleAttempt()), env);

  const postResponse = await routeRequest(postJson('https://worker.example/owner_queue', sampleOwnerQueueEntry()), env);
  assert.equal(postResponse.status, 201);

  const listResponse = await routeRequest(new Request('https://worker.example/owner_queue'), env);
  assert.equal(listResponse.status, 200);
  const body = await listResponse.json();
  assert.equal(body.entries.length, 1);
  assert.equal(body.entries[0].status, 'pending');
});

test('POST /owner_queue/:entry_id/resolve succeeds over real HTTP when Access is not configured (the un-provisioned default)', async () => {
  const env = makeEnv();
  await routeRequest(postJson('https://worker.example/generation_attempts', sampleAttempt()), env);
  await routeRequest(postJson('https://worker.example/owner_queue', sampleOwnerQueueEntry()), env);

  const resolveResponse = await routeRequest(
    postJson('https://worker.example/owner_queue/oq-router-1/resolve', {
      decision: 'approve_exact_hash', resolved_by: 'maurice', resolved_at: '2026-07-22T01:00:00Z',
    }),
    env,
  );
  assert.equal(resolveResponse.status, 200);

  const listResponse = await routeRequest(new Request('https://worker.example/owner_queue?status=resolved'), env);
  const body = await listResponse.json();
  assert.equal(body.entries.length, 1);
  assert.equal(body.entries[0].decision, 'approve_exact_hash');
});

test('POST /owner_queue/:entry_id/resolve is rejected with 401 when Access IS configured and no token is sent', async () => {
  const { publicJwk } = await generateTestKeypair();
  const env = makeEnv({ accessAudience: 'router-test-aud', jwksFetcher: fakeJwksFetcher(publicJwk) });
  await routeRequest(postJson('https://worker.example/generation_attempts', sampleAttempt()), env);
  await routeRequest(postJson('https://worker.example/owner_queue', sampleOwnerQueueEntry()), env);

  const resolveResponse = await routeRequest(
    postJson('https://worker.example/owner_queue/oq-router-1/resolve', {
      decision: 'approve_exact_hash', resolved_by: 'maurice', resolved_at: '2026-07-22T01:00:00Z',
    }),
    env,
  );
  assert.equal(resolveResponse.status, 401);

  // And the entry must still be pending -- a rejected Access check must
  // block the write, not just report an error after the fact.
  const listResponse = await routeRequest(new Request('https://worker.example/owner_queue'), env);
  const body = await listResponse.json();
  assert.equal(body.entries.length, 1);
});

test('POST /owner_queue/:entry_id/resolve succeeds when Access IS configured and a valid, matching-audience token is sent, and the JWT email overrides any client-claimed resolved_by', async () => {
  const { publicJwk, privateKey, kid } = await generateTestKeypair();
  const env = makeEnv({ accessAudience: 'router-test-aud', jwksFetcher: fakeJwksFetcher(publicJwk) });
  await routeRequest(postJson('https://worker.example/generation_attempts', sampleAttempt()), env);
  await routeRequest(postJson('https://worker.example/owner_queue', sampleOwnerQueueEntry()), env);

  const token = await signTestJwt(privateKey, kid, {
    aud: 'router-test-aud', email: 'maurice@example.com', exp: Math.floor(Date.now() / 1000) + 3600,
  });
  const resolveRequest = new Request('https://worker.example/owner_queue/oq-router-1/resolve', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'Cf-Access-Jwt-Assertion': token },
    // A client-supplied resolved_by claiming to be someone else -- the
    // Worker must ignore this and use the verified JWT's email instead
    // (see router.mjs's comment on the resolve handler for why).
    body: JSON.stringify({ decision: 'reject', resolved_by: 'someone-spoofing-maurice', resolved_at: '2026-07-22T01:00:00Z' }),
  });
  const resolveResponse = await routeRequest(resolveRequest, env);
  assert.equal(resolveResponse.status, 200);

  const listResponse = await routeRequest(new Request('https://worker.example/owner_queue?status=resolved'), env);
  const body = await listResponse.json();
  assert.equal(body.entries[0].resolved_by, 'maurice@example.com', 'resolved_by must come from the verified JWT, not the request body');
});

test('POST /owner_queue/:entry_id/resolve with an invalid decision option returns 400, not a database error', async () => {
  const env = makeEnv();
  await routeRequest(postJson('https://worker.example/generation_attempts', sampleAttempt()), env);
  await routeRequest(postJson('https://worker.example/owner_queue', sampleOwnerQueueEntry()), env);

  const resolveResponse = await routeRequest(
    postJson('https://worker.example/owner_queue/oq-router-1/resolve', {
      decision: 'not_a_real_option', resolved_by: 'maurice', resolved_at: '2026-07-22T01:00:00Z',
    }),
    env,
  );
  assert.equal(resolveResponse.status, 400);
});
