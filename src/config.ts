// Single source of brand + affiliate config. Swap BRAND / domain / tag here only.
export const SITE = {
  brand: 'Nest & Nook',
  tagline: 'Smarter home office & kitchen setups, reviewed and ranked.',
  url: 'https://nestandnook.org',           // registered via Cloudflare, 2026-07-03
  amazonAssociateTag: 'CHANGEME-20',         // Amazon Associates tracking id (set after approval)
  amazonMarketplace: 'www.amazon.com',
};

// Required legal disclosures — rendered automatically by BaseLayout on every page.
export const DISCLOSURE = {
  associate: 'As an Amazon Associate I earn from qualifying purchases.',
  ftc: 'This page contains affiliate links. If you buy through them, we may earn a commission at no extra cost to you.',
};

// Build a tagged Amazon link from an ASIN. Never cloak; always show it's Amazon.
export function amazonLink(asin: string): string {
  return `https://${SITE.amazonMarketplace}/dp/${asin}/?tag=${SITE.amazonAssociateTag}`;
}
