// Single source of brand, legal-status, and retailer-link configuration.
// Keep status flags accurate. Do not switch Amazon Associates to "approved"
// or add a live tracking tag until the account is actually approved.
export type AmazonAssociatesStatus = 'pending' | 'approved' | 'paused';

export const SITE = {
  brand: 'Nest & Nook',
  tagline: 'Small-space guides, reviews, recipes, and free visual planning tools.',
  url: 'https://nestandnook.org',
  contactEmail: 'hello@nestandnook.org',
  contactEmailVerified: false, // Set true only after routing/mailbox is tested.
  operatorRegion: 'Nevada, United States',
  amazonAssociatesStatus: 'pending' as AmazonAssociatesStatus,
  amazonAssociateTag: 'CHANGEME-20',
  amazonMarketplace: 'www.amazon.com',
  displayAdsActive: false,
  analyticsActive: false,
};

export const isAmazonAssociatesApproved =
  SITE.amazonAssociatesStatus === 'approved' &&
  Boolean(SITE.amazonAssociateTag) &&
  !SITE.amazonAssociateTag.startsWith('CHANGEME');

export const DISCLOSURE = {
  ftc: isAmazonAssociatesApproved
    ? 'This page contains affiliate links. If you buy through them, we may earn a commission at no extra cost to you.'
    : 'This page may link to retailers for convenience. Our Amazon Associates application is still pending, so current Amazon links are untagged and do not earn us a commission.',
  associate: isAmazonAssociatesApproved
    ? 'As an Amazon Associate, we earn from qualifying purchases.'
    : 'Amazon Associates status: application pending. We are not currently earning Amazon commissions.',
};

export const AMAZON_LINK_REL = isAmazonAssociatesApproved
  ? 'nofollow sponsored noopener'
  : 'nofollow noopener';

export const AMAZON_LINK_NOTE = isAmazonAssociatesApproved
  ? 'Amazon paid link. We may earn a commission from qualifying purchases.'
  : 'Amazon retailer link. No Amazon commission is currently earned while our application is pending.';

function addAssociateTag(url: URL): string {
  if (isAmazonAssociatesApproved) {
    url.searchParams.set('tag', SITE.amazonAssociateTag);
  }
  return url.toString();
}

// Build an Amazon product link from a verified ASIN. Never fabricate an ASIN.
export function amazonLink(asin: string): string {
  const cleanAsin = asin.trim();
  if (!/^[A-Z0-9]{10}$/.test(cleanAsin)) {
    throw new Error(`Invalid Amazon ASIN: ${asin}`);
  }
  return addAssociateTag(new URL(`https://${SITE.amazonMarketplace}/dp/${cleanAsin}/`));
}

// Build an Amazon search-results link for generic ingredients/categories.
// While Associates approval is pending, the link remains untagged.
export function amazonSearchLink(query: string): string {
  const url = new URL(`https://${SITE.amazonMarketplace}/s`);
  url.searchParams.set('k', query.trim());
  return addAssociateTag(url);
}
