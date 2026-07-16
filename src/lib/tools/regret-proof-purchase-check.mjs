/**
 * regret-proof-purchase-check.mjs
 * Data and scoring logic for "The Regret-Proof Purchase Check" — an
 * anti-impulse gut-check run BEFORE a purchase, not a product recommendation
 * tool. Built 2026-07-16 as part of the emotional-content-doctrine tool
 * rollout (see Emotional-Content-Doctrine-2026-07-16.md). This deliberately
 * does not sell anything — a "skip it" verdict routes back into the site's
 * diagnostic tool instead of a product page, which is the point: not every
 * feeling of "I need to fix my space" should end in a cart.
 * Pure JS — no imports, no side effects.
 */

export const QUESTIONS = [
  {
    id: 'q1',
    text: 'Can you name the specific problem this solves, in one sentence, right now?',
    options: [
      { value: 'buy',  label: 'Yes, easily — I could say it in one breath.' },
      { value: 'wait', label: "Sort of — I'd need a minute to explain it." },
      { value: 'skip', label: "Not really — I just think I'd like having it." },
    ],
  },
  {
    id: 'q2',
    text: 'Where exactly will it live, and does that spot exist right now?',
    options: [
      { value: 'buy',  label: 'Yes — I already know the exact spot and it\'s clear.' },
      { value: 'wait', label: "I have a rough idea but haven't measured it." },
      { value: 'skip', label: "No — I'll figure that out after it arrives." },
    ],
  },
  {
    id: 'q3',
    text: 'How did you find this item?',
    options: [
      { value: 'buy',  label: 'I went looking for it because of a specific need.' },
      { value: 'wait', label: "An ad or a \"you might also like\" followed me around for a few days." },
      { value: 'skip', label: "I saw it 10 minutes ago and I'm already adding it to the cart." },
    ],
  },
  {
    id: 'q4',
    text: 'If it were 30% more expensive, would you still want it?',
    options: [
      { value: 'buy',  label: 'Yes, honestly.' },
      { value: 'wait', label: "Maybe — I'd think about it." },
      { value: 'skip', label: "No — the price is doing a lot of the convincing." },
    ],
  },
  {
    id: 'q5',
    text: 'Do you already own something that almost does this job?',
    options: [
      { value: 'buy',  label: "No — there's a real gap." },
      { value: 'wait', label: "Yes, but it genuinely doesn't work well." },
      { value: 'skip', label: "Yes, and it's basically fine — I just want the nicer version." },
    ],
  },
  {
    id: 'q6',
    text: "Picture yourself a month from now. What's the likely outcome?",
    options: [
      { value: 'buy',  label: "I'm using it regularly and it turned out to be the right call." },
      { value: 'wait', label: 'It\'s fine, but I probably could have waited.' },
      { value: 'skip', label: "It's in a closet, or back in a box waiting to be returned." },
    ],
  },
];

export const TYPES = {
  buy: {
    id: 'buy',
    name: 'Green Light: Buy It',
    mirror: "You know the problem, you know the spot, and you went looking for this on purpose. This isn't impulse — it's a considered decision that happens to be easy to make. That's what a good purchase actually looks like.",
    superpower: "You did the thinking before the cart, not after.",
    kryptonite: "Even a good decision deserves a real home for the thing — recheck the spot right before it arrives.",
    winnieSays: "Go ahead. You've already done the part most people skip. Just double-check the exact spot one more time before it ships.",
    shareHook: "Tag someone who actually thinks before they buy",
    ctaLabel: 'See how a curated kit gets this right',
    ctaHref: '/kitchen/small-kitchen-starter-kit-under-100/',
    shareBody: "You named the problem, the spot, and the reason before adding to cart. That's a green light, not an impulse buy.",
  },
  wait: {
    id: 'wait',
    name: 'Yellow Light: Give It 48 Hours',
    mirror: "This isn't a clear yes or a clear no — and that's useful information, not a failure to decide. Somewhere between the ad that found you and the item that's mostly-fine-but-not-great, there's a real question worth 48 hours before it becomes a purchase.",
    superpower: "You're self-aware enough to notice you're not fully sure.",
    kryptonite: "Uncertainty resolves itself in the cart a lot faster than it resolves itself in your head — don't let checkout make the decision for you.",
    winnieSays: "Close the tab. If you still want it in two days, you actually want it. If you forgot about it, you have your answer.",
    shareHook: "Tag someone whose cart has had the same thing in it for a week",
    ctaLabel: 'Run the audit before you decide',
    ctaHref: '/home-office/small-home-office-setup-guide/',
    shareBody: "Not a clear yes, not a clear no — that's the yellow light. Give it 48 hours before it becomes a purchase.",
  },
  skip: {
    id: 'skip',
    name: 'Red Light: Skip It (For Now)',
    mirror: "There's no real problem this solves, no clear spot for it, and the appeal is coming more from the ad or the price than from an actual gap in your space. That's worth noticing before it becomes a return label three weeks from now.",
    superpower: "You're honest enough to run this check instead of just clicking buy — that's rare.",
    kryptonite: "The urge to buy something is sometimes standing in for a different, less shopping-shaped problem.",
    winnieSays: "Skip the cart for now. If your space still feels off, that's a real signal — it's just not pointing at this item. Go figure out what it's actually pointing at.",
    shareHook: "Tag someone about to buy the thing that fixes nothing",
    ctaLabel: "Find out what's actually bothering you",
    ctaHref: '/tools/why-doesnt-this-feel-done-yet/',
    shareBody: "No named problem, no clear spot, mostly ad-driven appeal — that's a red light. The urge to buy is pointing somewhere else.",
  },
};

/**
 * Score a purchase-check submission.
 * @param {Record<string, string>} answers — { q1: 'buy', q2: 'wait', ... }
 * @returns {{ type: object, tally: Record<string, number>, isTie: boolean, tiedWith: string[] }}
 */
export function scoreQuiz(answers) {
  // 'wait' listed first so a genuine tie defaults to the cautious middle
  // path, not an automatic green light — matches this tool's actual
  // purpose (countering impulse), unlike the personality/diagnostic quizzes
  // where insertion order doesn't carry a safety implication.
  const tally = { wait: 0, buy: 0, skip: 0 };
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
