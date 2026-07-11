import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { SITE } from '../config';
import { HUBS } from '../hubs';

export const GET: APIRoute = async () => {
  const reviews = await getCollection('reviews');
  const posts = await getCollection('blog');
  const recipes = await getCollection('recipes');

  const toDateStr = (d?: Date) => (d ? d.toISOString().split('T')[0] : undefined);
  type Entry = { loc: string; lastmod?: string; changefreq: string };

  const staticPages: Entry[] = [
    { loc: '/', changefreq: 'daily' },
    { loc: '/about/', changefreq: 'monthly' },
    { loc: '/contact/', changefreq: 'yearly' },
    { loc: '/editorial-standards/', changefreq: 'monthly' },
    { loc: '/privacy/', changefreq: 'yearly' },
    { loc: '/terms/', changefreq: 'yearly' },
    { loc: '/disclosure/', changefreq: 'yearly' },
    { loc: '/blog/', changefreq: 'daily' },
    { loc: '/guides/', changefreq: 'daily' },
    { loc: '/recipes/', changefreq: 'daily' },
  ];

  const hubPages: Entry[] = Object.keys(HUBS).map((hub) => ({
    loc: `/${hub}/`,
    changefreq: 'weekly',
  }));

  const reviewPages: Entry[] = reviews.map((r) => ({
    loc: `/${r.data.hub}/${r.slug}/`,
    lastmod: toDateStr(r.data.updatedDate ?? r.data.publishDate),
    changefreq: 'weekly',
  }));
  const blogPages: Entry[] = posts.map((p) => ({
    loc: `/blog/${p.slug}/`,
    lastmod: toDateStr(p.data.updatedDate ?? p.data.publishDate),
    changefreq: 'monthly',
  }));
  const recipePages: Entry[] = recipes.map((r) => ({
    loc: `/recipes/${r.slug}/`,
    lastmod: toDateStr(r.data.updatedDate ?? r.data.publishDate),
    changefreq: 'monthly',
  }));

  const all = [...staticPages, ...hubPages, ...reviewPages, ...blogPages, ...recipePages];
  const body = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${all.map((p) => `  <url>\n    <loc>${SITE.url}${p.loc}</loc>${p.lastmod ? `\n    <lastmod>${p.lastmod}</lastmod>` : ''}\n    <changefreq>${p.changefreq}</changefreq>\n  </url>`).join('\n')}
</urlset>\n`;

  return new Response(body, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
};
