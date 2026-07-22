# nookguard-worker

NookGuard Commit 14+15: the D1-backed ledger and R2-backed artifact backend,
per `SPEC.md`'s row 14+ ("Backend — Worker/D1/R2/Access/dashboard and
operations, lowest priority, build last"), Appendix H's SQL sketch, and
Appendix K's deliverables table.

## Scope so far

- **Commit 14** built and tested the **events / generation_attempts /
  reviews** D1 schema and the Worker API in front of it.
- **Commit 15** added R2-backed candidate artifact byte storage
  (`/artifacts/:sha256`), content-addressed and hash-verified at write time.

It does **not** yet:

- Cut `nookguard/ledger.py` or the Python generation adapter (Commit 5) over
  to call this Worker. The Python CLI still writes its own local append-only
  JSON-lines ledger and local quarantine files. Wiring the Python side to
  call this Worker's HTTP API instead is real, separate work for a later
  commit — this package only proves the Worker side is correct on its own.
- Add the Access-protected dashboard. That's Commit 16, and depends on this
  Worker's API existing first.
- Provision a real Cloudflare D1 database, R2 bucket, or Access policy. All
  of that requires Maurice's own Cloudflare account — see "Unresolved
  risks" below and `wrangler.toml`'s own comment.

## Layout

- `migrations/0001_init.sql` — the three tables from Appendix H, verbatim,
  plus indices the sketch doesn't specify (see the file's own comment for
  exactly what was added and why).
- `src/enforce.mjs` — the two pure policy functions implementing Appendix
  H's "Enforce in Worker transaction" comment (D1 side).
- `src/db.mjs` — data-access functions for all three D1 tables, dependency-
  injected against a D1-shaped `db` parameter.
- `src/artifacts.mjs` — R2-backed candidate artifact storage
  (`putArtifact`/`getArtifact`/`headArtifact`), dependency-injected against
  an R2-shaped `bucket` parameter. `putArtifact` verifies the uploaded
  bytes actually hash to the SHA-256 in the request path (Web Crypto,
  computed for real) before ever calling `bucket.put()` — the R2 twin of
  Commit 12's release-integrity hash check, enforced at write time instead
  of at verification time.
- `src/router.mjs` — the actual HTTP routing/validation logic
  (`routeRequest(request, env)`, where `env = { db, artifacts }`),
  exercised directly in tests via real `Request`/`Response` objects.
- `src/index.mjs` — the real `export default { fetch }` Worker entrypoint;
  a few lines wiring `env.DB`/`env.ARTIFACTS` into `router.mjs`.
- `wrangler.toml` — real Cloudflare Workers config (D1 + R2 bindings,
  migrations dir). `database_id`/`bucket_name` are placeholders — see the
  file's own comment.
- `tests/fakeD1.mjs` — a D1Database-shaped wrapper around Node's built-in
  `node:sqlite`, used only in tests. See that file's own comment for
  exactly what this does and does not prove.
- `tests/fakeR2.mjs` — an R2Bucket-shaped in-memory store, used only in
  tests. Same honesty caveat as `fakeD1.mjs`: real hashing, real byte
  storage/retrieval, not R2's real network/durability behavior.
- `tests/*.test.mjs` — real tests against real SQLite / the in-memory R2
  shim and real `Request`/`Response` objects, using Node's built-in test
  runner (`node --test`), matching this repository's own existing
  convention for JS tests (see `../tests/tools/*.test.mjs` and
  `../package.json`'s `test:tools` script) rather than introducing a new
  test framework.

## Running the tests

```
npm test
```

No `npm install` is required — this package has zero dependencies. That
was a deliberate choice made during Commit 14, not the original plan:
`better-sqlite3` (a native module) failed to install in this sandbox with
no Visual Studio C++ build tools available for `node-gyp` to compile
against, and `vitest` alone would have needed `npm install` to work around
this environment's `npm config get omit` → `dev` setting (the same
environment quirk already documented in the main project `CLAUDE.md` under
"Site search," which is why `pagefind` is a real `dependency` there, not a
`devDependency`). Node 24's built-in `node:sqlite`/`node:test`, plus Web
Crypto's `crypto.subtle.digest` for the R2 hash check in Commit 15, sidestep
all of that entirely — no native compilation, no npm install, and they
match this repository's own precedent for JS testing.

## Unresolved risks

- **No live Cloudflare account access in this sandbox.** `wrangler.toml`'s
  `database_id` and `bucket_name` are placeholders. Real D1/R2
  provisioning, `wrangler d1 migrations apply` against a live database, and
  `wrangler deploy` are all real steps that need Maurice's own Cloudflare
  account — the same standing category of gap as Cloudflare Pages'
  production branch source (flagged since Commit 1) and `--live-url`
  production verification (flagged since Commit 12).
- **No workerd/Miniflare test coverage.** `tests/fakeD1.mjs` and
  `tests/fakeR2.mjs` prove the schema and the application logic (`db.mjs`,
  `artifacts.mjs`, `router.mjs`, `enforce.mjs`) are correct against real
  SQLite, real Web-Crypto hashing, and real `Request`/`Response` objects.
  Neither exercises the actual Cloudflare Workers runtime, D1/R2's real
  network/consistency behavior, or `src/index.mjs`'s `env.DB`/
  `env.ARTIFACTS` wiring itself — that file is untested because testing it
  needs `wrangler dev` or `@cloudflare/vitest-pool-workers`, and installing
  either timed out / failed to resolve reliably in this sandbox (see
  Commit 14's BUILD-LOG entry for the specific failures hit). This is a
  real, named gap, not something papered over by the SQLite/R2-shim-level
  tests passing.
- **Neither `nookguard/ledger.py` nor the generation adapter has been cut
  over.** The Python CLI's ledger writes are still 100% local JSON-lines,
  and generated candidate bytes still land in the local quarantine
  directory (Commit 5's `store.py`), unchanged since those commits. This
  Worker is a real, tested, but currently unused parallel backend until a
  future commit wires the CLI to call it.
- **No authentication on the Worker API.** Every route in `router.mjs` is
  open — no bearer token, no Cloudflare Access check, on either the D1
  routes or the new `/artifacts/*` routes. Appendix K's "Dashboard:
  Access-protected Astro UI" describes protecting the *dashboard*; nothing
  in Appendix H or K describes protecting this Worker's own API the same
  way, but shipping it open to the public internet once deployed would be
  a real gap worth Maurice's explicit call before this Worker is ever
  actually deployed — flagged here rather than assumed away.
- **No object deletion or lifecycle policy for R2 artifacts.**
  `src/artifacts.mjs` deliberately exposes no delete route — content-
  addressed candidate bytes are meant to be immutable once written (section
  27: "no filename reuse... no automatic fix in place... preserves the
  rejected one"), so nothing in this commit needed one. A real deployment
  will eventually want an R2 lifecycle rule (or an explicit admin-only
  purge path) for quarantine bytes that were rejected and never released,
  so storage doesn't grow unbounded — not designed here, flagged as a real
  future need.
