# nookguard-dashboard

NookGuard Commit 16: the owner-queue dashboard, per Appendix K ("Dashboard:
Access-protected Astro UI") and Appendix J's operational runbook ("Maurice
can see and resolve only the owner queue from the private dashboard").

## What this is

A single static page (`src/pages/index.astro`) that lists pending Appendix E
owner-decision packets from the `owner_queue` D1 table (via
`nookguard-worker`'s `/owner_queue` API, Commit 16) and lets Maurice resolve
each one with one of the five Appendix E options (approve exact hash,
reject, revise spec, regenerate, defer), recording the consequences of that
decision. This is a separate Astro project (its own `package.json`, its own
eventual Cloudflare Pages deployment) from the main `nestandnook-site`
project one directory up — see `astro.config.mjs`'s own comment for why
keeping it separate was a deliberate choice, not default sprawl.

## What "Access-protected" means here, concretely

Cloudflare Access is an edge/network-level protection, not application
code — there is no middleware or server-side check this static site can run
to "verify Access," because a request that reaches this site's HTML at all
has, by definition, already passed Access (or Access isn't actually
configured). The real, still-open steps to make this protected are:

1. Deploy this project as its own Cloudflare Pages project, on its own
   subdomain (e.g. `admin.nestandnook.org`).
2. In Cloudflare Zero Trust → Access → Applications, create a Self-hosted
   application covering that subdomain, restricted to Maurice's own
   identity (email OTP or whatever identity provider he prefers).
3. Route the Worker (`nookguard-worker/`) at a path under the *same*
   subdomain (e.g. `admin.nestandnook.org/api/*`) rather than its own
   separate `workers.dev` origin — see "Deployment topology" below for why.

None of this is something a Cowork sandbox session can do — it requires
Maurice's own Cloudflare account, the same category of gap flagged
repeatedly since Commit 1 (Cloudflare Pages' production branch source) and
Commit 12 (`--live-url` verification).

## Deployment topology (why `/api`, not a separate origin)

`src/pages/index.astro`'s `WORKER_BASE_URL` defaults to `/api` — a
same-origin, relative path — not an absolute URL to a separate Worker
domain. This is deliberate: if the dashboard and the Worker are on
different origins, the browser's Cloudflare Access session cookie for the
dashboard's domain does not automatically authenticate cross-origin
requests to the Worker's domain, and CORS plus cross-site cookie policy
becomes a real, fragile problem to solve correctly. Routing the Worker at
a path under the *same* Access-protected hostname as the dashboard (one
Cloudflare "Route" pointing `/api/*` at the Worker, one Access application
covering the whole hostname) sidesteps all of that: the request is
same-origin, the browser sends the existing session cookie normally, and
Cloudflare's edge attaches the real `Cf-Access-Jwt-Assertion` header before
the request ever reaches the Worker. `nookguard-worker/src/router.mjs`'s
CORS headers (added this same commit) still matter for local dev (running
the dashboard and `wrangler dev` on different localhost ports), but are not
the primary mechanism for the real deployed system.

## Identity flow for a resolve action

1. Maurice authenticates to Access once (email OTP or configured identity
   provider) when he first opens the dashboard.
2. Every same-origin request to `/api/owner_queue/*` automatically carries
   both the Access session cookie and (added by Cloudflare's edge, not by
   this code) the `Cf-Access-Jwt-Assertion` header.
3. `nookguard-worker`'s resolve route verifies that JWT for real (RS256
   signature, audience, expiry — see `nookguard-worker/src/access.mjs`) and
   uses the JWT's own `email` claim as `resolved_by`, ignoring whatever the
   client-side JS sent — see `nookguard-worker/src/router.mjs`'s resolve
   handler comment. The dashboard's own fetch call sends a placeholder
   `resolved_by` value specifically because it cannot be trusted and isn't
   meant to be, once Access is actually configured.

## Layout

- `astro.config.mjs` — minimal static-output config; own comment explains
  the separate-project decision.
- `src/pages/index.astro` — the entire UI: static shell + client-side
  `<script>` that fetches `/api/owner_queue`, renders pending entries, and
  posts resolutions.
- `.env.example` — `PUBLIC_NOOKGUARD_WORKER_URL` override, local-dev only.
- `package.json` — `astro` is a real `dependency`, not a `devDependency`
  (same `npm config get omit` → `dev` environment quirk documented in the
  main project `CLAUDE.md` and in `nookguard-worker/README.md`).

## Running / building

```
npm install
npm run build   # astro build -> dist/
npm run dev     # astro dev, for local iteration
```

## Unresolved risks

- **No live Cloudflare account access in this sandbox.** No Pages project,
  no Access application, no route rule connecting a real deployed
  `nookguard-dashboard` to a real deployed `nookguard-worker` exists yet.
  This is tested-and-built code, not a deployed service — see
  "What 'Access-protected' means here" above for the exact remaining
  manual steps.
- **No end-to-end browser test of the dashboard against a real (or even
  Miniflare-emulated) Worker.** This commit verifies `astro build` produces
  real static output (see BUILD-LOG's evidence for the exact command/
  result) and that the Worker-side API the dashboard calls is fully tested
  (`nookguard-worker/tests/`), but nothing in this sandbox can load
  `index.astro` in a real browser and click through an actual resolve flow
  against a live or Miniflare-emulated backend — no Chrome/Playwright
  wired to a running `astro preview` + `wrangler dev` pair was attempted
  this commit. A real manual click-through, once both projects are
  deployed, is the honest remaining verification step.
- **The `resolved_by` placeholder string sent by the dashboard when Access
  is NOT yet configured is not itself an identity check of any kind** —
  matches the Worker's own already-documented "no authentication" state
  for every other route (Commits 14/15). Once Access is provisioned per
  the steps above, this stops mattering (the Worker overrides it), but
  until then, resolving an entry says "resolved by
  dashboard-unauthenticated-fallback" in the record, which is an honest
  reflection of the current state, not a bug to silently paper over.
- **No pagination, sorting, or search on the entries list.** Fine for the
  volumes NookGuard is expected to produce in the near term (per the main
  project's own paced-publishing constraints), but would need real work if
  the owner queue ever grew into the hundreds of pending entries.
