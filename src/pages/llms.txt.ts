import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { SITE, isAmazonAssociatesApproved } from '../config';
import { HUBS } from '../hubs';

export const GET: APIRoute = async () => {
  const reviews = await getCollection('reviews');
  const recipes = await getCollection('recipes');
  const posts = await getCollection('blog');
  const byHub = (hub: string) => reviews.filter((r) => r.data.hub === hub);
  const lines: string[] = [`# ${SITE.brand}`, '', `> ${SITE.tagline}`, ''];

  lines.push(`${SITE.brand} is an independently run content site covering home-office ergonomics, small-space kitchen gear, recipes, and practical guides. Product recommendations are research-led and based on public specifications and reported buyer experience, not first-party lab testing. Winnie Hollowell is a disclosed virtual AI host, not a real product tester.`);
  lines.push('');
  lines.push(isAmazonAssociatesApproved
    ? 'Monetization status: approved Amazon Associates participant; qualifying retailer links may earn commissions.'
    : 'Monetization status: Amazon Associates application pending; current Amazon links are untagged and do not earn commissions.');
  lines.push('');

  for (const hubKey of Object.keys(HUBS)) {
    const hub = HUBS[hubKey];
    const pages = byHub(hubKey);
    if (!pages.length) continue;
    lines.push(`## ${hub.name}`, '');
    for (const r of pages) lines.push(`- [${r.data.title}](${SITE.url}/${hubKey}/${r.slug}/): ${r.data.description}`);
    lines.push('');
  }

  if (recipes.length) {
    lines.push('## Recipes', '');
    for (const r of recipes) lines.push(`- [${r.data.title}](${SITE.url}/recipes/${r.slug}/): ${r.data.description}`);
    lines.push('');
  }
  if (posts.length) {
    lines.push('## Off the Clock and Guides', '');
    for (const p of posts) lines.push(`- [${p.data.title}](${SITE.url}/blog/${p.slug}/): ${p.data.description}`);
    lines.push('');
  }

  lines.push('## Trust and contact', '');
  lines.push(`- [About ${SITE.brand}](${SITE.url}/about/): Ownership, editorial process, and Winnie disclosure.`);
  lines.push(`- [Editorial Standards](${SITE.url}/editorial-standards/): Research, claims, corrections, and refresh rules.`);
  lines.push(`- [Affiliate Disclosure](${SITE.url}/disclosure/): Current monetization status and retailer-link policy.`);
  lines.push(`- [Privacy Policy](${SITE.url}/privacy/): Data, hosting, cookies, and third-party links.`);
  lines.push(`- [Terms of Use](${SITE.url}/terms/): Site-use terms and content limitations.`);
  lines.push(`- [Contact](${SITE.url}/contact/): How to report errors or contact the publisher.`);
  lines.push('', '## Optional', '', `- [Full content index](${SITE.url}/llms-full.txt): Every indexed page with its target keyword.`);

  return new Response(lines.join('\n') + '\n', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
