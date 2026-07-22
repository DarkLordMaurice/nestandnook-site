// Data-access functions for the owner_queue table (migrations/
// 0002_owner_queue.sql, Appendix E "Owner Decision Packet"). Same
// dependency-injection pattern as db.mjs: every function takes a D1-shaped
// `db` as its first argument, so the same code runs against the real
// Cloudflare D1 binding and against tests/fakeD1.mjs.
//
// This is the table the dashboard (nookguard-dashboard/, this same commit)
// actually reads and writes -- Appendix J's operational runbook: "Maurice
// can see and resolve only the owner queue from the private dashboard."

import { getGenerationAttempt } from './db.mjs';
import { isValidOwnerDecisionOption, OWNER_DECISION_OPTIONS } from './enforce.mjs';

function missingFields(obj, fields) {
  return fields.filter((f) => obj[f] === undefined || obj[f] === null || obj[f] === '');
}

function rowToEntry(row) {
  return {
    ...row,
    reasons: JSON.parse(row.reasons_json),
    evidence: JSON.parse(row.evidence_json),
    consequences: row.consequences_json ? JSON.parse(row.consequences_json) : null,
  };
}

const ENQUEUE_FIELDS = [
  'entry_id', 'asset_id', 'candidate_sha256', 'question', 'reasons', 'risk_tier',
  'result_state', 'evidence', 'queued_at',
];

/**
 * Appendix E's Question/Asset-requirement/Why-stopped/Evidence rows,
 * persisted at enqueue time. `reasons` and `evidence` are plain JS
 * values (array / object) here -- this function owns the JSON encoding,
 * callers never hand-serialize.
 */
export async function enqueueOwnerDecision(db, entry) {
  const missing = missingFields(entry, ENQUEUE_FIELDS);
  if (missing.length > 0) {
    return { ok: false, status: 400, error: `missing required field(s): ${missing.join(', ')}` };
  }

  const attemptResult = await getGenerationAttempt(db, entry.candidate_sha256);
  if (!attemptResult.ok) {
    return {
      ok: false, status: 404,
      error: `owner_queue.candidate_sha256 does not reference an existing generation_attempts row: ${entry.candidate_sha256}`,
    };
  }

  const existing = await db.prepare('SELECT entry_id FROM owner_queue WHERE entry_id = ?')
    .bind(entry.entry_id).first();
  if (existing) {
    return { ok: false, status: 409, error: `entry_id ${entry.entry_id} already exists` };
  }

  const result = await db.prepare(
    `INSERT INTO owner_queue
      (entry_id, asset_id, candidate_sha256, requirement_id, question, reasons_json, risk_tier,
       result_state, evidence_json, status, decision, consequences_json, queued_at, resolved_at, resolved_by)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, NULL, NULL)`,
  ).bind(
    entry.entry_id, entry.asset_id, entry.candidate_sha256, entry.requirement_id ?? null, entry.question,
    JSON.stringify(entry.reasons), entry.risk_tier, entry.result_state, JSON.stringify(entry.evidence),
    entry.queued_at,
  ).run();

  if (!result.success) {
    return { ok: false, status: 409, error: `could not insert owner_queue entry: ${result.error ?? 'unknown error'}` };
  }
  return { ok: true, status: 201, entry_id: entry.entry_id };
}

/** status: 'pending' (default) | 'resolved' | 'all'. */
export async function listOwnerDecisions(db, status = 'pending') {
  const stmt = status === 'all'
    ? db.prepare('SELECT * FROM owner_queue ORDER BY queued_at ASC')
    : db.prepare('SELECT * FROM owner_queue WHERE status = ? ORDER BY queued_at ASC').bind(status);
  const result = await stmt.all();
  return { ok: true, status: 200, entries: result.results.map(rowToEntry) };
}

export async function getOwnerDecision(db, entryId) {
  const row = await db.prepare('SELECT * FROM owner_queue WHERE entry_id = ?').bind(entryId).first();
  if (!row) {
    return { ok: false, status: 404, error: `no owner_queue entry for ${entryId}` };
  }
  return { ok: true, status: 200, entry: rowToEntry(row) };
}

/**
 * Appendix E's Options/Consequences rows. Resolves a pending entry with
 * one of the five allowed decisions (enforce.mjs's
 * isValidOwnerDecisionOption) and records what actually changed
 * (`consequences`, a plain object -- e.g. { site_change: '...',
 * override_permanence: 'permanent' | 'temporary' }). Rejects resolving an
 * already-resolved entry (409) -- a decision packet is meant to be acted
 * on once, matching the same "no fix in place, no silent re-decision"
 * philosophy as section 27's generation rules.
 */
export async function resolveOwnerDecision(db, { entry_id: entryId, decision, resolved_by: resolvedBy, resolved_at: resolvedAt, consequences }) {
  if (!entryId || !decision || !resolvedBy || !resolvedAt) {
    return { ok: false, status: 400, error: 'entry_id, decision, resolved_by, and resolved_at are all required' };
  }
  if (!isValidOwnerDecisionOption(decision)) {
    return {
      ok: false, status: 400,
      error: `decision must be one of: ${OWNER_DECISION_OPTIONS.join(', ')}`,
    };
  }

  const existing = await getOwnerDecision(db, entryId);
  if (!existing.ok) return existing;
  if (existing.entry.status !== 'pending') {
    return { ok: false, status: 409, error: `owner_queue entry ${entryId} is already ${existing.entry.status}, not pending` };
  }

  const result = await db.prepare(
    `UPDATE owner_queue
     SET status = 'resolved', decision = ?, resolved_by = ?, resolved_at = ?, consequences_json = ?
     WHERE entry_id = ?`,
  ).bind(decision, resolvedBy, resolvedAt, JSON.stringify(consequences ?? {}), entryId).run();

  if (!result.success) {
    return { ok: false, status: 409, error: `could not resolve owner_queue entry: ${result.error ?? 'unknown error'}` };
  }
  return { ok: true, status: 200, entry_id: entryId, decision };
}
