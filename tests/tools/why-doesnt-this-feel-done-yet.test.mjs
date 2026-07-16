import { test } from 'node:test';
import assert from 'node:assert/strict';
import { QUESTIONS, TYPES, scoreQuiz, validateQuizAnswers } from '../../src/lib/tools/why-doesnt-this-feel-done-yet.mjs';

const TYPE_KEYS = ['missing-anchor', 'function-friction', 'stalled-project', 'comparison-trap'];

test('QUESTIONS contains exactly 5 questions', () => {
  assert.equal(QUESTIONS.length, 5);
});

test('every question has 4 options', () => {
  for (const q of QUESTIONS) {
    assert.equal(q.options.length, 4, `Question ${q.id} should have 4 options`);
  }
});

test('every question option covers all 4 types', () => {
  for (const q of QUESTIONS) {
    const values = q.options.map((o) => o.value);
    for (const key of TYPE_KEYS) {
      assert.ok(values.includes(key), `Question ${q.id} missing option for type: ${key}`);
    }
  }
});

test('TYPES has all 4 diagnosis types with required fields', () => {
  const required = ['id', 'name', 'mirror', 'superpower', 'kryptonite', 'winnieSays', 'shareHook', 'ctaLabel', 'ctaHref', 'shareBody'];
  for (const [key, type] of Object.entries(TYPES)) {
    for (const field of required) {
      assert.ok(type[field], `Type ${key} missing field: ${field}`);
    }
  }
});

test('scoreQuiz returns missing-anchor when all answers are missing-anchor', () => {
  const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, 'missing-anchor']));
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'missing-anchor');
  assert.equal(result.isTie, false);
});

test('scoreQuiz returns comparison-trap when all answers are comparison-trap', () => {
  const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, 'comparison-trap']));
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'comparison-trap');
});

test('scoreQuiz detects a tie', () => {
  const answers = { q1: 'function-friction', q2: 'function-friction', q3: 'stalled-project', q4: 'stalled-project', q5: 'missing-anchor' };
  const result = scoreQuiz(answers);
  assert.equal(result.isTie, true);
  assert.ok(result.tiedWith.length > 0);
});

test('scoreQuiz picks the most frequent type when clear winner', () => {
  const answers = { q1: 'stalled-project', q2: 'stalled-project', q3: 'stalled-project', q4: 'missing-anchor', q5: 'comparison-trap' };
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'stalled-project');
  assert.equal(result.tally['stalled-project'], 3);
});

test('validateQuizAnswers returns empty array when all answered', () => {
  const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, 'missing-anchor']));
  assert.deepEqual(validateQuizAnswers(answers), []);
});

test('validateQuizAnswers flags missing answers', () => {
  const errors = validateQuizAnswers({ q1: 'missing-anchor' });
  assert.equal(errors.length, 4);
});
