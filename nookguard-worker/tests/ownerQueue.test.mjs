import test from 'node:test';
import assert from 'node:assert/strict';
import { createMigratedFakeD1 } from './fakeD1.mjs';
import { insertGenerationAttempt } from '../src/db.mjs';
import {
  enqueueOwnerDecision, listOwnerDecisions, getOwnerDecision, resolveOwnerDecision,
} from '../src/ownerQueue.mjs';

function sampleAttempt(overrides = {}) {
  return {
    candidate_sha256: 'cand-owner-1',
    asset_id: 'asset-1',
    spec_sha256: 'spec-sha-1',
    prompt_sha256: 'prompt-sha-1',
    generator_session_id: 'session-generator',
    artifact_uri: 'file:///quarantine/cand-owner-1.jpg',
    metadata_json: '{}',
    created_at: '2026-07-22T00:00:00Z',
    ...overrides,
  };
}

function sampleEntry(overrides = {}) {
  return {
    entry_id: 'oq-1',
    asset_id: 'asset-1',
    candidate_sha256: 'cand-owner-1',
    question: 'Approve this hero image for hub landing page X, exact hash abc123?',
    reasons: ['reviewer_disagreement'],
    risk_tier: 'tier_2',
    result_state: 'needs_owner',
    evidence: { candidate: 'cand-owner-1.jpg', reference: 'room-bible-office.jpg', literal_observations: ['a dresser is visible'] },
    queued_at: '2026-07-22T00:05:00Z',
    ...overrides,
  };
}

async function withRegisteredCandidate(db, attemptOverrides = {}) {
  await insertGenerationAttempt(db, sampleAttempt(attemptOverrides));
  return db;
}

test('enqueueOwnerDecision + listOwnerDecisions: real round trip, reasons/evidence come back as real objects not strings', async () => {
  const db = await withRegisteredCandidate(createMigratedFakeD1());
  const insertResult = await enqueueOwnerDecision(db, sampleEntry());
  assert.equal(insertResult.ok, true);
  assert.equal(insertResult.status, 201);

  const listed = await listOwnerDecisions(db, 'pending');
  assert.equal(listed.entries.length, 1);
  const entry = listed.entries[0];
  assert.equal(entry.status, 'pending');
  assert.deepEqual(entry.reasons, ['reviewer_disagreement']);
  assert.equal(entry.evidence.candidate, 'cand-owner-1.jpg');
  assert.equal(entry.consequences, null, 'unresolved entries have no consequences yet');
});

test('enqueueOwnerDecision: rejects a missing required field', async () => {
  const db = await withRegisteredCandidate(createMigratedFakeD1());
  const result = await enqueueOwnerDecision(db, sampleEntry({ question: undefined }));
  assert.equal(result.ok, false);
  assert.equal(result.status, 400);
  assert.match(result.error, /question/);
});

test('enqueueOwnerDecision: rejects a candidate_sha256 with no matching generation_attempts row', async () => {
  const db = createMigratedFakeD1(); // no candidate registered
  const result = await enqueueOwnerDecision(db, sampleEntry());
  assert.equal(result.ok, false);
  assert.equal(result.status, 404);
  assert.match(result.error, /does not reference an existing generation_attempts row/);
});

test('enqueueOwnerDecision: rejects a duplicate entry_id', async () => {
  const db = await withRegisteredCandidate(createMigratedFakeD1());
  await enqueueOwnerDecision(db, sampleEntry());
  const second = await enqueueOwnerDecision(db, sampleEntry());
  assert.equal(second.ok, false);
  assert.equal(second.status, 409);
});

test('listOwnerDecisions: defaults to pending only, "all" returns resolved entries too', async () => {
  const db = await withRegisteredCandidate(createMigratedFakeD1());
  await enqueueOwnerDecision(db, sampleEntry());
  await resolveOwnerDecision(db, {
    entry_id: 'oq-1', decision: 'approve_exact_hash', resolved_by: 'maurice', resolved_at: '2026-07-22T01:00:00Z',
  });

  const pending = await listOwnerDecisions(db, 'pending');
  assert.equal(pending.entries.length, 0);

  const resolved = await listOwnerDecisions(db, 'resolved');
  assert.equal(resolved.entries.length, 1);

  const all = await listOwnerDecisions(db, 'all');
  assert.equal(all.entries.length, 1);
});

