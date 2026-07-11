# Nest & Nook site (Astro → Cloudflare Pages)

Static small-space home-office, kitchen, recipe, and editorial content site.
Review and buying-guide pages live in `src/content/reviews/*.md` and render through `src/pages/[hub]/[...slug].astro`.

## Local verification

```bash
npm install
npm run audit:readiness
npm run audit:readiness:strict
npm run build
npm run preview
```

`pagefind` must remain a production dependency because Cloudflare may omit dev dependencies during install.

## Deploy

Push to `main` → Cloudflare Pages builds with `npm run build` and serves `dist/`.
Before pushing, verify the working tree, add explicit file paths only, and inspect the cache-busted live pages after deployment.

## Main configuration

- Brand, domain, contact email, Amazon status/tag, and disclosures: `src/config.ts`
- Content schemas: `src/content/config.ts`
- Shared page layout and entity graph: `src/layouts/BaseLayout.astro`
- Review pages: `src/content/reviews/*.md`
- Blog posts: `src/content/blog/*.md`
- Recipes: `src/content/recipes/*.md`

## Compliance

The Amazon application is pending until `src/config.ts` is deliberately changed after approval. While pending, Amazon links remain untagged and the site must not claim it earns Amazon commissions.
Never fabricate ASINs, prices, ratings, testing, credentials, or first-person Winnie ownership/use.
