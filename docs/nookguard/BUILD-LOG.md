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


## Commit 4: Canon and prompt compiler — DONE

**Completed:** 2026-07-21

**Changed (`site/nookguard/`):**
- `canon.py` (new) — `CanonRegistry` reads the 5 REAL canon files that already
  govern Winnie/room consistency in the main project (does not restate their
  content, only hashes/tracks it, per Appendix M's "without restating or
  changing Winnie canon" instruction): `Winnie-Image-Generation-Rules.md`,
  `winnie/Winnie-Identity-Source-of-Truth.md`, `winnie/Winnies-Home-Room-
  Bible.md`, `winnie/Character-Bible.md`, `winnie/Winnie-Image-Lexicon-2026-
  07-16.md`. `missing_canon_files()` fails loud rather than silently skipping
  a canon file that's expected but absent. `bundle_sha256()` hashes all 5
  files' current content into one hash; `check_bundle_is_current()` is the
  H007 check.
- `modules.py` (new) — `PromptModule` + `ModuleRegistry` with an
  `INCOMPATIBLE_PAIRS` set. Directly encodes the real 2026-07-18 incident from
  the main project (`STYLE_LIFESTYLE_SCENE` hallucinating indoor furniture
  into outdoor scenes) as a structural, enforced compile-time rejection
  (`check_compatibility()`) instead of a prose rule someone has to remember.
- `prompt_compiler.py` (rewritten, `COMPILER_VERSION` bumped to
  `0.2.0-canon-aware`) — `compile_prompt()` now: (1) hard-fails via
  `MissingCanonError` if any expected canon file is absent, (2) hard-fails via
  `StaleCanonError` if the contract's `canonical_reference_bundle_sha256`
  doesn't match the live canon bundle hash (H007), (3) selects an indoor or
  outdoor lifestyle-style module from the contract's `scene` text via a
  keyword heuristic and runs it through `ModuleRegistry.check_compatibility()`
  before including it, (4) embeds the live canon bundle hash as the first line
  of the compiled prompt text.
- `cli.py` — `cmd_spec_lock` now runs `CanonRegistry(project_root).
  missing_canon_files()` and, if clean, STAMPS the real live
  `bundle_sha256()` onto the contract's `canonical_reference_bundle_sha256`
  (never trusts a caller-supplied value — the whole point of the field is
  that it reflects true canon state at lock time). `cmd_prompt_compile` now
  passes a real `CanonRegistry` into `compile_prompt()` and translates
  `MissingCanonError`/`StaleCanonError`/`ValueError` (incompatible modules)
  into structured `{"ok": false, ...}` responses instead of letting them raise
  past the CLI boundary. New `--project-root` flag added to every subcommand
  (defaults to the real project root, computed from `cli.py`'s own file
  location, so no env var or hardcoded path is needed for normal use; tests
  override it to isolate from real canon content).
- `exceptions.py` — added `MissingCanonError`, `StaleCanonError`.
- `nookguard/tests/{test_canon.py, test_modules.py, test_prompt_compiler.py}`
  (new, 21 tests) — all use temp-directory fake canon roots, not the real
  project's `brand-assets/`, so they stay deterministic regardless of future
  real canon edits. Notable: `test_check_bundle_is_current_false_after_canon_
  edit` and `test_compile_prompt_raises_on_stale_canon_reference` are direct
  H007 regression tests; `test_check_compatibility_flags_the_real_
  incompatible_pair` and `test_compile_prompt_never_selects_both_indoor_and_
  outdoor` are direct regression tests for the real 2026-07-18 furniture-
  hallucination incident.

**Tests run:** `python -m pytest nookguard/tests -v` (Windows, via Desktop
Commander, real `python.exe` at `C:\Python314\python.exe`)
**Result:** 42 passed, 0 failed (21 from Commits 2-3 + 21 new). Includes the
existing `test_full_pipeline_run_start_through_validate` integration test
running end-to-end against the REAL project root's canon files (not a fake) —
this is the concrete proof that `cmd_spec_lock`'s new canon check passes
against the actual `brand-assets/` content as it exists today, not just an
isolated fixture.

**Commit:** `3d94cdb`, pushed to `origin/main` (`e424007..3d94cdb`).
Commit message lost its literal "(H007)" suffix to a PowerShell parsing quirk
with parentheses — cosmetic only, the enforcement itself is real and tested.

**Unresolved risks:** none new. The scene->module heuristic in
`prompt_compiler.py` (`_select_scene_style_modules`) is intentionally narrow —
only 2 modules exist so far (indoor/outdoor lifestyle). It is not yet wired to
read the real `scripts/image_style.py` module text from the main project;
that file lives outside this package and wasn't in Commit 4's stated scope
("Canonical registry, stale-source scan, module registry/source map" — the
scope is the registry mechanism, not porting the actual production prompt
library). Worth revisiting when this compiler starts producing prompts an
adapter actually uses (Commit 5+).

**Next:** Commit 5 (Generation adapter) — real Hugging Face Z-Image-Turbo
wrapper behind the same `adapters` interface `stub.py` already established,
with the documented `HF_TOKEN` explicit-sourcing gotcha from the main project
CLAUDE.md applied from the start, quarantine/immutable-path handling already
built in `store.py`, and `AVAILABLE_ADAPTERS` extended so `cmd_generate` stops
rejecting a real adapter name.
