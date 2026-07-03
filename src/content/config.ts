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
    pageType: z.enum(['comparison', 'roundup', 'single_review', 'buying_guide', 'setup_build']),
    publishDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    disclosure: z.boolean().default(true), // must be true — compliance-gate checks it
    schemaType: z.enum(['ItemList', 'Product', 'Article']).default('ItemList'),
    ogImage: z.string().optional(),
    // Product list drives the comparison table AND the JSON-LD ItemList.
    products: z.array(z.object({
      name: z.string(),
      asin: z.string(),                    // resolved to a tagged link at build
      bestFor: z.string(),                 // 'Best overall' / 'Best budget' / segment
      blurb: z.string(),
      pros: z.array(z.string()).optional(),
      cons: z.array(z.string()).optional(),
    })).default([]),
    internalLinks: z.array(z.object({ label: z.string(), href: z.string() })).default([]),
  }),
});

export const collections = { reviews };
