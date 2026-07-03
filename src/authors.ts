// Editorial identity for E-E-A-T. Post-2026, Google rewards demonstrable authorship.
// "Faceless" is fine; "authorless" is not. Every page carries a byline that links here.
//
// IMPORTANT (honesty + E-E-A-T): keep bios TRUE. Do not invent certifications or credentials.
// We do NOT claim hands-on product testing — we don't buy and test every item ourselves.
// Base authority on real, verifiable things: careful review-aggregation methodology (reading
// verified buyer reviews, comparing specs, weighing what reviewers actually report), years
// following the category, transparency about how picks are made. Maurice = publisher/editor
// of record. Never write copy that implies physical testing that didn't happen — that's both
// dishonest and a real Amazon Associates / FTC risk.

export interface Author {
  id: string;
  name: string;
  role: string;
  bio: string;
  // Fill these in with real handles/links when available — they strengthen E-E-A-T.
  links?: { label: string; href: string }[];
}

export const AUTHORS: Record<string, Author> = {
  editorial: {
    id: 'editorial',
    name: 'The Nest & Nook Team',        // replace with a real named editor when you have one
    role: 'Editorial & Reviews',
    bio: 'We research home office and small-space kitchen gear the tedious way: digging through verified buyer reviews, comparing specs that actually matter, and ranking picks by who each product genuinely suits — not by commission. Every guide states how we chose and what the trade-offs are.',
    links: [],
  },
  maurice: {
    id: 'maurice',
    name: 'Maurice',                     // publisher / editor of record — put your preferred byline
    role: 'Founder & Publisher',
    bio: 'Founder of Nest & Nook. Sets the editorial standards below and reviews every guide before it publishes.',
    links: [],
  },
};

export const DEFAULT_AUTHOR = AUTHORS.editorial;
