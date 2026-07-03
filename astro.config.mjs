import { defineConfig } from 'astro/config';
import { SITE } from './src/config.ts';

// Static output — deploys to Cloudflare Pages via git push (no adapter needed for static).
// NOTE: @astrojs/sitemap integration removed 2026-07-03 — it was crashing the build
// ("Cannot read properties of undefined (reading 'reduce')") due to a version mismatch
// between the resolved @astrojs/sitemap and Astro's astro:routes:resolved hook. Re-add
// once both are pinned to a verified-compatible pair; not required to launch.
export default defineConfig({
  site: SITE.url,
  build: { format: 'directory' }
});
