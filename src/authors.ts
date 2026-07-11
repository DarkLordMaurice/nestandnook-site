// Editorial identity for E-E-A-T. "Faceless" is fine; "authorless" is not.
// Keep bios true. Do not invent certifications or imply hands-on testing.
export interface Author {
  id: string;
  name: string;
  role: string;
  bio: string;
  links?: { label: string; href: string }[];
}

export const AUTHORS: Record<string, Author> = {
  editorial: {
    id: 'editorial',
    name: 'Nest & Nook Editorial',
    role: 'Research & Reviews',
    bio: 'Nest & Nook Editorial compares public product specifications and recurring patterns in buyer feedback, then organizes recommendations around small-space fit, measurable constraints, and honest trade-offs. The team does not claim hands-on testing unless a page explicitly documents it.',
    links: [],
  },
  maurice: {
    id: 'maurice',
    name: 'Maurice',
    role: 'Founder & Publisher',
    bio: 'Founder and publisher of Nest & Nook. Maurice sets the editorial standards, reviews the site’s guides before publication, and is the accountable editor of record.',
    links: [],
  },
  staff: {
    id: 'staff',
    name: 'the Nest & Nook Staff',
    role: 'Recipe Development',
    bio: 'Recipes are developed and tested by the Nest & Nook staff using standard, well-established techniques and ratios. Winnie Hollowell is an AI-generated editorial host who narrates tips and voice, not the one who developed or tested a recipe.',
    links: [],
  },
};

// Real named editor of record for public review bylines.
export const DEFAULT_AUTHOR = AUTHORS.maurice;

// Credited author for recipe bylines — recipes are a team/process credit,
// not an individual one. See Character-Bible.md: Winnie never claims to
// have personally developed or tested a recipe.
export const RECIPE_AUTHOR = AUTHORS.staff;
