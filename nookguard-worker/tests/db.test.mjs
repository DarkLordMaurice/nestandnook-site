import test from 'node:test';
import assert from 'node:assert/strict';
import { createMigratedFakeD1 } from './fakeD1.mjs';
import {
  insertEvent, listEventsByRunId,
  insertGenerationAttempt, getGenerationAttempt,
  insertReview, listReviewsByCandidate,
} from '../src/db.mjs';

function sampleAttempt(overrides = {}) {
  return {
    candidate_sha256: 'cand-sha-1',
    asset_id: 'asset-1',
    spec_sha256: 'spec-sha-1',
    prompt_sha256: 'prompt-sha-1',
    generator_session_id: 'session-generator',
    artifact_uri: 'file:///quarantine/cand-sha-1.jpg',
    metadata_json: '{}',
    created_at: '2026-07-22T00:00:00Z',
    ...overrides,
  };
}

function sampleReview(overrides = {}) {
  return {
    review_id: 'review-1',
    candidate_sha256: 'cand-sha-1',
    review_stage: 'observe_a',
    reviewer_session_id: 'session-reviewer',
    context_bundle_sha256: 'ctx-sha-1',
    result_json: '{}',
    created_at: '2026-07-22T00:01:00Z',
    ...overrides,
  };
}

test('migration runs cleanly against real SQLite and creates all three tables', () => {
  const db = createMigratedFakeD1();
  const tables = db._sqlite.prepare(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
  ).all().map((r) => r.name);
  assert.deepEqual(tables, ['events', 'generation_attempts', 'reviews']);
});

test('insertEvent + listEventsByRunId: real round trip through real SQLite', async () => {
  const db = createMigratedFakeD1();
  const event = {
    event_id: 'evt-1', run_id: 'run-1', asset_id: 'asset-1', event_type: 'spec_locked',
    actor_role: 'planner', actor_session_id: 'session-planner',
    payload_json: '{"foo":"bar"}', payload_sha256: 'payload-sha-1', created_at: '2026-07-22T00:00:00Z',
  };
  const insertResult = await insertEvent(db, event);
  assert.equal(insertResult.ok, true);
  assert.equal(insertResult.status, 201);

  const listResult = await listEventsByRunId(db, 'run-1');
  assert.equal(listResult.ok, true);
  assert.equal(listResult.events.length, 1);
  assert.equal(listResult.events[0].event_id, 'evt-1');
  assert.equal(listResult.events[0].payload_sha256, 'payload-sha-1');
});

test('insertEvent: rejects a missing required field instead of silently inserting nulls', async () => {
  const db = createMigratedFakeD1();
  const result = await insertEvent(db, { event_id: 'evt-1' });
  assert.equal(result.ok, false);
  assert.equal(result.status, 400);
  assert.match(result.error, /run_id/);
});

test('insertGenerationAttempt + getGenerationAttempt: real round trip', async () => {
  const db = createMigratedFakeD1();
  const insertResult = await insertGenerationAttempt(db, sampleAttempt());
  assert.equal(insertResult.ok, true);

  const fetched = await getGenerationAttempt(db, 'cand-sha-1');
  assert.equal(fetched.ok, true);
  assert.equal(fetched.generation_attempt.generator_session_id, 'session-generator');
});

test('insertGenerationAttempt: rejects a duplicate candidate_sha256 (primary key)', async () => {
  const db = createMigratedFakeD1();
  await insertGenerationAttempt(db, sampleAttempt());
  const second = await insertGenerationAttempt(db, sampleAttempt());
  assert.equal(second.ok, false);
  assert.equal(second.status, 409);
  assert.match(second.error, /already registered/);
});

test('getGenerationAttempt: 404s for an unregistered candidate_sha256', async () => {
  const db = createMigratedFakeD1();
  const result = await getGenerationAttempt(db, 'does-not-exist');
  assert.equal(result.ok, false);
  assert.equal(result.status, 404);
});

test('insertReview: real round trip when reviewer differs from generator', async () => {
  const db = createMigratedFakeD1();
  await insertGenerationAttempt(db, sampleAttempt());
  const result = await insertReview(db, sampleReview());
  assert.equal(result.ok, true);
  assert.equal(result.status, 201);

  const listed = await listReviewsByCandidate(db, 'cand-sha-1');
  assert.equal(listed.reviews.length, 1);
  assert.equal(listed.reviews[0].reviewer_session_id, 'session-reviewer');
});

test('insertReview: rejects a reviewer session equal to the generator session -- Appendix H rule 1, end to end', async () => {
  const db = createMigratedFakeD1();
  await insertGenerationAttempt(db, sampleAttempt({ generator_session_id: 'same-session' }));
  const result = await insertReview(db, sampleReview({ reviewer_session_id: 'same-session' }));
  assert.equal(result.ok, false);
  assert.equal(result.status, 409);
  assert.match(result.error, /must differ/);

  const listed = await listReviewsByCandidate(db, 'cand-sha-1');
  assert.equal(listed.reviews.length, 0, 'the rejected review must not have been written');
});

test('insertReview: rejects a candidate_sha256 that has no matching generation_attempts row -- the foreign key, enforced in application code', async () => {
  const db = createMigratedFakeD1();
  const result = await insertReview(db, sampleReview({ candidate_sha256: 'never-registered' }));
  assert.equal(result.ok, false);
  assert.equal(result.status, 404);
  assert.match(result.error, /does not reference an existing generation_attempts row/);
});

test('insertReview: rejects a duplicate review_id', async () => {
  const db = createMigratedFakeD1();
  await insertGenerationAttempt(db, sampleAttempt());
  await insertReview(db, sampleReview());
  const second = await insertReview(db, sampleReview({ context_bundle_sha256: 'ctx-sha-2' }));
  assert.equal(second.ok, false);
  assert.equal(second.status, 409);
  assert.match(second.error, /already exists/);
});

test('listReviewsByCandidate: multiple review stages for the same candidate all come back', async () => {
  const db = createMigratedFakeD1();
  await insertGenerationAttempt(db, sampleAttempt());
  await insertReview(db, sampleReview({ review_id: 'review-a', review_stage: 'observe_a' }));
  await insertReview(db, sampleReview({ review_id: 'review-b', review_stage: 'observe_b', reviewer_session_id: 'session-reviewer-2' }));
  await insertReview(db, sampleReview({ review_id: 'review-c', review_stage: 'judge', reviewer_session_id: 'session-judge' }));

  const listed = await listReviewsByCandidate(db, 'cand-sha-1');
  assert.equal(listed.reviews.length, 3);
  const stages = listed.reviews.map((r) => r.review_stage).sort();
  assert.deepEqual(stages, ['judge', 'observe_a', 'observe_b']);
});
