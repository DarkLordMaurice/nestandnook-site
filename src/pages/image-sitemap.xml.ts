import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { SITE } from '../config';

// Separate image sitemap using the standard sitemap image extension
// (https://www.google.com/schemas/sitemap-image/1.1) — every content page's
// hero/card image, wired up so image search can index them without relying
// on crawling + parsing each page's <img> tags. Kept as its own file (not
// merged into sitemap.xml) since it only needs to change contents. Hand-rolled
// for the same reason as sitemap.xml.ts: @astrojs/sitemap is out of the
// build (see astro.config.mjs).
export const GET: APIRoute = async () => {
  const reviews = await getCollection('reviews');
  const recipes = await getCollection('recipes');
  const posts = await getCollection('blog');

  type Entry = { loc: string; images: { url: string; title?: string }[] };

  const entries: Entry[] = [];

  for (const r of reviews) {
    const images: { url: string; title?: string }[] = [];
    if (r.data.image) images.push({ url: `${SITE.url}${r.data.image}`, title: r.data.title });
    for (const p of r.data.products) {
      if (p.image) images.push({ url: `${SITE.url}${p.image}`, title: p.name });
      if (p.winnieImage) images.push({ url: `${SITE.url}${p.winnieImage}` });
    }
    if (images.length > 0) entries.push({ loc: `${SITE.url}/${r.data.hub}/${r.slug}/`, images });
  }

  for (const r of recipes) {
    const images: { url: string; title?: string }[] = [{ url: `${SITE.url}${r.data.image}`, title: r.data.title }];
    if (r.data.winnieImage) images.push({ url: `${SITE.url}${r.data.winnieImage}` });
    entries.push({ loc: `${SITE.url}/recipes/${r.slug}/`, images });
  }

  for (const p of posts) {
    const images: { url: string; title?: string }[] = [{ url: `${SITE.url}${p.data.image}`, title: p.data.title }];
    entries.push({ loc: `${SITE.url}/blog/${p.slug}/`, images });
  }

  const body = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
${entries
  .map(
    (e) => `  <url>
    <loc>${e.loc}</loc>
${e.images
  .map(
    (img) => `    <image:image>
      <image:loc>${img.url}</image:loc>${img.title ? `\n      <image:title>${img.title.replace(/&/g, '&amp;')}</image:title>` : ''}
    </image:image>`
  )
  .join('\n')}
  </url>`
  )
  .join('\n')}
</urlset>
`;

  return new Response(body, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
