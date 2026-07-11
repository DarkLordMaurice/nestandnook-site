interface HeroAccent { src: string; alt: string; tilt?: 'left' | 'right'; }

export const HUBS: Record<string, {
  name: string; eyebrow: string; blurb: string; winnieIntro: string; winniePhoto: string;
  hero: string; heroAlt: string; heroAccents: HeroAccent[];
}> = {
  'home-office': {
    name: 'Home Office & Ergonomics',
    eyebrow: 'No overpriced fantasy setups',
    blurb: 'Affordable upgrades that fix a cramped, uncomfortable desk — footrests, stands, cable management, lighting, and full setup builds.',
    winnieIntro: "I've read approximately one million \"is this desk hack real or just aesthetic\" arguments in review sections, and I have Opinions. This corner of the site is the distilled version — no overpriced fantasy setups, just the footrests, stands, and cable wrangling that solve the specific, annoying problem you actually have.",
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
    eyebrow: 'Every inch, under negotiation',
    blurb: 'Space-saving tools for tiny kitchens and apartments — cabinet storage, counter prep, multi-function appliances, pantry organization, and complete setup guides.',
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
  // Pack implementation. The 3 image paths below (hero + 2 accents) are
  // RESERVED, not yet generated — same as every other page-level hero in
  // this batch, this hub landing page will not visibly work until Maurice
  // generates and places these 3 files via ChatGPT. See the master image
  // prompt doc for the exact prompts.
  'pet-care': {
    name: 'Small-Space Pet Care',
    eyebrow: 'Cats, dogs, and not much square footage',
    blurb: 'Litter, cleanup, feeding, enrichment, and renter-friendly setups for apartment cats and dogs — picks organized by what actually fits a small home, not what looks best in a big one.',
    winnieIntro: "I don't have a cat or a dog myself — I'm not going to pretend I do — but I read an unreasonable number of apartment pet setups, and the pattern is always the same: most pet gear is designed for a house with a mudroom, and most of us don't have one. This section is the small-space version — litter and odor control, hair and cleanup, feeding and hydration, enrichment, and gear that won't cost you a security deposit.",
    winniePhoto: '/winnie/headshot-v4-3.jpg',
    hero: '/winnie/pet-care-hero.jpg',
    heroAlt: 'Winnie Hollowell in a small, tidy apartment living room set up for a cat and a dog, with space-conscious pet gear nearby.',
    heroAccents: [
      { src: '/winnie/pet-care-side.jpg', alt: 'Winnie assessing a compact apartment corner set up for pet care.' },
      { src: '/winnie/winnie-pet-care-small-space-check.jpg', alt: 'Winnie measuring floor space for pet gear in a small apartment.' },
    ],
  },
};
