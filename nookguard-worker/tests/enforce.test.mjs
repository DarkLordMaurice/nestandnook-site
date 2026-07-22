import test from 'node:test';
import assert from 'node:assert/strict';
import {
  reviewerSessionDiffersFromGenerator, requiredStagesPresentAndPolicyPass,
  isValidOwnerDecisionOption, OWNER_DECISION_OPTIONS,
} from '../src/enforce.mjs';

test('reviewerSessionDiffersFromGenerator: rejects a reviewer session identical to the generator session', () => {
  const result = reviewerSessionDiffersFromGenerator('session-abc', 'session-abc');
  assert.equal(result.ok, false);
  assert.match(result.reason, /must differ/);
});

test('reviewerSessionDiffersFromGenerator: allows a reviewer session that differs from the generator session', () => {
  const result = reviewerSessionDiffersFromGenerator('session-reviewer', 'session-generator');
  assert.equal(result.ok, true);
});

test('reviewerSessionDiffersFromGenerator: rejects when either session id is missing', () => {
  assert.equal(reviewerSessionDiffersFromGenerator('', 'session-generator').ok, false);
  assert.equal(reviewerSessionDiffersFromGenerator('session-reviewer', '').ok, false);
  assert.equal(reviewerSessionDiffersFromGenerator(null, null).ok, false);
});

test('requiredStagesPresentAndPolicyPass: passes when all required stages are present and state is semantic_pass', () => {
  const result = requiredStagesPresentAndPolicyPass(
    ['observe_a', 'observe_b', 'judge'], ['observe_a', 'observe_b', 'judge'], 'semantic_pass',
  );
  assert.equal(result.ok, true);
});

test('requiredStagesPresentAndPolicyPass: passes on owner_approved (the NEEDS_OWNER escape hatch), not just semantic_pass', () => {
  const result = requiredStagesPresentAndPolicyPass(
    ['observe_a', 'observe_b', 'judge'], ['observe_a', 'observe_b', 'judge'], 'owner_approved',
  );
  assert.equal(result.ok, true);
});

test('requiredStagesPresentAndPolicyPass: rejects when a required review stage is missing', () => {
  const result = requiredStagesPresentAndPolicyPass(
    ['observe_a', 'judge'], ['observe_a', 'observe_b', 'judge'], 'semantic_pass',
  );
  assert.equal(result.ok, false);
  assert.match(result.reason, /observe_b/);
});

test('requiredStagesPresentAndPolicyPass: rejects a non-pass aggregator state even with all stages present', () => {
  const result = requiredStagesPresentAndPolicyPass(
    ['observe_a', 'observe_b', 'judge'], ['observe_a', 'observe_b', 'judge'], 'semantic_fail',
  );
  assert.equal(result.ok, false);
  assert.match(result.reason, /semantic_fail/);
});

test('requiredStagesPresentAndPolicyPass: rejects needs_owner as a bare pass (it must become owner_approved first)', () => {
  const result = requiredStagesPresentAndPolicyPass(
    ['observe_a', 'observe_b', 'judge'], ['observe_a', 'observe_b', 'judge'], 'needs_owner',
  );
  assert.equal(result.ok, false);
});

test('isValidOwnerDecisionOption: accepts exactly the five Appendix E options', () => {
  assert.equal(OWNER_DECISION_OPTIONS.length, 5);
  for (const option of OWNER_DECISION_OPTIONS) {
    assert.equal(isValidOwnerDecisionOption(option), true, `'${option}' should be valid`);
  }
});

test('isValidOwnerDecisionOption: rejects anything outside the closed set, including near-misses', () => {
  assert.equal(isValidOwnerDecisionOption('approved'), false, 'the Python owner_queue.py legacy value is not one of the five Appendix E options');
  assert.equal(isValidOwnerDecisionOption('approve'), false);
  assert.equal(isValidOwnerDecisionOption(''), false);
  assert.equal(isValidOwnerDecisionOption(undefined), false);
  assert.equal(isValidOwnerDecisionOption('APPROVE_EXACT_HASH'), false, 'case-sensitive, matching the rest of this codebase\'s lowercase-enum convention');
});
