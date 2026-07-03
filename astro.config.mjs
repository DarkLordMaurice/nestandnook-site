import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { SITE } from './src/config.ts';

// Static output — deploys to Cloudflare Pages via git push (no adapter needed for static).
export default defineConfig({
  site: SITE.url,
  integrations: [sitemap()],
  build: { format: 'directory' }
});
