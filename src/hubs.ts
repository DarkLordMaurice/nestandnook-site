// Hub registry — pillar pages for the hub-and-spoke topic maps.
// Pulled into its own module (not inline in [hub]/index.astro) so it's
// reliably available to both getStaticPaths and the page render scope
// during the Cloudflare Pages static build.
//
// `blurb` is the plain, SEO-facing meta description (kept factual/neutral).
// `winnieIntro` is Winnie's on-page narration — the personality layer.
// pos was for the old absolute-position overlap collage (retired — see
// global.css .collage-row comment). Photos now render in a plain left-to-
// right row via HeroCollage, so only src/alt/tilt matter.
interface HeroAccent { src: string; alt: string; tilt?: 'left' | 'right'; }

// `eyebrow` is the small badge line above the H1 on the hub landing page
// (src/pages/[hub]/index.astro). Added 2026-07-10 — it used to just repeat
// `name` verbatim (badge and headline showing the identical string), which
// Maurice flagged as a pointless redundant box. This is a short Winnie
// aside instead — same voice as `winnieIntro`, just a one-line teaser of it
// rather than a category label restating the headline.
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
    heroAlt: "Winnie Hollowell perched on a desk with a mug that reads 'make beautiful things,' surrounded by a gallery wall and plants",
    heroAccents: [
      { src: '/winnie/winnie-office-standing-desk.jpg', alt: 'Winnie at her standing desk mid-adjustment' },
      { src: '/winnie/winnie-office-wide-overview.jpg', alt: "A wide view of Winnie's actual gallery-wall home office" },
    ],
  },
  'kitchen': {
    name: 'Small-Space Kitchen Gear',
    eyebrow: 'Every inch, under negotiation',
    blurb: 'Space-saving gadgets and tools for tiny kitchens and apartments — storage, multi-function appliances, pantry organization, and full setup guides.',
    winnieIntro: "Small kitchens turn people either very efficient or very feral, and I respect both outcomes. This section covers the gadgets that earn their cabinet space when every inch is under negotiation — more clusters landing as we build this hub out.",
    winniePhoto: '/winnie/headshot-v4-2.jpg',
    hero: '/winnie/kitchen-hero.jpg',
    heroAlt: 'Winnie Hollowell stirring a pot on the stove in a small, plant-filled kitchen',
    heroAccents: [
      { src: '/winnie/kitchen-side.jpg', alt: 'Winnie working the counter from a side angle in her kitchen' },
      { src: '/winnie/winnie-kitchen-cabinet-reach.jpg', alt: 'Winnie reaching into a packed kitchen cabinet' },
    ],
  },
};
