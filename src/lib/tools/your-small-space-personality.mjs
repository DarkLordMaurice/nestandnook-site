/**
 * your-small-space-personality.mjs
 * Data and scoring logic for the "What Kind of Small-Space Person Are You?" quiz.
 * Pure JS — no imports, no side effects.
 */

export const QUESTIONS = [
  {
    id: 'q1',
    text: 'When you get home and walk through the door, your first feeling is usually…',
    options: [
      { value: 'nester',    label: 'Relief. This is my place.' },
      { value: 'starter',   label: 'Possibility. I see what it could be.' },
      { value: 'fixer',     label: 'Frustration. Nothing\'s where it should be.' },
      { value: 'optimizer', label: 'Fine, but I notice the one thing that could be better.' },
    ],
  },
  {
    id: 'q2',
    text: 'Your honest relationship with buying things for your home:',
    options: [
      { value: 'nester',    label: 'I love it — finding the right piece for a spot is genuinely satisfying.' },
      { value: 'starter',   label: 'I want to get it right the first time so I research everything first.' },
      { value: 'fixer',     label: 'I\'ve bought a lot of organizing stuff that didn\'t fix anything.' },
      { value: 'optimizer', label: 'I only buy when I know exactly what I need and why.' },
    ],
  },
  {
    id: 'q3',
    text: 'If a friend came over and noticed your space, what would they say?',
    options: [
      { value: 'nester',    label: '"It\'s so you in here."' },
      { value: 'starter',   label: '"I can tell you\'re in the middle of something."' },
      { value: 'fixer',     label: '"Have you tried those drawer dividers I told you about?"' },
      { value: 'optimizer', label: '"This is nice. I feel like something\'s almost perfect in here."' },
    ],
  },
  {
    id: 'q4',
    text: 'The thing that stresses you out most about your space:',
    options: [
      { value: 'nester',    label: 'There\'s not enough room for everything I actually love.' },
      { value: 'starter',   label: 'I don\'t want to mess it up before I\'ve really thought it through.' },
      { value: 'fixer',     label: 'I don\'t know why it still doesn\'t feel right after everything I\'ve tried.' },
      { value: 'optimizer', label: 'That one corner/shelf/drawer I haven\'t fixed yet.' },
    ],
  },
  {
    id: 'q5',
    text: 'Your version of "getting organized" usually starts with:',
    options: [
      { value: 'nester',    label: 'Making space for things I actually use and love.' },
      { value: 'starter',   label: 'A list, a plan, maybe a mood board.' },
      { value: 'fixer',     label: 'Buying something — a new bin, a new system — and hoping this is the one.' },
      { value: 'optimizer', label: 'Looking at what\'s there and asking what\'s not earning its place.' },
    ],
  },
  {
    id: 'q6',
    text: 'When you imagine your space "working perfectly," it feels like:',
    options: [
      { value: 'nester',    label: 'Cozy and full — but intentional. Everything tells a story.' },
      { value: 'starter',   label: 'Clean and ready. A good foundation for what comes next.' },
      { value: 'fixer',     label: 'Like I finally figured it out — and it\'s simpler than I expected.' },
      { value: 'optimizer', label: 'Exactly like now, minus that one thing.' },
    ],
  },
];

export const TYPES = {
  nester: {
    id: 'nester',
    name: 'The Nester',
    mirror: "You love your space and the things in it. Your home tells your story — the mug from that trip, the shelf of books you'll definitely re-read, the throw blanket collection that keeps growing. The problem isn't that you have too much. The problem is your space wasn't built for someone who actually lives in it this fully.",
    superpower: "You know exactly what matters — you just need a system that honors that.",
    kryptonite: "You buy storage for things you should let go of.",
    winnieSays: "Your stuff isn't the problem. The system around it is. Start with one category you genuinely use every day and build from there — don't touch the things you love until the system is working.",
    shareHook: "Tag someone whose apartment tells a whole story",
    ctaLabel: 'Build a system around what you love',
    ctaHref: '/kitchen/how-to-organize-a-small-kitchen-with-no-pantry/',
  },
  starter: {
    id: 'starter',
    name: 'The Fresh Starter',
    mirror: "You've just moved, or you've hit a wall and decided this time is different. You're ready. You have a vision. The anxiety isn't 'where do I start' — it's 'I don't want to do this wrong again.' You've been burned by impulse-buying your way into a messier space before and you're determined to think before you buy.",
    superpower: "Motivation is at its peak right now — use it strategically.",
    kryptonite: "Analysis paralysis. You'll research for weeks and then grab the wrong thing in a hurry.",
    winnieSays: "The research phase is good — but give it a deadline. Two weeks of thinking, then one decision. The perfect setup doesn't come from waiting. It comes from starting with the right foundation and adjusting.",
    shareHook: "Tag someone who's in their 'this time will be different' era",
    ctaLabel: 'Start with the right foundation',
    ctaHref: '/kitchen/small-kitchen-starter-kit-under-100/',
  },
  fixer: {
    id: 'fixer',
    name: 'The Chronic Fixer',
    mirror: "You've tried. The bins. The drawer dividers. The label maker phase. The 'everything gets a home' system that lasted two weeks. Your space still doesn't feel right and you're starting to wonder if the problem is you. It's not. The problem is you've been buying solutions to the wrong problem.",
    superpower: "You know what hasn't worked — which means you're closer than you think.",
    kryptonite: "Buying the solution before diagnosing the actual problem.",
    winnieSays: "Stop buying for a minute. The next step isn't another product — it's figuring out what actually causes the chaos. Usually it's one habit, not ten missing containers. Find the habit first.",
    shareHook: "Tag someone who has bought the exact same type of bin three times",
    ctaLabel: 'Diagnose the real problem first',
    ctaHref: '/kitchen/how-to-hide-small-kitchen-appliances-on-the-counter/',
  },
  optimizer: {
    id: 'optimizer',
    name: 'The Space Optimizer',
    mirror: "Your space is functional. It works. But you walk past certain spots and think 'there's a better version of this.' You're not in crisis — you're refining. You have good instincts, you're just looking for the upgrade that makes everything click.",
    superpower: "You already understand your space — you just need the right next move.",
    kryptonite: "Overthinking the upgrade until the moment passes.",
    winnieSays: "You're past the 'does this work at all' stage. The question now is what earns its spot versus what's just taking up real estate. Pick one area, make the call, see how it feels.",
    shareHook: "Tag someone who notices the one thing in every room that could be better",
    ctaLabel: 'Find the specific upgrade you\'re missing',
    ctaHref: '/home-office/best-desk-organizers-for-a-small-desk/',
  },
};

/**
 * Score a quiz submission.
 * @param {Record<string, string>} answers — { q1: 'nester', q2: 'fixer', ... }
 * @returns {{ type: object, tally: Record<string, number>, isTie: boolean, tiedWith: string[] }}
 */
export function scoreQuiz(answers) {
  const tally = { nester: 0, starter: 0, fixer: 0, optimizer: 0 };
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
