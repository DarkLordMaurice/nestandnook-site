import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateCounterFootprint, validateCounterFootprintInput } from '../../src/lib/tools/counter-footprint.mjs';

const base = {
  unit: 'in', counterWidth: 48, counterDepth: 25, itemWidth: 12, itemDepth: 14,
  sideClearance: 1, rearClearance: 2, prepWidth: 20, prepDepth: 18,
  frequency: 'daily', storageAvailable: false,
};

test('classifies a compact daily-use item as permanent when prep space remains', () => {
  const result = evaluateCounterFootprint(base);
  assert.equal(result.classification, 'permanent');
  assert.equal(result.physicallyFits, true);
  assert.equal(result.preservesPrepZone, true);
});

test('rejects an item that exceeds counter depth after clearance', () => {
  const result = evaluateCounterFootprint({ ...base, itemDepth: 24, rearClearance: 3 });
  assert.equal(result.classification, 'too-large');
  assert.equal(result.physicallyFits, false);
});

test('recommends storage for a weekly item that crowds the protected prep zone', () => {
  const result = evaluateCounterFootprint({ ...base, itemWidth: 26, prepWidth: 24, frequency: 'weekly', storageAvailable: true });
  assert.equal(result.classification, 'store-between-uses');
});

test('flags near-zero margin as a recheck', () => {
  const result = evaluateCounterFootprint({ ...base, counterWidth: 14.5, prepWidth: 1 });
  assert.equal(result.classification, 'recheck');
});

test('metric and imperial inputs produce equivalent percentages', () => {
  const imperial = evaluateCounterFootprint(base);
  const metric = evaluateCounterFootprint(Object.fromEntries(Object.entries({ ...base, unit: 'cm' }).map(([key, value]) =>
    [key, ['counterWidth', 'counterDepth', 'itemWidth', 'itemDepth', 'sideClearance', 'rearClearance', 'prepWidth', 'prepDepth'].includes(key) ? value * 2.54 : value]
  )));
  assert.equal(metric.footprintPercent, imperial.footprintPercent);
});

test('validation catches blank, negative, and implausibly large values', () => {
  const errors = validateCounterFootprintInput({ ...base, counterWidth: 0, sideClearance: -1, itemWidth: 999 });
  assert.ok(errors.length >= 3);
});

test('exact physical-fit boundary is accepted', () => {
  const result = evaluateCounterFootprint({ ...base, counterWidth: 14, counterDepth: 16, prepWidth: 1 });
  assert.equal(result.physicallyFits, true);
  assert.equal(result.classification, 'recheck');
});

test('zero clearances are valid', () => {
  assert.deepEqual(validateCounterFootprintInput({ ...base, sideClearance: 0, rearClearance: 0 }), []);
});

test('daily use without storage can produce permanent-tight when prep is crowded', () => {
  const result = evaluateCounterFootprint({ ...base, itemWidth: 25, prepWidth: 24 });
  assert.equal(result.classification, 'permanent-tight');
});
