import { defineConfig } from 'astro/config';
import { SITE } from './src/config.ts';

// Static output — deploys to Cloudflare Pages via git push (no adapter needed for static).
// NOTE: @astrojs/sitemap integration removed 2026-07-03 — it was crashing the build
// ("Cannot read properties of undefined (reading 'reduce')") due to a version mismatch
// between the resolved @astrojs/sitemap and Astro's astro:routes:resolved hook. Re-add
// once both are pinned to a verified-compatible pair; not required to launch.
export default defineConfig({
  site: SITE.url,
  build: { format: 'directory' },
  // The header search widget (BaseLayout.astro) dynamically imports
  // /pagefind/pagefind.js at runtime — a file that only exists after
  // `pagefind --site dist` runs as part of this same build script, so it
  // can never be resolved at bundle time. Marking it external stops Vite/
  // Rollup from trying to resolve it during `astro build` and leaves the
  // import() as a genuine runtime browser import, which is what Pagefind's
  // own docs recommend for embedding the core JS API outside pagefind-ui.js.
  vite: {
    build: {
      rollupOptions: {
        external: ['/pagefind/pagefind.js']
      }
    }
  }
});
