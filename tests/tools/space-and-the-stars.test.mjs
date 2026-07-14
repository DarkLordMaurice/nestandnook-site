import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SIGNS, getSignById, getAllSignIds } from '../../src/lib/tools/space-and-the-stars.mjs';

test('SIGNS contains exactly 12 entries', () => {
  assert.equal(SIGNS.length, 12);
});

test('every sign has all required fields', () => {
  const required = ['id', 'glyph', 'name', 'dates', 'archetype', 'profile', 'superpower', 'kryptonite', 'winnieSays', 'ctaLabel', 'ctaHref', 'hub'];
  for (const sign of SIGNS) {
    for (const field of required) {
      assert.ok(sign[field], `Sign ${sign.id} missing field: ${field}`);
    }
  }
});

test('all sign ids are unique', () => {
  const ids = SIGNS.map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length);
});

test('getSignById returns correct sign', () => {
  const aries = getSignById('aries');
  assert.equal(aries.name, 'Aries');
  assert.equal(aries.archetype, 'The Impulse Upgrader');
});

test('getSignById returns null for unknown id', () => {
  assert.equal(getSignById('ophiuchus'), null);
});

test('getAllSignIds returns 12 ids', () => {
  const ids = getAllSignIds();
  assert.equal(ids.length, 12);
  assert.ok(ids.includes('aries'));
  assert.ok(ids.includes('pisces'));
});

test('all ctaHref values start with /', () => {
  for (const sign of SIGNS) {
    assert.ok(sign.ctaHref.startsWith('/'), `Sign ${sign.id} ctaHref should start with /`);
  }
});
