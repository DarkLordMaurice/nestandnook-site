/**
 * why-doesnt-this-feel-done-yet.mjs
 * Data and scoring logic for the "Why Doesn't This Feel Done Yet?" diagnostic.
 * Built 2026-07-16 as part of the emotional-content-doctrine tool rollout
 * (see Emotional-Content-Doctrine-2026-07-16.md) — this is a diagnosis tool,
 * not a personality quiz: it validates the reader's specific complaint
 * ("this room still doesn't feel done") before routing them anywhere, and
 * the 4 outcomes are root causes, not identities.
 * Pure JS — no imports, no side effects.
 */

export const QUESTIONS = [
  {
    id: 'q1',
    text: "When you look at the room, what's actually bothering you?",
    options: [
      { value: 'missing-anchor',   label: "It just looks... unfinished. Like nothing pulls it together." },
      { value: 'function-friction', label: "Something is physically in the wrong spot, or the wrong size." },
      { value: 'stalled-project',  label: "There's a specific thing I started and never finished." },
      { value: 'comparison-trap',  label: "Honestly? It's fine. I just don't love it as much as a space I saw online." },
    ],
  },
  {
    id: 'q2',
    text: 'How long has it felt this way?',
    options: [
      { value: 'missing-anchor',   label: "Since I moved in — it's never quite clicked." },
      { value: 'function-friction', label: 'It got worse after I added something new.' },
      { value: 'stalled-project',  label: 'It was almost there, then life happened.' },
      { value: 'comparison-trap',  label: 'It felt fine until I started comparing it to something.' },
    ],
  },
  {
    id: 'q3',
    text: "If you had to point to one exact spot that's \"the problem,\" could you?",
    options: [
      { value: 'function-friction', label: 'Yes — I can point to the exact spot and the exact reason.' },
      { value: 'stalled-project',  label: "Yes — there's literally an unfinished task sitting there." },
      { value: 'missing-anchor',   label: "Not really. It's more of a general feeling." },
      { value: 'comparison-trap',  label: "No, because there isn't really a problem." },
    ],
  },
  {
    id: 'q4',
    text: "What have you already tried?",
    options: [
      { value: 'missing-anchor',   label: 'Rearranging things, hoping the right layout would click.' },
      { value: 'function-friction', label: "Nothing yet — I haven't pinpointed the actual mismatch." },
      { value: 'stalled-project',  label: "I started a fix and didn't finish it." },
      { value: 'comparison-trap',  label: "Nothing, because deep down I know it's not really broken." },
    ],
  },
  {
    id: 'q5',
    text: 'What would "done" actually look like?',
    options: [
      { value: 'missing-anchor',   label: 'One thing that makes the whole room feel intentional.' },
      { value: 'function-friction', label: 'Something fitting correctly for once.' },
      { value: 'stalled-project',  label: 'Just closing the loop on the thing I already started.' },
      { value: 'comparison-trap',  label: 'Probably just... accepting that it\'s already good enough.' },
    ],
  },
];

