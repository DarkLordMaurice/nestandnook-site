import { test } from 'node:test';
import assert from 'node:assert/strict';
import { QUESTIONS, TYPES, scoreQuiz, validateQuizAnswers } from '../../src/lib/tools/regret-proof-purchase-check.mjs';

const TYPE_KEYS = ['buy', 'wait', 'skip'];

test('QUESTIONS contains exactly 6 questions', () => {
  assert.equal(QUESTIONS.length, 6);
});

test('every question has 3 options', () => {
  for (const q of QUESTIONS) {
    assert.equal(q.options.length, 3, `Question ${q.id} should have 3 options`);
  }
});

test('every question option covers all 3 verdicts', () => {
  for (const q of QUESTIONS) {
    const values = q.options.map((o) => o.value);
    for (const key of TYPE_KEYS) {
      assert.ok(values.includes(key), `Question ${q.id} missing option for verdict: ${key}`);
    }
  }
});

test('TYPES has all 3 verdicts with required fields', () => {
  const required = ['id', 'name', 'mirror', 'superpower', 'kryptonite', 'winnieSays', 'shareHook', 'ctaLabel', 'ctaHref', 'shareBody'];
  for (const [key, type] of Object.entries(TYPES)) {
    for (const field of required) {
      assert.ok(type[field], `Type ${key} missing field: ${field}`);
    }
  }
});

test('scoreQuiz returns buy when all answers are buy', () => {
  const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, 'buy']));
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'buy');
  assert.equal(result.isTie, false);
});

test('scoreQuiz returns skip when all answers are skip', () => {
  const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, 'skip']));
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'skip');
});

test('scoreQuiz detects a tie', () => {
  const answers = { q1: 'buy', q2: 'buy', q3: 'buy', q4: 'skip', q5: 'skip', q6: 'skip' };
  const result = scoreQuiz(answers);
  assert.equal(result.isTie, true);
  assert.ok(result.tiedWith.length > 0);
});

test('scoreQuiz defaults to wait on a true 3-way tie (safety default, not buy)', () => {
  const answers = { q1: 'buy', q2: 'wait', q3: 'skip' };
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'wait');
  assert.equal(result.isTie, true);
});

test('scoreQuiz picks the most frequent verdict when clear winner', () => {
  const answers = { q1: 'wait', q2: 'wait', q3: 'wait', q4: 'buy', q5: 'skip', q6: 'buy' };
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'wait');
  assert.equal(result.tally.wait, 3);
});

test('validateQuizAnswers returns empty array when all answered', () => {
  const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, 'buy']));
  assert.deepEqual(validateQuizAnswers(answers), []);
});

test('validateQuizAnswers flags missing answers', () => {
  const errors = validateQuizAnswers({ q1: 'buy' });
  assert.equal(errors.length, 5);
});
