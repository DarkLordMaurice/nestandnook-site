import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { SITE } from '../config';
import { HUBS } from '../hubs';

// llms-full.txt — same index as llms.txt, plus the target keyword for every
// page. Kept as a second, separate file per the llms.txt convention (a
// lightweight nav file + a fuller reference file) rather than one that
// tries to do both jobs.
export const GET: APIRoute = async () => {
  const reviews = await getCollection('reviews');
  const recipes = await getCollection('recipes');
  const posts = await getCollection('blog');

  const byHub = (hub: string) => reviews.filter((r) => r.data.hub === hub);

  const lines: string[] = [];
  lines.push(`# ${SITE.brand} — Full Content Index`);
  lines.push('');
  lines.push(`> ${SITE.tagline}`);
  lines.push('');

  for (const hubKey of Object.keys(HUBS)) {
    const hub = HUBS[hubKey];
    const pages = byHub(hubKey);
    if (pages.length === 0) continue;
    lines.push(`## ${hub.name}`);
    lines.push('');
    for (const r of pages) {
      lines.push(`### ${r.data.title}`);
      lines.push(`URL: ${SITE.url}/${hubKey}/${r.slug}/`);
      lines.push(`Target keyword: ${r.data.primaryKeyword}`);
      lines.push(`Summary: ${r.data.description}`);
      lines.push('');
    }
  }

  if (recipes.length > 0) {
    lines.push('## Recipes');
    lines.push('');
    for (const r of recipes) {
      lines.push(`### ${r.data.title}`);
      lines.push(`URL: ${SITE.url}/recipes/${r.slug}/`);
      lines.push(`Target keyword: ${r.data.primaryKeyword}`);
      lines.push(`Summary: ${r.data.description}`);
      lines.push('');
    }
  }

  if (posts.length > 0) {
    lines.push("## Winnie's Notes (blog)");
    lines.push('');
    for (const p of posts) {
      lines.push(`### ${p.data.title}`);
      lines.push(`URL: ${SITE.url}/blog/${p.slug}/`);
      if (p.data.primaryKeyword) lines.push(`Target keyword: ${p.data.primaryKeyword}`);
      lines.push(`Summary: ${p.data.description}`);
      lines.push('');
    }
  }

  return new Response(lines.join('\n') + '\n', {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
