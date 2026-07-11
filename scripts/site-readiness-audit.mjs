#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const strict = process.argv.includes('--strict');
const failures = [];
const warnings = [];
const checked = { reviews: 0, recipes: 0, blog: 0, static: 0 };

const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const exists = (p) => fs.existsSync(path.join(root, p));
const walk = (dir, ext = null) => {
  const abs = path.join(root, dir);
  if (!fs.existsSync(abs)) return [];
  return fs.readdirSync(abs, { withFileTypes: true }).flatMap((e) => {
    const rel = path.join(dir, e.name);
    return e.isDirectory() ? walk(rel, ext) : (!ext || e.name.endsWith(ext) ? [rel] : []);
  });
};
const frontmatter = (text) => {
  const match = text.match(/^---\s*\n([\s\S]*?)\n---/);
  return match?.[1] ?? '';
};
const quoted = (fm, key) => {
  const match = fm.match(new RegExp(`^${key}:\\s*["']([^"']*)["']`, 'm'));
  return match?.[1];
};
const dateValue = (fm, key) => fm.match(new RegExp(`^${key}:\\s*([^\\n]+)`, 'm'))?.[1]?.trim();
const addFailure = (file, message) => failures.push(`${file}: ${message}`);
const addWarning = (file, message) => warnings.push(`${file}: ${message}`);

const configPath = 'src/config.ts';
if (!exists(configPath)) addFailure(configPath, 'missing');
const config = exists(configPath) ? read(configPath) : '';
const pending = /amazonAssociatesStatus:\s*'pending'/.test(config);
const approved = /amazonAssociatesStatus:\s*'approved'/.test(config);
if (pending && !/amazonAssociateTag:\s*'CHANGEME-20'/.test(config)) addFailure(configPath, 'pending status must retain placeholder tag');
if (approved && /CHANGEME-20/.test(config)) addFailure(configPath, 'approved status cannot use placeholder tag');
if (/contactEmailVerified:\s*false/.test(config)) addWarning(configPath, 'contact email routing is not marked verified; test the mailbox, then set contactEmailVerified: true');

const falseAssociatePatterns = [
  /As an Amazon Associate(?:,|\s)+(?:I|we) earn from qualifying purchases/i,
  /is an Amazon Associate/i,
  /participant in the Amazon Services LLC Associates Program/i,
  /Amazon Associates.affiliated/i,
];

const prohibitedPersonalUse = [
  /\bI tested\b/i,
  /\bI bought\b/i,
  /\bI own\b/i,
  /\bI actually reach for\b/i,
  /\bmy desk-mate\b/i,
  /\bin my home office\b/i,
];
const unsupportedClaims = [
  /highest lift on the market/i,
  /chiropractor-endorsed/i,
  /circulation benefits/i,
  /five dollars well spent/i,
  /Placeholder\s*[—-]/i,
  /DwellGear/i,
];

for (const file of walk('src', null)) {
  const text = read(file);
  // Compare with slashes normalized — walk() joins paths with path.join,
  // which emits backslashes on Windows, so a raw `file !== configPath`
  // never actually matched configPath ('src/config.ts', forward slash) on
  // this platform and silently failed to exclude it. That let the
  // approved-state string living inside config.ts's own status-aware
  // ternary (DISCLOSURE.associate) get flagged as if it were a hardcoded
  // false claim, even though it's dead code while status is 'pending'.
  const normalized = file.replace(/\\/g, '/');
  if (pending && normalized !== configPath) {
    for (const pattern of falseAssociatePatterns) {
      if (pattern.test(text)) addFailure(file, `claims active Amazon Associate status while config is pending (${pattern})`);
    }
  }
  for (const pattern of prohibitedPersonalUse) if (pattern.test(text)) addFailure(file, `possible fabricated Winnie personal use (${pattern})`);
  for (const pattern of unsupportedClaims) if (pattern.test(text)) addFailure(file, `prohibited/stale claim or placeholder (${pattern})`);
}

