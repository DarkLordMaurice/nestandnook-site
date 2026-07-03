# DwellGear site (Astro → Cloudflare Pages)

Static affiliate content site. Pages live in `src/content/reviews/*.md` and render through `src/pages/[hub]/[...slug].astro`.

## Local
```
npm install
npm run dev      # preview at localhost:4321
npm run build    # outputs dist/
```

## Deploy
Push to `main` → Cloudflare Pages auto-builds (build command `npm run build`, output dir `dist`).

## Where to change things
- Brand / domain / Amazon tag / disclosures → `src/config.ts`
- Disclosures render automatically via `BaseLayout.astro` → `AffiliateDisclosure.astro`
- New page = new markdown file in `src/content/reviews/` (produced by the page-builder skill)

## Compliance is structural
Every content page renders the FTC + Amazon Associate disclosures via the layout, and `rel="nofollow sponsored"` on affiliate links, so pages pass the compliance-gate by construction. Don't bypass the layout.