export const TYPES = {
  'missing-anchor': {
    id: 'missing-anchor',
    name: 'The Missing Anchor',
    mirror: "Nothing is actually broken. There's just no single finished, complete zone for your eye to land on — no one spot that reads as fully done, so the whole room reads as unfinished by association. You don't need more stuff. You need one thing to actually be complete.",
    superpower: "You can feel when a room isn't working, even without being able to name why.",
    kryptonite: "You keep rearranging everything instead of finishing one thing.",
    winnieSays: "Pick one zone — one shelf, one corner, one wall — and take it all the way to done before touching anything else. A single finished spot changes how the whole room reads.",
    shareHook: "Tag someone whose room is 90% there and hasn't been for a year",
    ctaLabel: 'Find your one finishing move',
    ctaHref: '/home-office/small-home-office-setup-guide/',
    shareBody: "You're missing one finished anchor spot — not more stuff. Pick one corner and take it all the way to done.",
  },
  'function-friction': {
    id: 'function-friction',
    name: 'Function Friction',
    mirror: "Something in this room physically doesn't fit — a clearance issue, a height mismatch, a storage gap — and no amount of styling will fix a functional mismatch. Your instinct that something is genuinely off is correct. It's just not a taste problem.",
    superpower: "You already know exactly where the friction is. That's most of the work.",
    kryptonite: "You keep buying things to decorate around the problem instead of measuring it.",
    winnieSays: "Before you buy anything else, measure the actual mismatch — height, clearance, or capacity. Fix the fit first. Everything else is downstream of that.",
    shareHook: "Tag someone who keeps rearranging the same broken spot",
    ctaLabel: 'Measure the actual mismatch first',
    ctaHref: '/home-office/how-to-sit-correctly-at-a-small-desk/',
    shareBody: "Something in the room physically doesn't fit — that's not a style problem, it's a measurement problem. Fix the fit first.",
  },
  'stalled-project': {
    id: 'stalled-project',
    name: 'The Stalled Project',
    mirror: "This room was almost done. Then it stopped — usually 80% of the way through, on the unglamorous last 20% (the cables, the mounting, the capping-off step) that doesn't feel urgent until it's the only thing left undone. The gap is smaller than it feels.",
    superpower: "You already did the hard part. What's left is genuinely small.",
    kryptonite: "The unfinished 20% keeps getting reprioritized behind everything newer.",
    winnieSays: "Don't start a new project in this room until you close the old one. The last 20% is usually a single afternoon, not a whole weekend — it just needs to go first.",
    shareHook: "Tag someone with a 'temporary' fix that's been there over a year",
    ctaLabel: 'Close the loop on what you started',
    ctaHref: '/home-office/desk-cable-management/',
    shareBody: "This room isn't unfinished — it's stalled at the last 20%. Close that loop before starting anything new.",
  },
  'comparison-trap': {
    id: 'comparison-trap',
    name: 'The Comparison Trap',
    mirror: "There's a real chance this room already works. The discomfort isn't coming from the room — it's coming from comparing it to a version of a space that was staged, lit, and edited to be photographed. That's not a fair comparison for a room you actually live in.",
    superpower: "You have a genuinely good eye — that's exactly why the comparison stings.",
    kryptonite: "You're grading a lived-in room against a photograph, and the photograph will always win.",
    winnieSays: "Ask what's actually not working — not what's not Pinterest. If nothing's genuinely broken, you're allowed to be done. Save the next purchase for a real problem.",
    shareHook: "Tag someone who's about to buy something their room doesn't actually need",
    ctaLabel: 'Run the real audit before buying anything',
    ctaHref: '/home-office/small-home-office-setup-guide/',
    shareBody: "The room is probably fine — the comparison is unfair. Run a real audit before buying anything new.",
  },
};

/**
 * Score a diagnostic submission.
 * @param {Record<string, string>} answers — { q1: 'missing-anchor', q2: 'stalled-project', ... }
 * @returns {{ type: object, tally: Record<string, number>, isTie: boolean, tiedWith: string[] }}
 */
export function scoreQuiz(answers) {
  const tally = { 'missing-anchor': 0, 'function-friction': 0, 'stalled-project': 0, 'comparison-trap': 0 };
  for (const value of Object.values(answers)) {
    if (value in tally) tally[value]++;
  }
  const max = Math.max(...Object.values(tally));
  const winners = Object.entries(tally).filter(([, count]) => count === max).map(([key]) => key);
  const winner = winners[0];
  const isTie = winners.length > 1;
  return {
    type: TYPES[winner],
    tally,
    isTie,
    tiedWith: isTie ? winners.slice(1).map((key) => TYPES[key].name) : [],
  };
}

/**
 * Validate that all questions have been answered.
 * @param {Record<string, string>} answers
 * @returns {string[]}
 */
export function validateQuizAnswers(answers) {
  return QUESTIONS.filter((q) => !answers[q.id]).map((q) => `Please answer: "${q.text}"`);
}
