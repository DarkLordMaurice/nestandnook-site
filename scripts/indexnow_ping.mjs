// Submits site URLs to IndexNow (Bing + other participating engines pick
// these up directly, no separate account/verification needed — unlike GSC/
// Bing Webmaster proper, which still need Maurice's login separately).
//
// Usage:
//   node scripts/indexnow_ping.mjs                 -> submits every URL in dist/sitemap.xml (bulk, run after a full build)
//   node scripts/indexnow_ping.mjs /some/path/      -> submits a single URL (run after publishing one new/updated page)
//
// Key file lives at site/public/<key>.txt (must match INDEXNOW_KEY below) so
// it ships to https://nestandnook.org/<key>.txt on every deploy automatically
// -- IndexNow verifies ownership by fetching that file, no DNS/meta-tag step.
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = join(__dirname, '..');
const HOST = 'nestandnook.org';
// Regenerated 2026-07-18 -- the prior key (fba633bc6b7afd67b61198e628c272cd)
// stayed HTTP 403 "UserForbiddedToAccessSite" for 5+ days even with the key
// file confirmed live, likely a stuck verification cache from the very first
// submission (made before the key file was actually deployed). Per the plan
// already logged for this scenario: don't keep debugging the same key past
// a day or two, generate a fresh one instead.
const INDEXNOW_KEY = '0bb98d4f6591f3ff4def0bf406ea433f';
const KEY_LOCATION = `https://${HOST}/${INDEXNOW_KEY}.txt`;

function urlsFromSitemap() {
  const sitemapPath = join(SITE_ROOT, 'dist', 'sitemap.xml');
  if (!existsSync(sitemapPath)) {
    console.error('dist/sitemap.xml not found — run `npm run build` first.');
    process.exit(1);
  }
  const xml = readFileSync(sitemapPath, 'utf8');
  const matches = [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map((m) => m[1]);
  if (!matches.length) {
    console.error('No <loc> entries found in sitemap.xml.');
    process.exit(1);
  }
  return matches;
}

async function submit(urlList) {
  const body = {
    host: HOST,
    key: INDEXNOW_KEY,
    keyLocation: KEY_LOCATION,
    urlList,
  };
  const res = await fetch('https://api.indexnow.org/indexnow', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(body),
  });
  console.log(`IndexNow submit: ${urlList.length} URL(s) -> HTTP ${res.status}`);
  if (res.status !== 200 && res.status !== 202) {
    const text = await res.text().catch(() => '');
    console.error('Response body:', text);
    process.exitCode = 1;
  }
}

const arg = process.argv[2];
const urls = arg ? [arg.startsWith('http') ? arg : `https://${HOST}${arg}`] : urlsFromSitemap();

// IndexNow's bulk endpoint accepts up to 10,000 URLs per request, well above
// this site's current page count, so one request is enough for a full-site
// submission; chunk defensively anyway in case the site grows a lot.
const CHUNK = 9000;
for (let i = 0; i < urls.length; i += CHUNK) {
  await submit(urls.slice(i, i + CHUNK));
}
