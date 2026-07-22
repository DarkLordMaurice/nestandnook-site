import test from 'node:test';
import assert from 'node:assert/strict';
import { createMigratedFakeD1 } from './fakeD1.mjs';
import { routeRequest } from '../src/router.mjs';

// Real Request/Response objects (global in Node 22+) round-tripped through
// routeRequest -- this is the same object shape Cloudflare passes into
// `fetch(request, env)` in production; only `env.DB` (here, the fakeD1
// instance) differs from a real deployment.

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
  const db = createMigratedFakeD1();
  const event = {
    event_id: 'evt-router-1', run_id: 'run-router-1', event_type: 'spec_locked', actor_role: 'planner',
    payload_json: '{}', payload_sha256: 'payload-sha', created_at: '2026-07-22T00:00:00Z',
  };
  const postResponse = await routeRequest(postJson('https://worker.example/events', event), db);
  assert.equal(postResponse.status, 201);
  const postBody = await postResponse.json();
  assert.equal(postBody.ok, true);

  const getResponse = await routeRequest(new Request('https://worker.example/events?run_id=run-router-1'), db);
  assert.equal(getResponse.status, 200);
  const getBody = await getResponse.json();
  assert.equal(getBody.events.length, 1);
  assert.equal(getBody.events[0].event_id, 'evt-router-1');
});

test('GET /events without run_id returns 400, not a database error', async () => {
  const db = createMigratedFakeD1();
  const response = await routeRequest(new Request('https://worker.example/events'), db);
  assert.equal(response.status, 400);
});

test('POST /generation_attempts then GET /generation_attempts/:sha round trips', async () => {
  const db = createMigratedFakeD1();
  const postResponse = await routeRequest(
    postJson('https://worker.example/generation_attempts', sampleAttempt()), db,
  );
  assert.equal(postResponse.status, 201);

  const getResponse = await routeRequest(
    new Request('https://worker.example/generation_attempts/cand-router-1'), db,
  );
  assert.equal(getResponse.status, 200);
  const body = await getResponse.json();
  assert.equal(body.generation_attempt.candidate_sha256, 'cand-router-1');
});

test('GET /generation_attempts/:sha 404s for an unknown candidate', async () => {
  const db = createMigratedFakeD1();
  const response = await routeRequest(new Request('https://worker.example/generation_attempts/nope'), db);
  assert.equal(response.status, 404);
});

test('POST /reviews with reviewer_session_id equal to the generator is rejected over real HTTP, end to end', async () => {
  const db = createMigratedFakeD1();
  await routeRequest(
    postJson('https://worker.example/generation_attempts', sampleAttempt({ generator_session_id: 'same-session' })),
    db,
  );
  const reviewResponse = await routeRequest(
    postJson('https://worker.example/reviews', {
      review_id: 'review-router-1', candidate_sha256: 'cand-router-1', review_stage: 'observe_a',
      reviewer_session_id: 'same-session', context_bundle_sha256: 'ctx-sha', result_json: '{}',
      created_at: '2026-07-22T00:01:00Z',
    }),
    db,
  );
  assert.equal(reviewResponse.status, 409);
  const body = await reviewResponse.json();
  assert.match(body.error, /must differ/);
});

test('POST /reviews with a valid distinct reviewer session succeeds, then GET /reviews lists it', async () => {
  const db = createMigratedFakeD1();
  await routeRequest(postJson('https://worker.example/generation_attempts', sampleAttempt()), db);
  const reviewResponse = await routeRequest(
    postJson('https://worker.example/reviews', {
      review_id: 'review-router-2', candidate_sha256: 'cand-router-1', review_stage: 'observe_a',
      reviewer_session_id: 'session-reviewer', context_bundle_sha256: 'ctx-sha', result_json: '{}',
      created_at: '2026-07-22T00:01:00Z',
    }),
    db,
  );
  assert.equal(reviewResponse.status, 201);

  const listResponse = await routeRequest(
    new Request('https://worker.example/reviews?candidate_sha256=cand-router-1'), db,
  );
  assert.equal(listResponse.status, 200);
  const body = await listResponse.json();
  assert.equal(body.reviews.length, 1);
});

test('malformed JSON body returns 400, not an unhandled exception', async () => {
  const db = createMigratedFakeD1();
  const badRequest = new Request('https://worker.example/events', {
    method: 'POST', body: '{not valid json', headers: { 'content-type': 'application/json' },
  });
  const response = await routeRequest(badRequest, db);
  assert.equal(response.status, 400);
});

test('unknown route returns 404 with a descriptive error, not a crash', async () => {
  const db = createMigratedFakeD1();
  const response = await routeRequest(new Request('https://worker.example/does-not-exist'), db);
  assert.equal(response.status, 404);
  const body = await response.json();
  assert.match(body.error, /no route/);
});
