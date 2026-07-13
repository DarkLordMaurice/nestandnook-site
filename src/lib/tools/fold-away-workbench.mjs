const UNITS = ['in', 'cm'];

const limits = {
  in: { recheck: 1, widthComfort: 6, passage: 30 },
  cm: { recheck: 2.5, widthComfort: 15, passage: 76 },
};

export function validateWorkbenchInput(input) {
  const errors = [];
  if (!UNITS.includes(input.unit)) errors.push('Choose inches or centimeters.');
  const positive = [
    ['wallWidth', 'usable wall width'], ['parkedDepth', 'wall-to-obstacle depth with the car parked'],
    ['openDepthAvailable', 'wall-to-obstacle depth with the car moved'], ['benchWidth', 'bench width'],
    ['openDepth', 'open bench depth'], ['foldedDepth', 'folded bench depth'],
    ['operatorClearance', 'working clearance'], ['passageTarget', 'minimum passage target'],
  ];
  for (const [key, label] of positive) {
    const value = Number(input[key]);
    if (!Number.isFinite(value) || value <= 0) errors.push(`Enter a ${label} greater than zero.`);
  }
  if (Number(input.openDepthAvailable) < Number(input.parkedDepth)) errors.push('The car-moved depth cannot be smaller than the car-parked depth.');
  if (Number(input.foldedDepth) > Number(input.openDepth)) errors.push('Folded depth cannot be greater than open depth.');
  return errors;
}

export function evaluateWorkbench(input) {
  const errors = validateWorkbenchInput(input);
  if (errors.length) throw new Error(errors.join(' '));
  const threshold = limits[input.unit];
  const widthMargin = input.wallWidth - input.benchWidth;
  const requiredWorkingDepth = input.openDepth + input.operatorClearance;
  const parkedWorkMargin = input.parkedDepth - requiredWorkingDepth;
  const movedWorkMargin = input.openDepthAvailable - requiredWorkingDepth;
  const foldedPassage = input.parkedDepth - input.foldedDepth;
  const foldedPassageMargin = foldedPassage - input.passageTarget;
  const nearBoundary = [widthMargin, parkedWorkMargin, movedWorkMargin, foldedPassageMargin].some((margin) => Math.abs(margin) <= threshold.recheck);

  let classification;
  if (widthMargin < 0 || movedWorkMargin < 0 || foldedPassageMargin < 0) classification = 'no-fit';
  else if (nearBoundary) classification = 'recheck';
  else if (parkedWorkMargin >= 0) classification = widthMargin < threshold.widthComfort || parkedWorkMargin < threshold.widthComfort ? 'tight' : 'ready';
  else classification = 'move-car';

  const labels = {
    ready: 'Fits with the car parked', tight: 'Fits, but the margins are tight',
    'move-car': 'Parked compactly; open only after moving the car',
    'no-fit': 'This bench and bay do not safely share the measured space', recheck: 'The result is too close to call',
  };
  const reasons = [];
  if (widthMargin < 0) reasons.push(`The bench is ${round(Math.abs(widthMargin))} ${input.unit} wider than the usable wall bay.`);
  else reasons.push(`The bench leaves ${round(widthMargin)} ${input.unit} of total wall-width margin.`);
  if (parkedWorkMargin >= 0) reasons.push(`Open working depth leaves ${round(parkedWorkMargin)} ${input.unit} before the parked-car boundary.`);
  else reasons.push(`Opening and using the bench needs ${round(Math.abs(parkedWorkMargin))} ${input.unit} more depth than the parked-car layout provides.`);
  reasons.push(`When folded, the bench leaves an estimated ${round(foldedPassage)} ${input.unit} passage.`);
  if (movedWorkMargin >= 0) reasons.push(`With the car moved, the working setup retains ${round(movedWorkMargin)} ${input.unit} of depth margin.`);
  else reasons.push(`Even with the car moved, the setup is short by ${round(Math.abs(movedWorkMargin))} ${input.unit}.`);

  const measureBeforeBuying = [
    'Measure from the wall’s proudest obstruction, including trim, outlets, pipes, door tracks, and handles.',
    'Confirm the manufacturer’s open depth includes hinges, brackets, vises, and any rear mounting offset.',
    'Mark the folded and open outlines on the floor with painter’s tape, then open doors and walk the route.',
    'Verify wall construction, fasteners, load rating, and installation instructions separately from this space check.',
  ];
  const avoid = [
    'Do not place the bench in a garage-door track, electrical-panel, appliance, stair, or required-exit clearance.',
    'Do not treat advertised load capacity as permission to use unsuitable wall anchors or framing.',
    'Do not count a vehicle’s door-swing or mirror space as working clearance.',
  ];
  return { classification, label: labels[classification], widthMargin: round(widthMargin), requiredWorkingDepth: round(requiredWorkingDepth), parkedWorkMargin: round(parkedWorkMargin), movedWorkMargin: round(movedWorkMargin), foldedPassage: round(foldedPassage), foldedPassageMargin: round(foldedPassageMargin), reasons, measureBeforeBuying, avoid };
}

function round(value) { return Math.round(value * 10) / 10; }
