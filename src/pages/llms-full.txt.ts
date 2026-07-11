import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { SITE, isAmazonAssociatesApproved } from '../config';
import { HUBS } from '../hubs';

export const GET: APIRoute = async () => {
  const reviews = await getCollection('reviews');
  const recipes = await getCollection('recipes');
  const posts = await getCollection('blog');
  const lines: string[] = [
    `# ${SITE.brand} — Full Content Index`,
    '',
    `> ${SITE.tagline}`,
    '',
    `Monetization status: ${isAmazonAssociatesApproved ? 'Amazon Associates approved' : 'Amazon Associates application pending; Amazon links are currently untagged'}.`,
    '',
  ];

  for (const hubKey of Object.keys(HUBS)) {
    const pages = reviews.filter((r) => r.data.hub === hubKey);
    if (!pages.length) continue;
    lines.push(`## ${HUBS[hubKey].name}`, '');
    for (const r of pages) {
      lines.push(`### ${r.data.title}`);
      lines.push(`URL: ${SITE.url}/${hubKey}/${r.slug}/`);
      lines.push(`Target keyword: ${r.data.primaryKeyword}`);
      lines.push(`Summary: ${r.data.description}`);
      lines.push(`Published: ${r.data.publishDate.toISOString().slice(0, 10)}`);
      lines.push(`Last reviewed: ${(r.data.updatedDate ?? r.data.publishDate).toISOString().slice(0, 10)}`);
      lines.push('');
    }
  }

  if (recipes.length) {
    lines.push('## Recipes', '');
    for (const r of recipes) {
      lines.push(`### ${r.data.title}`);
      lines.push(`URL: ${SITE.url}/recipes/${r.slug}/`);
      lines.push(`Target keyword: ${r.data.primaryKeyword}`);
      lines.push(`Summary: ${r.data.description}`);
      lines.push(`Last reviewed: ${(r.data.updatedDate ?? r.data.publishDate).toISOString().slice(0, 10)}`);
      lines.push('');
    }
  }

  if (posts.length) {
    lines.push('## Off the Clock and Guides', '');
    for (const p of posts) {
      lines.push(`### ${p.data.title}`);
      lines.push(`URL: ${SITE.url}/blog/${p.slug}/`);
      if (p.data.primaryKeyword) lines.push(`Target keyword: ${p.data.primaryKeyword}`);
      lines.push(`Summary: ${p.data.description}`);
      lines.push(`Last reviewed: ${(p.data.updatedDate ?? p.data.publishDate).toISOString().slice(0, 10)}`);
      lines.push('');
    }
  }

  return new Response(lines.join('\n') + '\n', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
