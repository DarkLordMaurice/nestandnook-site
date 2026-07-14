import { test } from 'node:test';
import assert from 'node:assert/strict';
import { QUESTIONS, TYPES, scoreQuiz, validateQuizAnswers } from '../../src/lib/tools/your-small-space-personality.mjs';

test('QUESTIONS contains exactly 6 questions', () => {
  assert.equal(QUESTIONS.length, 6);
});

test('every question has 4 options', () => {
  for (const q of QUESTIONS) {
    assert.equal(q.options.length, 4, `Question ${q.id} should have 4 options`);
  }
});

test('every question option covers all 4 types', () => {
  const typeKeys = ['nester', 'starter', 'fixer', 'optimizer'];
  for (const q of QUESTIONS) {
    const values = q.options.map((o) => o.value);
    for (const key of typeKeys) {
      assert.ok(values.includes(key), `Question ${q.id} missing option for type: ${key}`);
    }
  }
});

test('TYPES has all 4 personality types with required fields', () => {
  const required = ['id', 'name', 'mirror', 'superpower', 'kryptonite', 'winnieSays', 'shareHook', 'ctaLabel', 'ctaHref'];
  for (const [key, type] of Object.entries(TYPES)) {
    for (const field of required) {
      assert.ok(type[field], `Type ${key} missing field: ${field}`);
    }
  }
});

test('scoreQuiz returns nester when all answers are nester', () => {
  const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, 'nester']));
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'nester');
  assert.equal(result.isTie, false);
});

test('scoreQuiz returns optimizer when all answers are optimizer', () => {
  const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, 'optimizer']));
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'optimizer');
});

test('scoreQuiz detects a tie', () => {
  // 3 nester, 3 starter
  const answers = { q1: 'nester', q2: 'nester', q3: 'nester', q4: 'starter', q5: 'starter', q6: 'starter' };
  const result = scoreQuiz(answers);
  assert.equal(result.isTie, true);
  assert.ok(result.tiedWith.length > 0);
});

test('scoreQuiz picks the most frequent type when clear winner', () => {
  const answers = { q1: 'fixer', q2: 'fixer', q3: 'fixer', q4: 'nester', q5: 'starter', q6: 'optimizer' };
  const result = scoreQuiz(answers);
  assert.equal(result.type.id, 'fixer');
  assert.equal(result.tally.fixer, 3);
});

test('validateQuizAnswers returns empty array when all answered', () => {
  const answers = Object.fromEntries(QUESTIONS.map((q) => [q.id, 'nester']));
  assert.deepEqual(validateQuizAnswers(answers), []);
});

test('validateQuizAnswers flags missing answers', () => {
  const errors = validateQuizAnswers({ q1: 'nester' });
  assert.equal(errors.length, 5);
});
