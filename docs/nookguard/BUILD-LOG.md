# NookGuard Build Log

Evidence-backed record of what has actually been built, per phase, per Appendix M's
own instruction: do not claim a phase complete before its exit criteria are
demonstrated in a clean run. Each entry: changed files, tests run/results, unresolved
risks, next phase, checkable commit hash.

---

## Commit 1: Containment — DONE

**Completed:** 2026-07-21

**Changed:**
- New local git repo at `Amazon Drop Ship/` root (separate from `site/`) versioning
  316 previously-untracked files (`scripts/` — 174 files, `skills/`, `config/`, root
  docs). `brand-assets/` (1.3GB) and `uploads/` excluded via `.gitignore`.
  Commit: `f43fb5488713cd9230ee8e4d6db7da516efab99b`
- `site/docs/nookguard/{NookGuard-Plan.docx, README.md, SPEC.md, BUILD-LOG.md}` added,
  committed, pushed to `main`. Commit: `3e396498534c991a2e395b8130476fb11e370b55`
- `production` branch created off that same commit and pushed to origin.

**Exit criteria check:**
- No scheduled run can change public media outside a release workflow — TRUE. Both
  `nest-and-nook-daily-blog-post` and `nest-and-nook-daily-image-and-page-build` are
  `enabled: false` (confirmed via `list_scheduled_tasks`) and stay that way until
  Commits 5-8 (generation adapter + review pipeline) exist.

**Unresolved risks (carried forward, not blocking):**
- Cloudflare Pages' actual deploy-source branch is unverified — dashboard access
  needed (Maurice only). `production` branch exists at the git level but is not
  confirmed wired to the real deploy. Flag again at Commit 12.
- This session's Cowork sandbox mount showed unreliable file-locking on bulk git ops
  (stale `index.lock`, permission-denied `rm`). All git/filesystem work for NookGuard
  went through Desktop Commander instead — keep doing that for future commits, don't
  retry heavy git ops from the sandbox bash tool on this project.
- Two stale `index.lock` files were found and removed during this session (one in
  each repo) — neither reflected an actually-running process (confirmed via
  `Get-Process git`) but both are worth a mental note in case some other tool/session
  is leaving git processes uncleanly killed.

---

## Commit 2: Schemas and ledger — IN PROGRESS

**Started:** 2026-07-21
## Commit 2: Schemas and ledger — DONE

**Completed:** 2026-07-21

**Changed (all in `site/nookguard/`, new Python package, root `pyproject.toml`):**
- `schemas.py` — Pydantic models: AssetContract (Appendix B fields, includes
  `validate_requirements_are_concrete()` to reject vague requirements),
  GenerationAttempt (section 27), BlindObservation (Appendix C, no pass/fail
  field), RequirementJudgment + ContractJudgment (Appendix D, `extra="forbid"`
  so a narrative-override field like `extra_justification` is a schema error,
  not just a convention), Event (Appendix H).
- `hashing.py` — sha256_bytes/sha256_file/sha256_canonical_json/
  content_addressed_path.
- `ledger.py` — append-only JSON-lines event log (Commit 14 will swap the
  storage backend to D1 per Appendix H's SQL; schema/contract unchanged) with
  `verify_integrity()` tamper detection.
- `state_machine.py` — AssetState enum + TRANSITIONS table + `transition()`
  that raises InvalidTransitionError on illegal moves + `is_regenerate_source()`
  enforcing "no fix in place" (section 27) structurally, not by convention.
- `nookguard/tests/` — 17 tests across 4 files.

**Tests run:** `python -m pytest nookguard/tests/ -v --cache-clear`
**Result:** 17 passed, 0 failed, 0 warnings (verified twice, clean cache).

Notable test coverage tied directly to real incidents/rules, not generic
coverage: `test_cannot_self_certify_generation_to_release` (the core failure
this system exists to prevent), `test_semantic_fail_states_require_regenerate_
not_fix_in_place` (the banana-foil/goat-fence incidents specifically),
`test_needs_owner_cannot_auto_pass`, `test_requirement_judgment_rejects_
narrative_override_field`.

**Commit:** `5626144b05981c8f38005fce01504da6199b1696`, pushed to `origin/main`.

**Honest note on my own process:** first draft of `test_sha256_bytes_known_
vector` hand-typed a "known" SHA-256 hex constant from memory and it was wrong
by one character — caught by actually running the test, not by eyeballing it.
Rewrote it to compute the expected value via `hashlib` directly instead of a
memorized literal. Flagging this because the main project CLAUDE.md's standing
rule is "every checkable claim needs a checkable artifact, not prose" — this is
exactly that kind of claim, and it would have been wrong if not run for real.

**Unresolved risks:** none new. Same Cloudflare-branch-verification gap as
Commit 1, still deferred to Commit 12.

**Next:** Commit 3 (mediactl CLI) — run/spec/prompt/generate/register/validate
commands wrapping the schemas/ledger/state-machine built here.
