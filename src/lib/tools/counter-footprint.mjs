/** @typedef {'in'|'cm'} Unit */
/** @typedef {'daily'|'weekly'|'occasional'} Frequency */
/** @typedef {'permanent'|'permanent-tight'|'store-between-uses'|'too-large'|'recheck'} Classification */

const finitePositive = (value) => Number.isFinite(value) && value > 0;
const finiteNonNegative = (value) => Number.isFinite(value) && value >= 0;

export function validateCounterFootprintInput(input) {
  const errors = [];
  const required = [
    ['counterWidth', 'Counter width'],
    ['counterDepth', 'Counter depth'],
    ['itemWidth', 'Item width'],
    ['itemDepth', 'Item depth'],
    ['prepWidth', 'Prep-zone width'],
    ['prepDepth', 'Prep-zone depth'],
  ];

  for (const [key, label] of required) {
    if (!finitePositive(input[key])) errors.push(`${label} must be greater than zero.`);
  }

  for (const [key, label] of [
    ['sideClearance', 'Side clearance'],
    ['rearClearance', 'Rear clearance'],
  ]) {
    if (!finiteNonNegative(input[key])) errors.push(`${label} cannot be negative.`);
  }

  if (!['daily', 'weekly', 'occasional'].includes(input.frequency)) {
    errors.push('Choose how often you expect to use the item.');
  }
  if (!['in', 'cm'].includes(input.unit)) errors.push('Choose inches or centimeters.');

  const upper = input.unit === 'cm' ? 1000 : 400;
  for (const [key, label] of [...required, ['sideClearance', 'Side clearance'], ['rearClearance', 'Rear clearance']]) {
    if (Number.isFinite(input[key]) && input[key] > upper) {
      errors.push(`${label} looks unusually large. Recheck the unit and measurement.`);
    }
  }

  return errors;
}

const round1 = (value) => Math.round(value * 10) / 10;

export function evaluateCounterFootprint(input) {
  const errors = validateCounterFootprintInput(input);
  if (errors.length) throw new Error(errors.join(' '));

  const effectiveItemWidth = input.itemWidth + input.sideClearance * 2;
  const effectiveItemDepth = input.itemDepth + input.rearClearance;
  const counterArea = input.counterWidth * input.counterDepth;
  const itemArea = effectiveItemWidth * effectiveItemDepth;
  const remainingArea = Math.max(0, counterArea - itemArea);
  const footprintPercent = (itemArea / counterArea) * 100;

  const physicallyFits = effectiveItemWidth <= input.counterWidth && effectiveItemDepth <= input.counterDepth;
  const preservesPrepZone = physicallyFits
    && effectiveItemWidth + input.prepWidth <= input.counterWidth
    && Math.max(effectiveItemDepth, input.prepDepth) <= input.counterDepth;

  const widthMargin = input.counterWidth - effectiveItemWidth;
  const depthMargin = input.counterDepth - effectiveItemDepth;
  const tolerance = input.unit === 'cm' ? 2.5 : 1;
  const closeCall = physicallyFits && (widthMargin < tolerance || depthMargin < tolerance);

  let classification;
  if (!physicallyFits) {
    classification = 'too-large';
  } else if (closeCall) {
    classification = 'recheck';
  } else if (preservesPrepZone && footprintPercent <= 35) {
    classification = 'permanent';
  } else if (preservesPrepZone && input.frequency === 'daily') {
    classification = 'permanent-tight';
  } else if (!preservesPrepZone && input.frequency === 'daily' && !input.storageAvailable) {
    classification = 'permanent-tight';
  } else {
    classification = 'store-between-uses';
  }

  const labels = {
    permanent: 'Earns permanent counter space',
    'permanent-tight': 'Fits, but the counter will stay tight',
    'store-between-uses': 'Store it between uses',
    'too-large': 'Too large for this counter',
    recheck: 'Measurements are too close to call',
  };

  const reasons = [];
  if (!physicallyFits) {
    if (effectiveItemWidth > input.counterWidth) reasons.push('The item plus side clearance is wider than the available counter.');
    if (effectiveItemDepth > input.counterDepth) reasons.push('The item plus rear clearance is deeper than the available counter.');
  } else {
    reasons.push(`The operating footprint uses about ${round1(footprintPercent)}% of the measured counter area.`);
    reasons.push(preservesPrepZone
      ? 'The appliance and your protected prep zone can sit side by side in this estimate.'
      : 'The item fits physically, but it does not preserve the prep zone you asked to keep clear.');
    if (input.frequency === 'daily') reasons.push('Daily use makes permanent placement more defensible than it would be for an occasional tool.');
    if (input.frequency !== 'daily') reasons.push('Because use is not daily, storage between uses may return more value than permanent placement.');
  }

  return {
    classification,
    label: labels[classification],
    effectiveItemWidth: round1(effectiveItemWidth),
    effectiveItemDepth: round1(effectiveItemDepth),
    counterArea: round1(counterArea),
    itemArea: round1(itemArea),
    footprintPercent: round1(footprintPercent),
    remainingArea: round1(remainingArea),
    physicallyFits,
    preservesPrepZone,
    closeCall,
    reasons,
    measureBeforeBuying: [
      'Confirm the manufacturer-required rear, side, and overhead clearance for the exact model.',
      'Measure the widest and deepest points, including handles, cord exits, hinges, lids, and baskets.',
      'Check the outlet location and make sure the cord can reach without crossing a sink, burner, or walkway.',
    ],
    avoid: [
      'Do not treat this area estimate as proof that the real layout is safe or convenient.',
      'Do not reduce manufacturer clearance simply to make the item fit.',
      'Do not block the only landing zone for hot cookware or the counter section you actually use for prep.',
    ],
  };
}
