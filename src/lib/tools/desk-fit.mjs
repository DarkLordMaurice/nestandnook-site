/** @typedef {'in'|'cm'} Unit */
/** @typedef {'ready'|'adjust-chair'|'add-footrest'|'desk-too-low'|'recheck'} Classification */

const positive = (value) => Number.isFinite(value) && value > 0;
const nonNegative = (value) => Number.isFinite(value) && value >= 0;
const round1 = (value) => Math.round(value * 10) / 10;

export function validateDeskFitInput(input) {
  const errors = [];
  const required = [
    ['deskHeight', 'Desk work-surface height'],
    ['deskClearance', 'Desk underside clearance'],
    ['chairMin', 'Chair minimum seat height'],
    ['chairMax', 'Chair maximum seat height'],
    ['elbowAboveSeat', 'Elbow height above the seat'],
    ['lowerLegHeight', 'Lower-leg height'],
    ['thighClearance', 'Thigh-and-knee clearance'],
  ];
  for (const [key, label] of required) if (!positive(input[key])) errors.push(`${label} must be greater than zero.`);
  for (const [key, label] of [['keyboardThickness', 'Keyboard or desk-pad thickness'], ['footrestMax', 'Maximum footrest height']]) {
    if (!nonNegative(input[key])) errors.push(`${label} cannot be negative.`);
  }
  if (!['in', 'cm'].includes(input.unit)) errors.push('Choose inches or centimeters.');
  if (positive(input.chairMin) && positive(input.chairMax) && input.chairMin > input.chairMax) errors.push('Chair minimum height cannot be greater than its maximum height.');
  const upper = input.unit === 'cm' ? 300 : 120;
  for (const [key, label] of [...required, ['keyboardThickness', 'Keyboard or desk-pad thickness'], ['footrestMax', 'Maximum footrest height']]) {
    if (Number.isFinite(input[key]) && input[key] > upper) errors.push(`${label} looks unusually large. Recheck the unit and measurement.`);
  }
  return errors;
}

export function evaluateDeskFit(input) {
  const errors = validateDeskFitInput(input);
  if (errors.length) throw new Error(errors.join(' '));

  const tolerance = input.unit === 'cm' ? 1.25 : 0.5;
  const safetyMargin = input.unit === 'cm' ? 2.5 : 1;
  const targetSeatHeight = input.deskHeight - input.keyboardThickness - input.elbowAboveSeat;
  const seatWithinRange = targetSeatHeight >= input.chairMin && targetSeatHeight <= input.chairMax;
  const clampedSeatHeight = Math.min(input.chairMax, Math.max(input.chairMin, targetSeatHeight));
  const elbowMismatch = Math.abs(targetSeatHeight - clampedSeatHeight);
  const availableLegroom = input.deskClearance - clampedSeatHeight;
  const requiredLegroom = input.thighClearance + safetyMargin;
  const legroomMargin = availableLegroom - requiredLegroom;
  const footSupportGap = Math.max(0, clampedSeatHeight - input.lowerLegHeight);
  const footrestCoversGap = footSupportGap <= input.footrestMax + tolerance;
  const closeCall = Math.abs(legroomMargin) < tolerance || Math.abs(input.footrestMax - footSupportGap) < tolerance || elbowMismatch > 0 && elbowMismatch < tolerance;

  let classification;
  if (legroomMargin < 0) classification = 'desk-too-low';
  else if (!seatWithinRange && elbowMismatch >= tolerance) classification = 'adjust-chair';
  else if (closeCall) classification = 'recheck';
  else if (footSupportGap > tolerance && footrestCoversGap) classification = 'add-footrest';
  else if (footSupportGap > tolerance && !footrestCoversGap) classification = 'adjust-chair';
  else classification = 'ready';

  const labels = {
    ready: 'The measurements line up',
    'adjust-chair': 'The chair range is the weak link',
    'add-footrest': 'Compatible with a footrest',
    'desk-too-low': 'The desk is too low underneath',
    recheck: 'Measurements are too close to call',
  };
  const reasons = [];
  reasons.push(`The estimated seat height for a relaxed elbow match is ${round1(targetSeatHeight)} ${input.unit}.`);
  reasons.push(seatWithinRange
    ? 'That target falls inside the chair’s stated adjustment range.'
    : `The nearest chair setting misses the target by about ${round1(elbowMismatch)} ${input.unit}.`);
  reasons.push(legroomMargin >= 0
    ? `The underside leaves about ${round1(legroomMargin)} ${input.unit} beyond the measured thigh-and-knee space plus a planning margin.`
    : `The underside is short by about ${round1(Math.abs(legroomMargin))} ${input.unit} after the measured thigh-and-knee space and planning margin.`);
  if (footSupportGap > tolerance) reasons.push(footrestCoversGap
    ? `At the estimated seat setting, a footrest needs to bridge about ${round1(footSupportGap)} ${input.unit}; the entered footrest range can cover it.`
    : `At the estimated seat setting, foot support is short by about ${round1(footSupportGap)} ${input.unit}, more than the entered footrest can cover.`);
  else reasons.push('The estimated seat setting should keep the feet supported without adding meaningful footrest height.');

  return {
    classification, label: labels[classification], targetSeatHeight: round1(targetSeatHeight),
    recommendedSeatHeight: round1(clampedSeatHeight), elbowMismatch: round1(elbowMismatch),
    availableLegroom: round1(availableLegroom), legroomMargin: round1(legroomMargin),
    footSupportGap: round1(footSupportGap), seatWithinRange, footrestCoversGap, closeCall, reasons,
    measureBeforeBuying: [
      'Measure desk height at the keyboard or input surface, not at a decorative edge.',
      'Confirm the chair’s loaded seat-height range; published dimensions may be measured without a person sitting in it.',
      'Check the narrowest underside point, including drawers, support bars, cable trays, and apron rails.',
      'Measure elbow-to-seat and lower-leg height while wearing the shoes normally used at the desk.',
    ],
    avoid: [
      'Do not raise the chair for elbow comfort while leaving the feet unsupported.',
      'Do not count empty-looking space that is blocked by a drawer, crossbar, or control box.',
      'Do not treat this measurement check as medical or clinical ergonomic advice.',
    ],
  };
}
