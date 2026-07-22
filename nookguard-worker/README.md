# nookguard-worker

NookGuard Commit 14: the D1-backed ledger backend, per `SPEC.md`'s row 14+
("Backend — Worker/D1/R2/Access/dashboard and operations, lowest priority,
build last") and Appendix H's SQL sketch.

## Scope of this commit

This commit builds and tests the **events / generation_attempts / reviews**
D1 schema and the Worker API in front of it. It does **not** yet:

- Cut `nookguard/ledger.py` (Python, Commit 2) over to call this Worker.
  The Python CLI still writes its own local append-only JSON-lines ledger.
  Wiring the Python side to call this Worker's HTTP API instead is real,
  separate work for a later commit — this commit only proves the Worker
  side is correct on its own.
- Add R2 (artifact/media byte storage). Per `SPEC.md`'s own ordering
  ("Worker/D1/R2/Access/dashboard") D1 comes first; R2 is Commit 15.
- Add the Access-protected dashboard. That's Commit 16, and depends on
  this Worker's API existing first.
- Provision a real Cloudflare D1 database, R2 bucket, or Access policy.
  All of that requires Maurice's own Cloudflare account — see
  "Unresolved risks" below and `wrangler.toml`'s own comment.

## Layout

- `migrations/0001_init.sql` — the three tables from Appendix H, verbatim,
  plus indices the sketch doesn't specify (see the file's own comment for
  exactly what was added and why).
- `src/enforce.mjs` — the two pure policy functions implementing Appendix
  H's "Enforce in Worker transaction" comment.
- `src/db.mjs` — data-access functions for all three tables, dependency-
  injected against a D1-shaped `db` parameter.
- `src/router.mjs` — the actual HTTP routing/validation logic, exercised
  directly in tests via real `Request`/`Response` objects.
- `src/index.mjs` — the real `export default { fetch }` Worker entrypoint;
  a two-line wrapper around `router.mjs`.
- `wrangler.toml` — real Cloudflare Workers config (D1 binding, migrations
  dir). `database_id` is a placeholder — see the file's own comment.
- `tests/fakeD1.mjs` — a D1Database-shaped wrapper around Node's built-in
  `node:sqlite`, used only in tests. See that file's own comment for
  exactly what this does and does not prove.
- `tests/*.test.mjs` — real tests against real SQLite (via the shim above)
  and real `Request`/`Response` objects, using Node's built-in test runner
  (`node --test`), matching this repository's own existing convention for
  JS tests (see `../tests/tools/*.test.mjs` and `../package.json`'s
  `test:tools` script) rather than introducing a new test framework.

## Running the tests

```
npm test
```

No `npm install` is required — this package has zero dependencies. That
was a deliberate choice made during this commit, not the original plan:
`better-sqlite3` (a native module) failed to install in this sandbox with
no Visual Studio C++ build tools available for `node-gyp` to compile
against, and `vitest` alone would have needed `npm install` to work around
this environment's `npm config get omit` → `dev` setting (the same
environment quirk already documented in the main project `CLAUDE.md` under
"Site search," which is why `pagefind` is a real `dependency` there, not a
`devDependency`). Node 24's built-in `node:sqlite` and `node:test` sidestep
both problems entirely — no native compilation, no npm install, and they
match this repository's own precedent for JS testing.

## Unresolved risks

- **No live Cloudflare account access in this sandbox.** `wrangler.toml`'s
  `database_id` is a placeholder. Real D1 provisioning, `wrangler d1
  migrations apply` against a live database, and `wrangler deploy` are all
  real steps that need Maurice's own Cloudflare account — the same
  standing category of gap as Cloudflare Pages' production branch source
  (flagged since Commit 1) and `--live-url` production verification
  (flagged since Commit 12).
- **No workerd/Miniflare test coverage.** `tests/fakeD1.mjs` proves the
  schema and the application logic (`db.mjs`, `router.mjs`, `enforce.mjs`)
  are correct against real SQLite and real `Request`/`Response` objects.
  It does not exercise the actual Cloudflare Workers runtime, D1's real
  network/consistency behavior, or `src/index.mjs`'s `env.DB` wiring
  itself — that two-line file is untested because testing it needs
  `wrangler dev` or `@cloudflare/vitest-pool-workers`, and installing
  either timed out / failed to resolve reliably in this sandbox (see
  Commit 14's BUILD-LOG entry for the specific failures hit). This is a
  real, named gap, not something papered over by the SQLite-level tests
  passing.
- **`nookguard/ledger.py` has not been cut over.** The Python CLI's
  ledger writes are still 100% local JSON-lines, unchanged since Commit 2.
  This Worker is a real, tested, but currently unused parallel backend
  until a future commit wires the CLI to call it.
- **No authentication on the Worker API itself yet.** Every route in
  `router.mjs` is open — no bearer token, no Cloudflare Access check.
  Appendix K's "Dashboard: Access-protected Astro UI" describes protecting
  the *dashboard*; nothing in Appendix H or K describes protecting this
  Worker's own API the same way, but shipping it open to the public
  internet once deployed would be a real gap worth Maurice's explicit call
  before this Worker is ever actually deployed — flagged here rather than
  assumed away.
