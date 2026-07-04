// Hub registry — pillar pages for the hub-and-spoke topic maps.
// Pulled into its own module (not inline in [hub]/index.astro) so it's
// reliably available to both getStaticPaths and the page render scope
// during the Cloudflare Pages static build.
//
// `blurb` is the plain, SEO-facing meta description (kept factual/neutral).
// `winnieIntro` is Winnie's on-page narration — the personality layer.
export const HUBS: Record<string, { name: string; blurb: string; winnieIntro: string; hero: string; heroAlt: string }> = {
  'home-office': {
    name: 'Home Office & Ergonomics',
    blurb: 'Affordable upgrades that fix a cramped, uncomfortable desk — footrests, stands, cable management, lighting, and full setup builds.',
    winnieIntro: "I've rearranged this desk of mine more times than I can count, and every single fix that actually stuck lives in this corner of the site. No overpriced fantasy setups — just the footrests, stands, and cable wrangling that turn a cramped desk into somewhere you don't mind spending your whole day.",
    hero: '/winnie/office-hero.jpg',
    heroAlt: "Winnie Hollowell perched on her desk with a mug that reads 'make beautiful things,' surrounded by her gallery wall and plants",
  },
  'kitchen': {
    name: 'Small-Space Kitchen Gear',
    blurb: 'Space-saving gadgets and tools for tiny kitchens and apartments. Guides publishing soon.',
    winnieIntro: "A tiny kitchen taught me more about efficiency than any office ever did. I'm building this section out with the gadgets that earn their cabinet space — check back soon.",
    hero: '/winnie/kitchen-hero.jpg',
    heroAlt: 'Winnie Hollowell stirring a pot on the stove in her small, plant-filled kitchen',
  },
};
