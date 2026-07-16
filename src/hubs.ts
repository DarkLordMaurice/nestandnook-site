interface HeroAccent { src: string; alt: string; tilt?: 'left' | 'right'; }

export const HUBS: Record<string, {
  name: string; eyebrow: string; blurb: string; winnieIntro: string; winniePhoto: string;
  hero: string; heroAlt: string; heroAccents: HeroAccent[];
}> = {
  'home-office': {
    name: 'Home Office & Ergonomics',
    eyebrow: 'Your desk is working against you. Let\'s fix that.',
    blurb: 'You\'re doing real work at a desk that wasn\'t designed for real work. Here are the upgrades that actually change that — no overpriced fantasy setups, no guessing.',
    winnieIntro: "I've read approximately one million \"is this desk hack real or just aesthetic\" arguments in review sections, and I have Opinions. This corner of the site is the distilled version — no overpriced fantasy setups, just the monitor setups, lighting, and cable wrangling that solve the specific, annoying problem you actually have.",
    winniePhoto: '/winnie/headshot-v4-1.jpg',
    hero: '/winnie/office-hero.jpg',
    heroAlt: "Winnie Hollowell in a warm, compact home office surrounded by practical desk tools and plants.",
    heroAccents: [
      { src: '/winnie/winnie-office-standing-desk.jpg', alt: 'Winnie adjusting a standing desk in a compact home office.' },
      { src: '/winnie/winnie-office-wide-overview.jpg', alt: 'A wide view of a compact, gallery-wall home office.' },
    ],
  },
  'kitchen': {
    name: 'Small-Space Kitchen Gear',
    eyebrow: 'You cook real food. Your kitchen has opinions about that.',
    blurb: 'You cook real meals in a space that wasn\'t built for it. This is the gear that actually earns cabinet space when you don\'t have any to spare.',
    winnieIntro: "Small kitchens turn people either very efficient or very feral, and I respect both outcomes. This section covers the gadgets that earn their cabinet space when every inch is under negotiation — more clusters landing as we build this hub out.",
    winniePhoto: '/winnie/headshot-v4-2.jpg',
    hero: '/winnie/kitchen-hero.jpg',
    heroAlt: 'Winnie Hollowell cooking in a small, plant-filled kitchen with practical storage nearby.',
    heroAccents: [
      { src: '/winnie/kitchen-side.jpg', alt: 'Winnie working at a compact kitchen counter from a side angle.' },
      { src: '/winnie/winnie-kitchen-cabinet-reach.jpg', alt: 'Winnie reaching into a compact kitchen cabinet.' },
    ],
  },
  // Pet Care hub added 2026-07-11 alongside the Pet Care Full-Hub Completion
  // Pack implementation. Hero + 2 accents use the "PENDING" sentinel
  // (matching the review-page image: "PENDING" pattern) — HeroCollage.astro
  // renders a same-size camera placeholder tile for any photo with
  // src: "PENDING" instead of a broken <img>. Real filenames stay logged in
  // Winnie-Photo-Queue.md / the master prompt doc; swap each `src` from
  // "PENDING" back to its real path once Maurice delivers that photo.
  'pet-care': {
    name: 'Small-Space Pet Care',
    eyebrow: 'You\'d reorganize everything for them if you could.',
    blurb: 'Most pet gear is designed for a house with a mudroom. You don\'t have one. This section is the small-space version — everything organized by what actually fits, not what photographs well in a bigger place.',
    winnieIntro: "I don't have a cat or a dog myself — I'm not going to pretend I do — but I read an unreasonable number of apartment pet setups, and the pattern is always the same: most pet gear is designed for a house with a mudroom, and most of us don't have one. This section is the small-space version — litter and odor control, hair and cleanup, feeding and hydration, enrichment, and gear that won't cost you a security deposit.",
    winniePhoto: '/winnie/headshot-v4-3.jpg',
    hero: 'PENDING',
    heroAlt: 'Winnie Hollowell in a small, tidy apartment living room set up for a cat and a dog, with space-conscious pet gear nearby.',
    heroAccents: [
      { src: 'PENDING', alt: 'Winnie assessing a compact apartment corner set up for pet care.' },
      { src: 'PENDING', alt: 'Winnie measuring floor space for pet gear in a small apartment.' },
    ],
  },
  // Garage hub added 2026-07-11, topic map at config/niches/garage.json.
  // Hero + accents use the "PENDING" sentinel like Pet Care above.
  'garage': {
    name: 'Small-Space Garage & Storage',
    eyebrow: 'The car still has to fit.',
    blurb: 'Most garage organization advice is written for a garage three times the size of yours. This isn\'t that. Wall storage, tool systems, seasonal rotation, and workspaces built around the one non-negotiable: the car still has to fit at the end of it.',
    winnieIntro: "Most garage-organization content is written for a garage the size of a small warehouse. This section is for the rest of us: a single-car garage, a shared driveway spot, a storage locker doing the job a garage would — where the one non-negotiable rule is the car still has to fit at the end of it.",
    winniePhoto: '/winnie/headshot-v4-4.jpg',
    hero: '/winnie/garage-hero.jpg',
    heroAlt: 'Winnie Hollowell measuring wall space in a small, single-car garage before installing storage.',
    heroAccents: [
      { src: '/winnie/garage-stud-finder.jpg', alt: 'Winnie using a stud finder along a garage wall.' },
      { src: '/winnie/garage-overhead-clearance.jpg', alt: 'Winnie assessing overhead ceiling clearance in a small garage.' },
    ],
  },
};
