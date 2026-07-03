// Hub registry — pillar pages for the hub-and-spoke topic maps.
// Pulled into its own module (not inline in [hub]/index.astro) so it's
// reliably available to both getStaticPaths and the page render scope
// during the Cloudflare Pages static build.
export const HUBS: Record<string, { name: string; blurb: string }> = {
  'home-office': {
    name: 'Home Office & Ergonomics',
    blurb: 'Affordable upgrades that fix a cramped, uncomfortable desk — footrests, stands, cable management, lighting, and full setup builds.',
  },
  'kitchen': {
    name: 'Small-Space Kitchen Gear',
    blurb: 'Space-saving gadgets and tools for tiny kitchens and apartments. Guides publishing soon.',
  },
};
