import { defineCollection, z } from 'astro:content';

// Content collection schema for review/roundup/comparison pages.
// page-builder writes these; seo-optimizer finalizes title/description/schema.
const reviews = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string().max(65),            // title tag
    description: z.string().max(160),      // meta description
    primaryKeyword: z.string(),
    hub: z.string(),                       // e.g. 'home-office'
    pageType: z.enum(['comparison', 'roundup', 'single_review', 'buying_guide', 'setup_build', 'how_to', 'product_page', 'lifestyle', 'pillar']),
    publishDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    disclosure: z.boolean().default(true), // must be true — compliance-gate checks it
    schemaType: z.enum(['ItemList', 'Product', 'Article']).default('ItemList'),
    ogImage: z.string().optional(),
    // Card thumbnail for homepage/hub grids — a Winnie hero/lifestyle shot,
    // NOT a literal product photo (those stay unset per compliance note above
    // until PA-API/sales unlock real product photography). Falls back to the
    // hub's hero image (HUBS[hub].hero) in templates if left unset.
    image: z.string().optional(),
    // Product list drives the comparison table AND the JSON-LD ItemList.
    products: z.array(z.object({
      name: z.string(),
      asin: z.string(),                    // resolved to a tagged link at build
      bestFor: z.string(),                 // 'Best overall' / 'Best budget' / segment
      blurb: z.string(),
      pros: z.array(z.string()).optional(),
      cons: z.array(z.string()).optional(),
      // Real product photo — hold off populating until PA-API unlocks (~3 qualifying
      // sales); sourcing product images without API access risks Amazon Associates
      // image-use terms. Leave unset until then.
      image: z.string().optional(),
      // AI-rendered "Winnie with this product" lifestyle image — used sporadically,
      // NOT on every product. Must be disclosed as AI-rendered for demonstration
      // (see about.astro AI-imagery disclosure + brand-assets/winnie/ prompt kit).
      winnieImage: z.string().optional(),
    })).default([]),
    internalLinks: z.array(z.object({ label: z.string(), href: z.string() })).default([]),
  }),
});

// Blog — Winnie Hollowell's voice. Distinct from the `reviews` collection:
// these are personality-led posts (her opinions, her "here's what I'd do"
// takes), not the SEO cluster roundups/how-tos. She never claims personal
// product testing OR personal ownership/use here — that's not honest, and
// it's a real Amazon Associates / FTC risk. She showcases picks the real
// editorial team compiled from verified buyer reviews. As of 2026-07-03,
// posts no longer repeat the AI/virtual-host disclosure inline (that's a
// one-time explanation on the About page now, not a per-post paragraph) —
// see WinnieByline.astro. Aim for a real 2-4 minute read (~500-800 words)
// that actually digs into its stated topic, not a short generic take.
const blog = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string().max(70),
    description: z.string().max(160),
    publishDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    ogImage: z.string().optional(),
    category: z.string().default('Notes from the nook'),
    image: z.string().default('/winnie/blog-header.jpg'),
    winniePhoto: z.string().optional(), // vary the byline headshot — see WinnieByline.astro
    relatedGuides: z.array(z.object({ label: z.string(), href: z.string() })).default([]),
  }),
});

// Recipes — a distinct traffic channel from reviews/blog. High-search-volume,
// kitchen-adjacent recipe content (schema.org Recipe rich-result eligible).
// Recipes are ORIGINAL content, not "Winnie's family recipes" — she doesn't
// have a kitchen history (she's a disclosed AI/virtual host, see
// Character-Bible.md), so recipe posts must never imply she personally
// developed/tested/inherited them. Framing: developed by the Nest & Nook
// kitchen team using standard, well-established techniques and ratios;
// Winnie narrates the tips/voice layer, same disclosed-host pattern as blog.
// Recipes should link to relevant Kitchen hub product roundups where a real
// verified product page exists (see internalLinks) — that's the whole point
// of this content: it drives search traffic AND cross-sells gear.
const recipes = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string().max(70),
    description: z.string().max(160),
    primaryKeyword: z.string(),
    publishDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    category: z.enum(['breakfast', 'main', 'side', 'dessert', 'snack']),
    cuisine: z.string().default('American'),
    prepTimeMinutes: z.number(),
    cookTimeMinutes: z.number(),
    servings: z.number(),
    difficulty: z.enum(['easy', 'intermediate', 'advanced']).default('easy'),
    image: z.string(),
    imageAlt: z.string(),
    winnieImage: z.string().optional(),  // Winnie-in-kitchen lifestyle shot (AI-rendered; disclosed on the About page, not repeated per-page)
    winnieNote: z.string().optional(),   // Short personality blurb in Winnie's voice about this specific dish — paired with her headshot via WinnieNote.astro
    winnieHeadshot: z.string().optional(), // vary which headshot shows next to winnieNote — don't repeat avatar.jpg on every recipe
    // Ingredients grouped so recipes with e.g. "for the sauce" sub-lists render cleanly.
    ingredientGroups: z.array(z.object({
      groupName: z.string().optional(),  // omit for a single flat list
      items: z.array(z.string()),
    })),
    instructions: z.array(z.object({
      step: z.string(),
    })),
    // Nutrition is an estimate, never a medical/dietary claim — keep it labeled as such
    // in the template, and only include fields we're confident estimating.
    nutrition: z.object({
      calories: z.number().optional(),
      servingSize: z.string().optional(),
    }).optional(),
    tips: z.array(z.string()).default([]),
    faqs: z.array(z.object({ q: z.string(), a: z.string() })).default([]),
    keywords: z.array(z.string()).default([]),
    disclosure: z.boolean().default(true),  // true whenever relatedProducts has affiliate links
    relatedProducts: z.array(z.object({ label: z.string(), href: z.string() })).default([]),
    relatedRecipes: z.array(z.object({ label: z.string(), href: z.string() })).default([]),
  }),
});

export const collections = { reviews, blog, recipes };
