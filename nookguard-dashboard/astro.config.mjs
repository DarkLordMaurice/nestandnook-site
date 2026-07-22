import { defineConfig } from 'astro/config';

// NookGuard Commit 16: a deliberately separate Astro project (its own
// package.json, its own Cloudflare Pages deployment target), NOT a route
// folded into the main nestandnook-site project. Reasoning, spelled out
// once here rather than left implicit: the main site is fully public
// marketing/affiliate content -- mixing an internal owner-decision
// dashboard into the same deploy means any Cloudflare Access
// misconfiguration on one path could expose the other, or vice versa.
// A separate Pages project gets its own domain/subdomain and its own
// Access application scoped to "protect everything here," which is a
// simpler, safer policy than "protect this one path of a public site."
// See README.md for the real, still-open provisioning steps this implies.
export default defineConfig({
  output: 'static',
});
