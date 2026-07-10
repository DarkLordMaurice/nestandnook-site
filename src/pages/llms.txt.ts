import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { SITE } from '../config';
import { HUBS } from '../hubs';

// llms.txt — the emerging (2024-2026) convention for giving LLM/AI-answer
// crawlers a clean, curated index of a site instead of making them parse
// full HTML. Hand-rolled and build-time-generated (same pattern as
// sitemap.xml.ts) so it never drifts out of sync as new reviews/recipes/blog
// posts are added — no separate file to remember to update by hand.
export const GET: APIRoute = async () => {
  const reviews = await getCollection('reviews');
  const recipes = await getCollection('recipes');
  const posts = await getCollection('blog');

  const byHub = (hub: string) => reviews.filter((r) => r.data.hub === hub);

  const lines: string[] = [];
  lines.push(`# ${SITE.brand}`);
  lines.push('');
  lines.push(`> ${SITE.tagline}`);
  lines.push('');
  lines.push(
    `${SITE.brand} is an independently run, Amazon Associates–affiliated content site covering home office ergonomics and small-space kitchen gear, plus an original recipe collection. Product picks are compiled by a real editorial team from verified buyer reviews and specs (not first-party lab testing). The on-site host "Winnie Hollowell" is a disclosed, fully virtual AI persona, not a real person — see /about/ for the full disclosure.`
  );
  lines.push('');

  for (const hubKey of Object.keys(HUBS)) {
    const hub = HUBS[hubKey];
    const pages = byHub(hubKey);
    if (pages.length === 0) continue;
    lines.push(`## ${hub.name}`);
    lines.push('');
    for (const r of pages) {
      lines.push(`- [${r.data.title}](${SITE.url}/${hubKey}/${r.slug}/): ${r.data.description}`);
    }
    lines.push('');
  }

  if (recipes.length > 0) {
    lines.push('## Recipes');
    lines.push('');
    for (const r of recipes) {
      lines.push(`- [${r.data.title}](${SITE.url}/recipes/${r.slug}/): ${r.data.description}`);
    }
    lines.push('');
  }

  if (posts.length > 0) {
    lines.push("## Off the Clock (blog)");
    lines.push('');
    for (const p of posts) {
      lines.push(`- [${p.data.title}](${SITE.url}/blog/${p.slug}/): ${p.data.description}`);
    }
    lines.push('');
  }

  lines.push('## About');
  lines.push('');
  lines.push(`- [About ${SITE.brand}](${SITE.url}/about/): Who runs the site, how picks are made, and the Winnie AI-host disclosure.`);
  lines.push(`- [Editorial Standards](${SITE.url}/editorial-standards/): How reviews are researched and ranked.`);
  lines.push(`- [Affiliate Disclosure](${SITE.url}/disclosure/): Amazon Associates relationship.`);
  lines.push('');
  lines.push('## Optional');
  lines.push('');
  lines.push(`- [Full content index](${SITE.url}/llms-full.txt): Every page above with its target keyword included.`);

  return new Response(lines.join('\n') + '\n', {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
