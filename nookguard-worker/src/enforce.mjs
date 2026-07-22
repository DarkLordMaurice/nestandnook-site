// Pure policy functions implementing Appendix H's "Enforce in Worker
// transaction" comment (migrations/0001_init.sql, bottom). Pure and
// dependency-free by design, mirroring nookguard/hooks.py's pattern on the
// Python side (Commit 11 BUILD-LOG): policy decisions live in small
// functions with no I/O, so they're trivially unit-testable and the
// HTTP-facing router (src/router.mjs) is the only place that has to deal
// with request parsing, D1 access, and status codes.

/**
 * Appendix H, rule 1: "reviewer_session_id != generation_attempt.
 * generator_session_id". A reviewer session can never be the same session
 * that generated the candidate it's reviewing -- the Worker-level twin of
 * spec section 27's "No generator review" rule (the generation session may
 * report tool errors but cannot submit quality evidence about its own
 * output).
 */
export function reviewerSessionDiffersFromGenerator(reviewerSessionId, generatorSessionId) {
  if (!reviewerSessionId || !generatorSessionId) {
    return { ok: false, reason: 'reviewer_session_id and generator_session_id are both required' };
  }
  if (reviewerSessionId === generatorSessionId) {
    return {
      ok: false,
      reason: `reviewer_session_id (${reviewerSessionId}) must differ from the generation `
        + `attempt's generator_session_id`,
    };
  }
  return { ok: true };
}

// States nookguard/state_machine.py's AssetState enum (Python, Commit 2)
// treats as a legitimate release-eligible pass -- either the judge/
// aggregator passed the candidate outright (SEMANTIC_PASS) or an owner
// explicitly approved it after a NEEDS_OWNER stop (OWNER_APPROVED). Kept
// as plain string literals here rather than importing the Python enum
// (there is no cross-language import path) -- if state_machine.py's
// values ever change, this constant and PYTHON_ASSET_STATES_REFERENCE at
// the bottom of this file both need updating together.
const PASS_STATES = new Set(['semantic_pass', 'owner_approved']);

/**
 * Appendix H, rule 2: "approval candidate SHA must have required review
 * stages and computed policy PASS". This does NOT recompute the semantic
 * aggregation policy table itself -- that stays nookguard/aggregator.py's
 * job (Commit 8); duplicating a second, JS-language copy of the policy
 * table here would be exactly the "redesign the architecture around
 * convenience" Appendix M forbids. What this checks is the Worker-level
 * invariant on top of that already-computed result: an approval write must
 * name every required review stage, and must cite an aggregator verdict
 * that is actually one of the real pass states above -- not re-derive one.
 */
export function requiredStagesPresentAndPolicyPass(reviewStages, requiredStages, aggregatorState) {
  const missing = requiredStages.filter((stage) => !reviewStages.includes(stage));
  if (missing.length > 0) {
    return { ok: false, reason: `missing required review stage(s): ${missing.join(', ')}` };
  }
  if (!PASS_STATES.has(aggregatorState)) {
    return { ok: false, reason: `aggregator state '${aggregatorState}' is not a pass state` };
  }
  return { ok: true };
}

// See the comment on PASS_STATES above -- kept here as an explicit,
// greppable cross-reference so a future edit to either side is easy to
// find, not because this file imports it.
export const PYTHON_ASSET_STATES_REFERENCE = 'nookguard/state_machine.py:AssetState';
