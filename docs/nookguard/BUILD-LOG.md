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


## Commit 3: mediactl CLI — DONE

**Completed:** 2026-07-21

**Changed (`site/nookguard/`):**
- `cli.py` — `mediactl` with subcommands `run-start`, `run-preflight`,
  `spec-lock`, `prompt-compile`, `generate`, `register`, `validate`. Every
  command prints one JSON object and returns a matching dict (`run_cli()` is
  the testable entry point `main()` wraps) — real business failures (bad
  contract, illegal state transition, missing file, unimplemented adapter)
  come back as `{"ok": false, "error": ...}` with exit code 1, never a raw
  traceback.
- `store.py` — filesystem-backed store for specs/prompts/quarantined
  candidates/attempts/asset-state, all content-addressed. This is the
  pre-Commit-14 stand-in for the D1/R2 backend — same contract, swappable
  storage engine.
- `prompt_compiler.py` — minimal real compiler (subject/action/scene/
  requirements -> deterministic text). Commit 4 replaces the body with a
  canon-aware version; the signature and caller contract stay the same.
- `adapters/stub.py` — generates a real, tiny, valid PNG so the pipeline has
  something genuine to push through technical validation. `generate` refuses
  any adapter name other than `stub` with an explicit "not available until
  Commit 5" error — it does not pretend to call a real model.
- `validators/image.py` — real (not stubbed) checks: opens/decodes, min
  resolution, nonzero file size. Explicitly reports which checks it does NOT
  yet perform (`checks_not_yet_implemented`: duplicate detection, EXIF scan,
  blank-image detection, OCR/logo scan) rather than silently passing them —
  Commit 6 fills these in.

**Tests run:** `python -m pytest nookguard/tests/ -v --cache-clear`
**Result:** 21 passed, 0 failed (17 from Commit 2 + 4 new CLI integration
tests). Also smoke-tested the real entry point directly:
`python -m nookguard.cli run-start --store-root nookguard_store_smoketest`
produced valid JSON on stdout (artifact dir removed before commit, not
checked in — this is one-off proof, not a fixture).

New integration coverage: `test_full_pipeline_run_start_through_validate`
(run→spec→prompt→generate→register→validate exercised for real, through the
CLI, not mocked), `test_generate_rejects_unimplemented_adapter`,
`test_spec_lock_rejects_vague_requirement`, `test_cannot_register_before_
generate` (state machine enforced through the real CLI, not just in
isolation like Commit 2's tests).

**Commit:** `eefa57d73e02512380fb939316122b14b3d97116`, pushed to `origin/main`.

**Honest note on my own process (second one — see Commit 2's note too):**
first draft of `cmd_register` checked file existence (prompt/candidate) before
checking whether the state transition was even legal, so an illegal-transition
call with a bogus candidate hash returned a confusing "file not found" instead
of the real "illegal transition" reason. Caught by writing a test for the
specific failure mode I wanted to guarantee, not by inspection. Reordered so
the state-machine check always runs first, before any file lookups.

**Unresolved risks:** none new.

**Next:** Commit 4 (canon registry + prompt compiler upgrade) — this is where
NookGuard starts reading the real Room Bible / Winnie-Image-Generation-Rules
canon and detecting stale sources, replacing `prompt_compiler.py`'s minimal
body.
