// Data-access functions for the three tables in migrations/0001_init.sql.
// Every function here takes a D1-shaped `db` as its first argument
// (dependency injection, matching the pattern used throughout the Python
// side of NookGuard -- see e.g. nookguard/production_verifier.py's
// `fetcher` parameter) so the exact same code runs against the real
// Cloudflare D1 binding in production and against tests/fakeD1.mjs's real-
// SQLite shim in tests. Nothing in this file is aware it might be running
// against a fake.

import { reviewerSessionDiffersFromGenerator } from './enforce.mjs';

function missingFields(obj, fields) {
  return fields.filter((f) => obj[f] === undefined || obj[f] === null || obj[f] === '');
}

const EVENT_FIELDS = [
  'event_id', 'run_id', 'event_type', 'actor_role', 'payload_json', 'payload_sha256', 'created_at',
];

/** Insert one row into events. asset_id and actor_session_id are nullable per Appendix H. */
export async function insertEvent(db, event) {
  const missing = missingFields(event, EVENT_FIELDS);
  if (missing.length > 0) {
    return { ok: false, status: 400, error: `missing required field(s): ${missing.join(', ')}` };
  }
  const result = await db.prepare(
    `INSERT INTO events
      (event_id, run_id, asset_id, event_type, actor_role, actor_session_id, payload_json, payload_sha256, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    event.event_id, event.run_id, event.asset_id ?? null, event.event_type, event.actor_role,
    event.actor_session_id ?? null, event.payload_json, event.payload_sha256, event.created_at,
  ).run();

  if (!result.success) {
    return { ok: false, status: 409, error: `could not insert event: ${result.error ?? 'unknown error'}` };
  }
  return { ok: true, status: 201, event_id: event.event_id };
}

export async function listEventsByRunId(db, runId) {
  const result = await db.prepare('SELECT * FROM events WHERE run_id = ? ORDER BY created_at ASC').bind(runId).all();
  return { ok: true, status: 200, events: result.results };
}

const GENERATION_ATTEMPT_FIELDS = [
  'candidate_sha256', 'asset_id', 'spec_sha256', 'prompt_sha256',
  'generator_session_id', 'artifact_uri', 'metadata_json', 'created_at',
];

/** Insert one row into generation_attempts. Rejects a duplicate candidate_sha256 (primary key). */
export async function insertGenerationAttempt(db, attempt) {
  const missing = missingFields(attempt, GENERATION_ATTEMPT_FIELDS);
  if (missing.length > 0) {
    return { ok: false, status: 400, error: `missing required field(s): ${missing.join(', ')}` };
  }
  const existing = await db.prepare('SELECT candidate_sha256 FROM generation_attempts WHERE candidate_sha256 = ?')
    .bind(attempt.candidate_sha256).first();
  if (existing) {
    return { ok: false, status: 409, error: `candidate_sha256 ${attempt.candidate_sha256} is already registered` };
  }
  const result = await db.prepare(
    `INSERT INTO generation_attempts
      (candidate_sha256, asset_id, spec_sha256, prompt_sha256, generator_session_id, artifact_uri, metadata_json, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    attempt.candidate_sha256, attempt.asset_id, attempt.spec_sha256, attempt.prompt_sha256,
    attempt.generator_session_id, attempt.artifact_uri, attempt.metadata_json, attempt.created_at,
  ).run();

  if (!result.success) {
    return { ok: false, status: 409, error: `could not insert generation_attempt: ${result.error ?? 'unknown error'}` };
  }
  return { ok: true, status: 201, candidate_sha256: attempt.candidate_sha256 };
}

export async function getGenerationAttempt(db, candidateSha256) {
  const row = await db.prepare('SELECT * FROM generation_attempts WHERE candidate_sha256 = ?')
    .bind(candidateSha256).first();
  if (!row) {
    return { ok: false, status: 404, error: `no generation_attempt registered for ${candidateSha256}` };
  }
  return { ok: true, status: 200, generation_attempt: row };
}

const REVIEW_FIELDS = [
  'review_id', 'candidate_sha256', 'review_stage', 'reviewer_session_id', 'context_bundle_sha256',
  'result_json', 'created_at',
];

/**
 * Insert one row into reviews. Enforces both real invariants before
 * touching the database: the candidate_sha256 foreign key must resolve to
 * a real generation_attempts row (Appendix H's FOREIGN KEY), and the
 * reviewer session must differ from that row's generator_session_id
 * (Appendix H's "Enforce in Worker transaction" rule 1, see
 * src/enforce.mjs). Both checks run before the INSERT, not as a
 * database-level trigger -- see the comment in migrations/0001_init.sql
 * for why.
 */
export async function insertReview(db, review) {
  const missing = missingFields(review, REVIEW_FIELDS);
  if (missing.length > 0) {
    return { ok: false, status: 400, error: `missing required field(s): ${missing.join(', ')}` };
  }

  const attemptResult = await getGenerationAttempt(db, review.candidate_sha256);
  if (!attemptResult.ok) {
    return {
      ok: false, status: 404,
      error: `reviews.candidate_sha256 does not reference an existing generation_attempts row: ${review.candidate_sha256}`,
    };
  }

  const policy = reviewerSessionDiffersFromGenerator(
    review.reviewer_session_id,
    attemptResult.generation_attempt.generator_session_id,
  );
  if (!policy.ok) {
    return { ok: false, status: 409, error: policy.reason };
  }

  const existing = await db.prepare('SELECT review_id FROM reviews WHERE review_id = ?')
    .bind(review.review_id).first();
  if (existing) {
    return { ok: false, status: 409, error: `review_id ${review.review_id} already exists` };
  }

  const result = await db.prepare(
    `INSERT INTO reviews
      (review_id, candidate_sha256, review_stage, reviewer_session_id, context_bundle_sha256, result_json, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    review.review_id, review.candidate_sha256, review.review_stage, review.reviewer_session_id,
    review.context_bundle_sha256, review.result_json, review.created_at,
  ).run();

  if (!result.success) {
    return { ok: false, status: 409, error: `could not insert review: ${result.error ?? 'unknown error'}` };
  }
  return { ok: true, status: 201, review_id: review.review_id };
}

export async function listReviewsByCandidate(db, candidateSha256) {
  const result = await db.prepare('SELECT * FROM reviews WHERE candidate_sha256 = ? ORDER BY created_at ASC')
    .bind(candidateSha256).all();
  return { ok: true, status: 200, reviews: result.results };
}
