// Hub registry — pillar pages for the hub-and-spoke topic maps.
// Pulled into its own module (not inline in [hub]/index.astro) so it's
// reliably available to both getStaticPaths and the page render scope
// during the Cloudflare Pages static build.
//
// `blurb` is the plain, SEO-facing meta description (kept factual/neutral).
// `winnieIntro` is Winnie's on-page narration — the personality layer.
export const HUBS: Record<string, { name: string; blurb: string; winnieIntro: string; winniePhoto: string; hero: string; heroAlt: string }> = {
  'home-office': {
    name: 'Home Office & Ergonomics',
    blurb: 'Affordable upgrades that fix a cramped, uncomfortable desk — footrests, stands, cable management, lighting, and full setup builds.',
    winnieIntro: "I've read approximately one million \"is this desk hack real or just aesthetic\" arguments in review sections, and I have Opinions. This corner of the site is the distilled version — no overpriced fantasy setups, just the footrests, stands, and cable wrangling that solve the specific, annoying problem you actually have.",
    winniePhoto: '/winnie/headshot-v4-1.jpg',
    hero: '/winnie/office-hero.jpg',
    heroAlt: "Winnie Hollowell perched on a desk with a mug that reads 'make beautiful things,' surrounded by a gallery wall and plants",
  },
  'kitchen': {
    name: 'Small-Space Kitchen Gear',
    blurb: 'Space-saving gadgets and tools for tiny kitchens and apartments. Guides publishing soon.',
    winnieIntro: "Small kitchens turn people either very efficient or very feral, and I respect both outcomes. I'm building this section out with the gadgets that earn their cabinet space when every inch is under negotiation — check back soon.",
    winniePhoto: '/winnie/headshot-v4-2.jpg',
    hero: '/winnie/kitchen-hero.jpg',
    heroAlt: 'Winnie Hollowell stirring a pot on the stove in a small, plant-filled kitchen',
  },
};