test('resolveOwnerDecision: approve_exact_hash succeeds, records consequences, and getOwnerDecision reflects it', async () => {
  const db = await withRegisteredCandidate(createMigratedFakeD1());
  await enqueueOwnerDecision(db, sampleEntry());

  const result = await resolveOwnerDecision(db, {
    entry_id: 'oq-1', decision: 'approve_exact_hash', resolved_by: 'maurice',
    resolved_at: '2026-07-22T01:00:00Z', consequences: { site_change: 'hero image goes live on hub landing page X', override_permanence: 'permanent' },
  });
  assert.equal(result.ok, true);
  assert.equal(result.status, 200);

  const fetched = await getOwnerDecision(db, 'oq-1');
  assert.equal(fetched.entry.status, 'resolved');
  assert.equal(fetched.entry.decision, 'approve_exact_hash');
  assert.equal(fetched.entry.resolved_by, 'maurice');
  assert.equal(fetched.entry.consequences.override_permanence, 'permanent');
});

test('resolveOwnerDecision: rejects a decision outside the Appendix E five-option allow-list', async () => {
  const db = await withRegisteredCandidate(createMigratedFakeD1());
  await enqueueOwnerDecision(db, sampleEntry());
  const result = await resolveOwnerDecision(db, {
    entry_id: 'oq-1', decision: 'maybe_later', resolved_by: 'maurice', resolved_at: '2026-07-22T01:00:00Z',
  });
  assert.equal(result.ok, false);
  assert.equal(result.status, 400);
  assert.match(result.error, /must be one of/);
});

test('resolveOwnerDecision: 404s for an unknown entry_id', async () => {
  const db = await withRegisteredCandidate(createMigratedFakeD1());
  const result = await resolveOwnerDecision(db, {
    entry_id: 'does-not-exist', decision: 'defer', resolved_by: 'maurice', resolved_at: '2026-07-22T01:00:00Z',
  });
  assert.equal(result.ok, false);
  assert.equal(result.status, 404);
});

test('resolveOwnerDecision: rejects resolving an already-resolved entry a second time', async () => {
  const db = await withRegisteredCandidate(createMigratedFakeD1());
  await enqueueOwnerDecision(db, sampleEntry());
  await resolveOwnerDecision(db, {
    entry_id: 'oq-1', decision: 'defer', resolved_by: 'maurice', resolved_at: '2026-07-22T01:00:00Z',
  });
  const second = await resolveOwnerDecision(db, {
    entry_id: 'oq-1', decision: 'reject', resolved_by: 'maurice', resolved_at: '2026-07-22T02:00:00Z',
  });
  assert.equal(second.ok, false);
  assert.equal(second.status, 409);
  assert.match(second.error, /already resolved, not pending/);
});

test('resolveOwnerDecision: rejects missing required fields', async () => {
  const db = await withRegisteredCandidate(createMigratedFakeD1());
  await enqueueOwnerDecision(db, sampleEntry());
  const result = await resolveOwnerDecision(db, { entry_id: 'oq-1', decision: 'reject' });
  assert.equal(result.ok, false);
  assert.equal(result.status, 400);
});

test('all five Appendix E decision options are individually accepted', async () => {
  const options = ['approve_exact_hash', 'reject', 'revise_spec', 'regenerate', 'defer'];
  for (const [i, decision] of options.entries()) {
    const db = await withRegisteredCandidate(createMigratedFakeD1(), { candidate_sha256: `cand-opt-${i}` });
    await enqueueOwnerDecision(db, sampleEntry({ entry_id: `oq-opt-${i}`, candidate_sha256: `cand-opt-${i}` }));
    const result = await resolveOwnerDecision(db, {
      entry_id: `oq-opt-${i}`, decision, resolved_by: 'maurice', resolved_at: '2026-07-22T01:00:00Z',
    });
    assert.equal(result.ok, true, `decision '${decision}' should be accepted`);
  }
});
