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

// Build a tagged Amazon SEARCH RESULTS link from a plain-text query — added
// 2026-07-10 for generic recipe ingredients (flour, eggs, a specific spice)
// where there's no single canonical product to point at and picking one
// specific ASIN would mean guessing. This never fabricates a product; it's
// Amazon's real search endpoint with our tag attached, same mechanism as
// clicking "search" on amazon.com. Use amazonLink(asin) instead whenever a
// specific product has actually been looked up and confirmed.
export function amazonSearchLink(query: string): string {
  return `https://${SITE.amazonMarketplace}/s?k=${encodeURIComponent(query)}&tag=${SITE.amazonAssociateTag}`;
}
