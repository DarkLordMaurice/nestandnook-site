import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CONFESSIONS, TYPES, scoreRoast, validateRoastAnswers } from '../../src/lib/tools/roast-my-space.mjs';

const TYPE_KEYS = ['clutter-monarch', 'serial-starter', 'cozy-chaos', 'stealth-perfectionist'];

test('CONFESSIONS contains exactly 12 confessions', () => {
  assert.equal(CONFESSIONS.length, 12);
});

test('every confession maps to a known type', () => {
  for (const c of CONFESSIONS) {
    assert.ok(TYPE_KEYS.includes(c.type), `Confession ${c.id} has unknown type: ${c.type}`);
  }
});

test('each of the 4 types has exactly 3 confessions', () => {
  for (const key of TYPE_KEYS) {
    const count = CONFESSIONS.filter((c) => c.type === key).length;
    assert.equal(count, 3, `Type ${key} should have 3 confessions`);
  }
});

test('TYPES has all 4 roast types with required fields', () => {
  const required = ['id', 'name', 'roastLine', 'realTalk', 'winnieSays', 'shareHook', 'ctaLabel', 'ctaHref', 'shareBody'];
  for (const [key, type] of Object.entries(TYPES)) {
    for (const field of required) {
      assert.ok(type[field], `Type ${key} missing field: ${field}`);
    }
  }
});

test('scoreRoast returns clutter-monarch when only clutter-monarch confessions are checked', () => {
  const ids = CONFESSIONS.filter((c) => c.type === 'clutter-monarch').map((c) => c.id);
  const result = scoreRoast(ids);
  assert.equal(result.type.id, 'clutter-monarch');
  assert.equal(result.isTie, false);
});

test('scoreRoast returns stealth-perfectionist when only those confessions are checked', () => {
  const ids = CONFESSIONS.filter((c) => c.type === 'stealth-perfectionist').map((c) => c.id);
  const result = scoreRoast(ids);
  assert.equal(result.type.id, 'stealth-perfectionist');
});

test('scoreRoast detects a tie between two equally-checked types', () => {
  const ids = [
    ...CONFESSIONS.filter((c) => c.type === 'cozy-chaos').map((c) => c.id),
    ...CONFESSIONS.filter((c) => c.type === 'serial-starter').map((c) => c.id),
  ];
  const result = scoreRoast(ids);
  assert.equal(result.isTie, true);
  assert.ok(result.tiedWith.length > 0);
});

test('scoreRoast picks the most-checked type when there is a clear winner', () => {
  const clutterIds = CONFESSIONS.filter((c) => c.type === 'clutter-monarch').map((c) => c.id);
  const oneCozy = CONFESSIONS.find((c) => c.type === 'cozy-chaos').id;
  const result = scoreRoast([...clutterIds, oneCozy]);
  assert.equal(result.type.id, 'clutter-monarch');
  assert.equal(result.tally['clutter-monarch'], 3);
});

test('validateRoastAnswers returns empty array when at least one box is checked', () => {
  assert.deepEqual(validateRoastAnswers(['c1']), []);
});

test('validateRoastAnswers flags an empty selection', () => {
  const errors = validateRoastAnswers([]);
  assert.equal(errors.length, 1);
});
