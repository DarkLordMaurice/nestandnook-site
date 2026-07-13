import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateWorkbench, validateWorkbenchInput } from '../../src/lib/tools/fold-away-workbench.mjs';

const base = { unit: 'in', wallWidth: 72, parkedDepth: 64, openDepthAvailable: 100, benchWidth: 48, openDepth: 24, foldedDepth: 10, operatorClearance: 30, passageTarget: 30 };

test('ready with the car parked', () => assert.equal(evaluateWorkbench(base).classification, 'ready'));
test('tight but usable parked fit', () => assert.equal(evaluateWorkbench({ ...base, wallWidth: 53 }).classification, 'tight'));
test('move-car workflow', () => assert.equal(evaluateWorkbench({ ...base, parkedDepth: 45 }).classification, 'move-car'));
test('bench too wide', () => assert.equal(evaluateWorkbench({ ...base, benchWidth: 80 }).classification, 'no-fit'));
test('open layout fails even with car moved', () => assert.equal(evaluateWorkbench({ ...base, openDepthAvailable: 50, parkedDepth: 40 }).classification, 'no-fit'));
test('folded passage fails target', () => assert.equal(evaluateWorkbench({ ...base, parkedDepth: 45, foldedDepth: 20 }).classification, 'no-fit'));
test('exact boundary requests recheck', () => assert.equal(evaluateWorkbench({ ...base, parkedDepth: 54 }).classification, 'recheck'));
test('metric and imperial inputs agree', () => { const metric = Object.fromEntries(Object.entries(base).map(([key, value]) => [key, typeof value === 'number' ? value * 2.54 : key === 'unit' ? 'cm' : value])); assert.equal(evaluateWorkbench(metric).classification, evaluateWorkbench(base).classification); });
test('invalid dimensions are rejected', () => assert.ok(validateWorkbenchInput({ ...base, foldedDepth: 30, openDepth: 20, openDepthAvailable: 20, parkedDepth: 30 }).length >= 2));
test('result exposes buying checklist', () => assert.equal(evaluateWorkbench(base).measureBeforeBuying.length, 4));
