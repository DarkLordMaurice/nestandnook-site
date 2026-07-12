import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateDeskFit, validateDeskFitInput } from '../../src/lib/tools/desk-fit.mjs';

const base = { unit: 'in', deskHeight: 29, deskClearance: 27, keyboardThickness: 1, chairMin: 16, chairMax: 21, elbowAboveSeat: 10, lowerLegHeight: 18, thighClearance: 7, footrestMax: 4 };

test('returns ready for a clean chair, desk, and foot-support match', () => assert.equal(evaluateDeskFit(base).classification, 'ready'));
test('returns add-footrest when the chair fits the desk but feet need support', () => assert.equal(evaluateDeskFit({ ...base, deskHeight: 31, deskClearance: 30 }).classification, 'add-footrest'));
test('returns desk-too-low when underside clearance crowds the measured legs', () => assert.equal(evaluateDeskFit({ ...base, deskClearance: 25 }).classification, 'desk-too-low'));
test('returns adjust-chair when target seat height exceeds chair range', () => assert.equal(evaluateDeskFit({ ...base, deskHeight: 34, deskClearance: 34, footrestMax: 8 }).classification, 'adjust-chair'));
test('returns adjust-chair when available footrest cannot bridge the support gap', () => assert.equal(evaluateDeskFit({ ...base, deskHeight: 31, deskClearance: 30, footrestMax: 1 }).classification, 'adjust-chair'));
test('returns recheck on a near-zero legroom margin', () => assert.equal(evaluateDeskFit({ ...base, deskClearance: 26.2 }).classification, 'recheck'));
test('metric and imperial inputs produce the same classification', () => {
  const cm = Object.fromEntries(Object.entries(base).map(([key, value]) => typeof value === 'number' ? [key, value * 2.54] : [key, value])); cm.unit = 'cm';
  assert.equal(evaluateDeskFit(cm).classification, evaluateDeskFit(base).classification);
});
test('accepts a zero-thickness keyboard and zero-height footrest', () => assert.equal(validateDeskFitInput({ ...base, keyboardThickness: 0, footrestMax: 0 }).length, 0));
test('rejects inverted chair ranges and missing measurements', () => {
  const errors = validateDeskFitInput({ ...base, chairMin: 22, chairMax: 18, deskHeight: 0 });
  assert.ok(errors.some((error) => error.includes('greater than zero'))); assert.ok(errors.some((error) => error.includes('minimum height')));
});