for (const file of walk('src/content/reviews', '.md')) {
  checked.reviews++;
  const text = read(file);
  const fm = frontmatter(text);
  const title = quoted(fm, 'title');
  const description = quoted(fm, 'description');
  const image = quoted(fm, 'image');
  if (!title) addFailure(file, 'missing title');
  if (title && title.length > 65) addFailure(file, `title is ${title.length} characters (max 65)`);
  if (!description) addFailure(file, 'missing description');
  if (description && description.length > 160) addFailure(file, `description is ${description.length} characters (max 160)`);
  if (!/^disclosure:\s*true/m.test(fm)) addFailure(file, 'disclosure must be true');
  if (!/<(?:p|section)[^>]+id=["']quick-answer["']/i.test(text)) addWarning(file, 'missing #quick-answer');
  if (!/id=["']measure-first-check["']/i.test(text)) addWarning(file, 'missing #measure-first-check');
  if (!/id=["']do-not-buy-(?:if|this-if)["']/i.test(text)) addWarning(file, 'missing do-not-buy stable ID');
  const linkCount = (text.match(/\]\(\//g) ?? []).length;
  if (linkCount < 2 && !/internalLinks:\s*\n(?:\s+-[\s\S]*?){2}/m.test(fm)) addWarning(file, 'fewer than two apparent internal links');
  if (image && !exists(`public${image}`)) addFailure(file, `hero image does not exist: public${image}`);
  for (const match of fm.matchAll(/^\s*asin:\s*["']?([A-Z0-9]+)["']?\s*$/gm)) {
    if (!/^[A-Z0-9]{10}$/.test(match[1])) addFailure(file, `invalid ASIN ${match[1]}`);
  }
  const published = dateValue(fm, 'publishDate');
  const updated = dateValue(fm, 'updatedDate');
  if (!published) addFailure(file, 'missing publishDate');
  if (!updated) addWarning(file, 'missing updatedDate; visible Last Reviewed will fall back to publish date');
}

for (const file of walk('src/content/recipes', '.md')) {
  checked.recipes++;
  const text = read(file);
  const fm = frontmatter(text);
  const title = quoted(fm, 'title');
  const description = quoted(fm, 'description');
  const image = quoted(fm, 'image');
  if (title && title.length > 70) addFailure(file, `title is ${title.length} characters (max 70)`);
  if (description && description.length > 160) addFailure(file, `description is ${description.length} characters (max 160)`);
  if (!image) addFailure(file, 'missing required image');
  else if (!exists(`public${image}`)) addFailure(file, `hero image does not exist: public${image}`);
}
checked.blog = walk('src/content/blog', '.md').length;
checked.static = walk('src/pages', '.astro').length;

for (const required of ['src/pages/privacy.astro', 'src/pages/contact.astro', 'src/pages/terms.astro', 'src/pages/disclosure.astro', 'src/pages/editorial-standards.astro']) {
  if (!exists(required)) addFailure(required, 'required trust page missing');
}
for (const required of ['src/components/HowWeChoose.astro', 'src/components/LastReviewed.astro', 'src/components/LinkLevelDisclosure.astro']) {
  if (!exists(required)) addFailure(required, 'required shared component missing');
}

console.log(`Nest & Nook readiness audit (${strict ? 'strict' : 'build-blocking'})`);
console.log(`Checked: ${checked.reviews} reviews, ${checked.recipes} recipes, ${checked.blog} blog posts, ${checked.static} static Astro pages.`);
if (warnings.length) {
  console.log(`\nWarnings (${warnings.length}):`);
  for (const item of warnings) console.log(`- ${item}`);
}
if (failures.length) {
  console.error(`\nFailures (${failures.length}):`);
  for (const item of failures) console.error(`- ${item}`);
}
const exitFailure = failures.length > 0 || (strict && warnings.length > 0);
if (exitFailure) {
  console.error(`\nAudit ${strict ? 'strict ' : ''}FAILED.`);
  process.exit(1);
}
console.log('\nAudit PASSED.');
