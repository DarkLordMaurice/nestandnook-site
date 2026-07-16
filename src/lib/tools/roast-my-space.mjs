/**
 * roast-my-space.mjs
 * Data and scoring logic for "Roast My Space" — a shareable, confession-style
 * tool built 2026-07-16 as part of the emotional-content-doctrine tool
 * rollout (see Emotional-Content-Doctrine-2026-07-16.md). Unlike the other
 * two tools (single-answer-per-question), this one is a checklist: readers
 * pick every confession that's true, and the roast is scored across all of
 * them. The roast itself is always affectionate, never actually mean —
 * never about a third party, always about the reader's own space, same
 * standing rule the site already applies to Winnie's own pending-photo
 * jokes (see WinniePendingPhoto.astro).
 * Pure JS — no imports, no side effects.
 */

export const CONFESSIONS = [
  { id: 'c1',  label: 'There\'s a chair, and its only real job is holding clothes.', type: 'clutter-monarch' },
  { id: 'c2',  label: 'You own more storage bins than you\'ve actually sorted things into.', type: 'clutter-monarch' },
  { id: 'c3',  label: 'There\'s a drawer or closet you will not open in front of guests.', type: 'clutter-monarch' },
  { id: 'c4',  label: 'Something has been "temporary" for over a year.', type: 'serial-starter' },
  { id: 'c5',  label: 'You\'ve started reorganizing a space and abandoned it mid-project — more than once.', type: 'serial-starter' },
  { id: 'c6',  label: 'You\'ve bought the same type of organizing bin more than once, hoping this one would be the one.', type: 'serial-starter' },
  { id: 'c7',  label: 'You have a favorite blanket pile, and it has never once been fully folded.', type: 'cozy-chaos' },
  { id: 'c8',  label: 'Guests always say it "feels so cozy" — and you know exactly which corner they didn\'t see.', type: 'cozy-chaos' },
  { id: 'c9',  label: 'There\'s a candle, a plant, and a stack of books arranged specifically for when people visit.', type: 'cozy-chaos' },
  { id: 'c10', label: 'You\'ve rearranged the same three items more than five times looking for "the right spot."', type: 'stealth-perfectionist' },
  { id: 'c11', label: 'Everything looks great until someone opens a cabinet.', type: 'stealth-perfectionist' },
  { id: 'c12', label: 'You have a system. The system requires you to be well-rested and organized to work. You are neither, most days.', type: 'stealth-perfectionist' },
];

export const TYPES = {
  'clutter-monarch': {
    id: 'clutter-monarch',
    name: 'The Clutter Monarch',
    roastLine: "You don't have clutter. You have a *collection*, and it has simply outgrown its palace. There's a whole kingdom behind that one drawer nobody's allowed to open.",
    realTalk: "Here's the actual pattern: you keep buying containment instead of sorting what's already there. More bins doesn't fix a sorting problem — it just gives the pile somewhere nicer to live.",
    winnieSays: "Pick the one spot you'd least want a guest to open. Empty it completely, sort it into keep/donate/trash, and only put back what earns a spot. Do that before buying a single new bin.",
    shareHook: "Tag your fellow Clutter Monarch — you'll know who",
    ctaLabel: 'Sort one small spot for real',
    ctaHref: '/kitchen/how-to-organize-a-small-pantry/',
    shareBody: "Verdict: The Clutter Monarch. More bins won't fix it — sort one spot for real before buying another container.",
  },
  'serial-starter': {
    id: 'serial-starter',
    name: 'The Serial Project Starter',
    roastLine: "Five projects, one finished, and a very confident origin story for each of the other four. Your space is basically a museum of good intentions.",
    realTalk: "You're not bad at organizing — you're bad at the boring last step. The first 80% of a project is fun. The last 20% (mounting, capping off, actually donating the bag by the door) is not, and that's exactly why it's still sitting there.",
    winnieSays: "Don't start anything new until one stalled project is actually finished — the whole thing, including the boring last step. One closed loop beats five open ones.",
    shareHook: "Tag someone with a 'temporary' fix that's over a year old",
    ctaLabel: 'Finish the boring last step',
    ctaHref: '/home-office/desk-cable-management/',
    shareBody: "Verdict: The Serial Project Starter. Five projects, one finished — close one loop before opening another.",
  },
  'cozy-chaos': {
    id: 'cozy-chaos',
    name: 'The Cozy Chaos Curator',
    roastLine: "Your space has main-character energy and a supporting cast of chaos just out of frame. Warm, inviting, and there is absolutely a corner doing a lot of heavy lifting to keep the illusion going.",
    realTalk: "The cozy part is real — that's not a bit, people actually do feel it. The chaos part is also real, and it's usually contained to one or two specific spots, not the whole room. You don't need a system. You need one small, achievable win.",
    winnieSays: "Pick one surface — just one — and get it fully clear. Not organized, not perfect. Just clear. The rest of the room can stay exactly as cozy as it already is.",
    shareHook: "Tag someone whose home feels amazing and has one secret corner",
    ctaLabel: 'Start with one small, achievable win',
    ctaHref: '/kitchen/how-to-organize-a-small-fridge/',
    shareBody: "Verdict: The Cozy Chaos Curator. The warmth is real — start with one small, achievable win, not a whole system.",
  },
  'stealth-perfectionist': {
    id: 'stealth-perfectionist',
    name: 'The Stealth Perfectionist',
    roastLine: "From the doorway, this space is a masterpiece. Open any cabinet and you've entered a different, more honest documentary. The system is beautiful. The system also requires a full night's sleep to operate correctly.",
    realTalk: "Your system works when conditions are perfect, which is exactly the problem — Tuesday night after a long day is the actual test, and that's when it collapses. The fix isn't a better system. It's a lazier version of the one you already have.",
    winnieSays: "Build the tired version of your system on purpose — the one that still works when you just want to drop everything and deal with it later. It should survive a bad day, not just a good one.",
    shareHook: "Tag someone whose cabinets tell a very different story than their shelves",
    ctaLabel: 'Build a system that survives a bad day',
    ctaHref: '/home-office/small-home-office-setup-guide/',
    shareBody: "Verdict: The Stealth Perfectionist. Beautiful from the doorway, honest behind the cabinet — build the lazy version of your system.",
  },
};

/**
 * Score a Roast My Space submission.
 * @param {string[]} selectedIds — confession ids the reader checked
 * @returns {{ type: object, tally: Record<string, number>, isTie: boolean, tiedWith: string[] }}
 */
export function scoreRoast(selectedIds) {
  const tally = { 'clutter-monarch': 0, 'serial-starter': 0, 'cozy-chaos': 0, 'stealth-perfectionist': 0 };
  for (const id of selectedIds) {
    const confession = CONFESSIONS.find((c) => c.id === id);
    if (confession) tally[confession.type]++;
  }
  const max = Math.max(...Object.values(tally));
  const winners = Object.entries(tally).filter(([, count]) => count === max).map(([key]) => key);
  const winner = winners[0];
  const isTie = max > 0 && winners.length > 1;
  return {
    type: TYPES[winner],
    tally,
    isTie,
    tiedWith: isTie ? winners.slice(1).map((key) => TYPES[key].name) : [],
  };
}

/**
 * Validate that at least one confession is checked.
 * @param {string[]} selectedIds
 * @returns {string[]}
 */
export function validateRoastAnswers(selectedIds) {
  if (!selectedIds || selectedIds.length === 0) {
    return ['Check at least one box — even one honest confession is enough to start.'];
  }
  return [];
}
