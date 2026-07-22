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


## Commit 5: Generation adapter — DONE

**Completed:** 2026-07-21

**Changed (`site/nookguard/`):**
- `adapters/huggingface.py` (new) — real Z-Image-Turbo wrapper. Deliberately
  mirrors the exact, already-proven `gradio_client.predict()` call signature
  from the main project's production scripts (verified by reading
  `scripts/gen_offtheclock_backlog_images.py` directly, not guessed from
  memory) rather than inventing a new API shape: same model
  (`Tongyi-MAI/Z-Image-Turbo`), same kwargs (`resolution`, `seed`, `steps`,
  `shift`, `random_seed`, `gallery_images`, `api_name="/generate"`), same
  gallery-item parsing. `generate()` never writes to disk — returns JPEG
  bytes, leaving content-addressed placement to `store.quarantine_candidate`.
  Section 27 rules implemented as real code, not comments: bounded retry
  (`max_retries`, default 3, with a bounded backoff tuple — never an
  unbounded loop), `AdapterGenerationBlockedError` on exhaustion (never a
  bare exception escaping to the caller), and `_classify_error()` which
  refuses to report "rate_limited" unless a token was actually resolved —
  this is a direct, mechanical fix for the exact 2026-07-11 incident in the
  main project CLAUDE.md where a missing `HF_TOKEN` got misreported to
  Maurice as "quota exhausted" when the real PRO account had capacity left.
  `_resolve_hf_token()` re-implements that same incident's fix as code: check
  `os.environ` first, then fall back to reading the real persistent Windows
  User env var via `[System.Environment]::GetEnvironmentVariable('HF_TOKEN',
  'User')` if the process-level copy is empty, so this adapter can't
  silently run unauthenticated just because a launching shell forgot to
  source it.
- `adapters/__init__.py` — `AVAILABLE_ADAPTERS` now `{"stub", "huggingface"}`.
- `cli.py` — `cmd_generate` now dispatches on `args.adapter` instead of
  hardcoding the stub module; huggingface-path failures come back as
  structured `{"ok": false, "generation_blocked_reason": ..., "attempts":
  ...}` rather than a raised exception reaching the CLI boundary.
- `nookguard/tests/test_adapters_huggingface.py` (new, 11 tests) — 100%
  network-free via the `client`/`client_factory` injection seams `generate()`
  exposes for exactly this purpose. Notable:
  `test_generate_never_sleeps_more_than_backoff_table_length` (proves the
  retry loop is genuinely bounded), `test_classify_error_does_not_claim_
  rate_limited_without_token` (direct regression test for the 2026-07-11
  incident — a quota-shaped error message must still classify as `no_token`
  when unauthenticated, never `rate_limited`).
- `nookguard/tests/test_cli.py` — added
  `test_generate_dispatches_to_huggingface_adapter` (patches
  `huggingface.generate` directly, proves `cmd_generate` really routes to it
  and returns a `.jpg` artifact with the right adapter version — not just
  that the stub path still works). Fixed
  `test_generate_rejects_unimplemented_adapter`, which pre-Commit-5 used
  `"huggingface"` as its example of a not-yet-available adapter — now uses
  `"openai"`, since huggingface is real now. Also caught the same missing
  `--run-id`/`--session-id` bug already documented in Commit 3's own honest
  note (the ledger's `Event` schema requires both; a test that omits them
  gets a `pydantic.ValidationError` that looks like an unrelated failure) —
  fixed on the new test before it ever reached BUILD-LOG as a false problem.

**Tests run:** `python -m pytest nookguard/tests -v`
**Result:** 54 passed, 0 failed (42 from Commits 2-4 + 12 new: 11 adapter unit
tests + 1 CLI integration test). Also independently confirmed
`gradio_client` (2.5.0) and `Pillow` (12.2.0) are actually installed on the
real Windows Python this project uses, before writing code that imports them
— not assumed.

**Commit:** `36401e5`, pushed to `origin/main` (`d03b157..36401e5`).

**Unresolved risks:**
- This adapter has NOT been exercised against the real Hugging Face API in
  this session — only against injected fakes. That's intentional (no network
  access from the sandbox, and a real call costs ZeroGPU quota minutes for a
  no-op smoke test) but it means the real `gradio_client.Client(...).predict(
  ...)` call path itself is unverified end-to-end by this session, only by
  the fact that it's a byte-for-byte copy of an already-proven production
  call. Worth a single real smoke-test generation the first time this
  adapter is actually used for a real asset, rather than trusting the copy
  blindly forever.
- No live HF_TOKEN was read or used this session (Desktop Commander shell was
  never asked to source it) — `_resolve_hf_token()`'s Windows-fallback branch
  is covered by unit tests with a mocked environ, not by an actual
  `subprocess.run` against the real persistent env var. Low risk (it's a
  direct copy of the main project's already-working PowerShell one-liner) but
  flagging per the "checkable artifact, not prose" standard.
- Per Maurice's 2026-07-21 instruction, image publishing stays frozen — this
  adapter existing does not restart the daily scheduled tasks. That only
  happens once Commits 6-8 (validators + review agents + aggregation) exist
  and a real release path is wired up.

**Next:** Commit 6 (Technical validators) — fill in the
`checks_not_yet_implemented` gaps `validators/image.py` already declares
(duplicate detection, EXIF/privacy scan, blank-image detection, OCR/logo
scan), plus the review-pack generator that Commit 7's blind observers will
consume.


## Commit 6: Technical validators — DONE

**Completed:** 2026-07-21

**Changed (`site/nookguard/`):**
- `dedup.py` (new) — `DedupRegistry`, a small JSON-file-backed corpus of
  `{candidate_sha256: {exact_sha256, phash}}`. Exact-duplicate check reuses
  the same sha256 helper as everywhere else in this project. Near-duplicate
  uses a real aHash (average hash) implemented directly on PIL — no
  `imagehash` dependency, since it isn't installed in this environment and
  aHash is simple enough to write and verify directly (grayscale, downscale
  to 8x8, threshold each pixel against the image's own mean, pack into a
  64-bit hex hash; Hamming distance between two hashes measures similarity).
  Policy, stated explicitly in the module docstring: exact duplicate = hard
  technical fail (section 27's "no filename reuse" concern — a byte-
  identical output from a different generation attempt means something is
  actually wrong); near-duplicate = reported for review, not auto-failed
  (a consistent brand style can legitimately produce similar shots).
- `review_pack.py` (new) — `build_review_pack()` builds the exact bundle
  Commit 7's blind-observer sessions will be handed: candidate reference +
  role ("blind_a" gets nothing extra; "adversarial_b" gets Appendix C's
  general failure taxonomy) — and nothing else. Deliberately excludes the
  contract, requirements, prompt text, and any expected/allowed/forbidden
  object list, per Appendix C's explicit rule that the observer session
  never sees the contract. `review_pack_sha256` hashes only what the
  observer was actually shown, so a review pack can't be silently swapped
  after the fact any more than a spec or prompt can.
- `validators/image.py` (expanded) — `_check_exif_privacy` (flags embedded
  GPS EXIF — a real privacy leak if a candidate with location metadata ever
  shipped), `_check_blank_or_solid` (per-channel stddev threshold — a
  genuine generation defect, not a style judgment), and dedup wiring
  (`dedup_registry`/`candidate_sha256` optional params; when omitted, both
  duplicate checks report `performed: False` rather than a false-clean
  result). `NOT_YET_IMPLEMENTED` is down to exactly two items, both left
  out for a stated reason rather than oversight: `edge_clipping_risk`
  (subject-clipping is a semantic/subject-detection question, correctly
  the blind-observer layer's job in Commit 7-8, not a deterministic pixel
  check) and `ocr_logo_scan` (neither `pytesseract` nor a system
  `tesseract` binary exists in this environment — checked directly via
  `shutil.which("tesseract")`, not assumed; reports `performed: False`
  with the concrete reason rather than silently passing).
- `store.py` — added `review_packs_dir` + `save_review_pack`/
  `load_review_pack`, and a `dedup_registry_path` property so `cli.py`
  doesn't need to know the registry's on-disk layout.
- `cli.py` — `cmd_validate` now builds a real `DedupRegistry` from the
  store root, passes it into `image_validator.validate()`, and registers
  the candidate into the corpus ONLY on a real technical pass (a failed/
  blank/duplicate candidate shouldn't become a future "known good"
  comparison point). New `cmd_review_pack_build` + `review-pack-build`
  subcommand: requires state `TECHNICAL_PASS`, builds both observer roles'
  packs, transitions the asset to `OBSERVING` (the state machine already
  had this exact edge from Commit 2 — Commit 6 is the first thing to
  actually use it).
- `nookguard/tests/{test_dedup.py, test_review_pack.py,
  test_validators_image.py}` (new, 22 tests) — `test_dedup.py` initially
  used solid-color image fixtures for the "different images -> different
  hash" cases, which failed: aHash thresholds each pixel against the
  image's OWN mean, so a perfectly uniform image always hashes to the same
  all-1s pattern regardless of its actual color (a real, documented
  property of aHash, not a bug in this implementation) — fixed by switching
  those two fixtures to gradient images, which give aHash real structure to
  distinguish. `test_validators_image.py` covers the full `NOT_YET_
  IMPLEMENTED` reduction directly: blank/solid hard-fail, EXIF/GPS report,
  exact-duplicate hard-fail via an injected registry, near-duplicate
  reported-not-failed, OCR reported-not-performed. `test_cli.py`'s full
  pipeline test now runs one step further, through `review-pack-build`,
  asserting the two observer roles produce genuinely different
  `review_pack_sha256` values (not the same pack relabeled).

**Honest note on my own process:** first draft of a CLI-level duplicate-
detection integration test (registering a second, deliberately byte-
identical stub-generated candidate under a different asset_id) was wrong
and never got past being drafted — the content-addressed store already
deduplicates identical bytes to the SAME `candidate_sha256`/quarantine
file, so a second `register` call for that same candidate hash against a
different asset would collide on `store.save_attempt`'s existing "one
output, one record" guard before ever reaching `validate()`. That's
actually correct, intentional behavior (an earlier layer already catches
the exact scenario I was trying to construct), but it meant my test's
premise didn't hold. Caught this by trying to write the test through, not
by review — dropped that draft and moved exact/near-duplicate coverage to
direct unit tests against `DedupRegistry`/`validate()` instead, which
correctly isolate the dedup-registry's OWN corpus-across-runs behavior
(the case it actually exists for) from the store's separate, already-
proven same-run content-addressing guarantee.

**Tests run:** `python -m pytest nookguard/tests -q`
**Result:** 76 passed, 0 failed, 0 warnings (54 from Commits 2-5 + 22 new).
Fixed a real `DeprecationWarning` from Pillow 12 (`Image.getdata()` ->
`get_flattened_data()`) surfaced by the new tests rather than leaving it as
noise.

**Commit:** `84e2e04`, pushed to `origin/main` (`cb1397e..84e2e04`).
Commit message again lost its parenthetical punctuation to the same
PowerShell quoting quirk noted in Commit 4 — cosmetic only.

**Unresolved risks:**
- `ocr_logo_scan` and `edge_clipping_risk` remain unimplemented, for the
  stated reasons above — flagging again here so a future session doesn't
  read "42 -> 2 remaining" as "basically done" and skip verifying which two
  are still open and why.
- `DedupRegistry`'s corpus file is per-`store_root`, not yet a single
  project-wide corpus — right now, dedup only catches repeats within one
  `mediactl` store directory, not across every asset ever generated for
  the real site. Worth revisiting when Commit 14's real backend exists;
  until then this is a known, bounded gap, not a silent one.

**Next:** Commit 7 (Claude review agents) — real Claude Agent SDK sessions
for the blind observer (role `blind_a`), adversarial observer (role
`adversarial_b`), and contract judge, each with a distinct session ID and
role-scoped context bundle (no shared context between them, per Appendix
C/D and section 46's Definition of Done), consuming the review packs this
commit now produces for real.


## Commit 7: Claude review agents — DONE

**Completed:** 2026-07-21

**Research done before writing any code:** dispatched the `claude-code-
guide` subagent to get the exact, correct headless-invocation mechanics
before guessing at CLI flags. Finding that changed the design: the `claude`
CLI's headless `-p`/`--print` mode does NOT feed local image files into
vision — its Read tool treats a referenced file path as text, not an image
(open upstream issue, cited in the subagent's sources). True headless
vision needs either the separate Claude Agent SDK package (confirmed NOT
installed in this environment — `pip show claude_agent_sdk` fails) or the
base Anthropic Messages API directly, which IS installed (`anthropic`
0.76.0, confirmed via direct import, not assumed). Built the runner around
the Messages API for that reason — it's also a stronger fit for "session
separation" than the CLI would have been: a single stateless
`messages.create()` call with no conversation history and no tools attached
has no mechanism to leak context between two calls, by construction, not by
convention.

**Changed (`site/nookguard/`):**
- `agents/{blind_observer_system_prompt.md, adversarial_observer_system_
  prompt.md, contract_judge_system_prompt.md}` (new) — the real instruction
  text each role runs under. Blind observer: inventory only, explicitly
  told it has no basis for a quality judgment since it wasn't told what was
  expected. Adversarial observer: same inventory task plus the Appendix C
  failure taxonomy (unexpected_furniture, material_fusion, duplicated_
  items, malformed_anatomy_or_hands, impossible_physics, branded_or_
  readable_text, environment_contradiction, repeated_composition), with an
  explicit instruction not to invent a defect that isn't there just because
  it was asked to look hard. Contract judge: told explicitly not to invent
  evidence beyond what the two observation reports contain, not to produce
  an overall pass/fail, and not to attempt any `extra_justification`-style
  override field (schema already rejects it via `extra="forbid"` from
  Commit 2 — the instructions tell the model this up front so it complies
  on the first try instead of the call failing schema validation).
- `agent_runner.py` (new) — `run_observer_session(review_pack, *,
  executor=...)` and `run_judge_session(contract, spec_sha256,
  blind_observation, adversarial_observation, *, executor=...)`.
  `ReviewSessionError` is the section 29.5 "Model JSON invalid or session
  interrupted -> REVIEW_ERROR" trigger — raised on executor failure OR
  schema-validation failure, never swallowed into a default result.
  `_extract_json()` tolerates a markdown code-fenced response despite
  instructions not to fence it (defensive, since models don't always
  follow formatting instructions exactly). `agent_definition_hash()`
  hashes each instruction file's real content into `reviewer_agent_hash`/
  `judge_agent_hash` — a future edit to any of these three files changes
  that hash, so a change in review behavior is attributable, not invisible.
  `_default_executor` is the real Messages API call (model
  `claude-opus-4-8`, no tools, no conversation history).
- **Structural (not just documented) enforcement of "the observer never
  sees the contract":** `run_observer_session()`'s function signature has
  no parameter through which a contract, prompt, or requirement list could
  be passed — confirmed by a dedicated test that inspects the real
  signature (`inspect.signature`), not just a docstring claim. Symmetric
  check on `run_judge_session()` for image/prompt-text params (the judge
  reasons over the two structured observation reports plus the contract's
  requirements, never the image itself, per Appendix D).
- `pyproject.toml` — added `Pillow`, `gradio_client`, `anthropic` as real
  `dependencies`. These were already load-bearing imports since Commit 3/5
  (`stub.py`, `validators/image.py`, `dedup.py`, `adapters/huggingface.py`)
  but had never actually been declared — a real gap, fixed while adding
  `anthropic` for this commit rather than left for later.
- `nookguard/tests/test_agent_runner.py` (new, 18 tests) — 100% network-
  free via the `executor` injection seam both runner functions expose.
  Notable: `test_run_observer_session_signature_has_no_contract_parameter`
  and `test_run_judge_session_signature_has_no_image_parameter` (the
  structural checks described above), `test_run_observer_session_
  adversarial_b_instruction_mentions_taxonomy` /
  `..._blind_a_instruction_has_no_taxonomy_mention` (proves the two
  observer roles are genuinely instructed differently, not just labeled
  differently), `test_agent_definition_hash_changes_with_content`,
  `test_real_agent_definition_files_exist_and_hash` (loads the actual
  shipped `.md` files, not a fixture — catches a typo'd filename
  immediately rather than only in a fixture-based test).

**Tests run:** `python -m pytest nookguard/tests -q`
**Result:** 94 passed, 0 failed, 0 warnings (76 from Commits 2-6 + 18 new).
Fixed a `PydanticDeprecatedSince211` warning in the new tests (instance-
level `model_fields` access -> class-level) surfaced during this run rather
than left as noise, same standard as Commit 6.

**Commit:** `b49020b`, pushed to `origin/main` (`2705ba4..b49020b`).

**Unresolved risks:**
- `_default_executor` (the real `anthropic.Anthropic().messages.create()`
  call) has NOT been exercised live in this session — no `ANTHROPIC_API_KEY`
  was configured or used here, same honest caveat as Commit 5's HF adapter.
  Everything UP TO the API call boundary is real and tested (prompt
  construction, image encoding, response parsing, schema validation, error
  classification); the actual network call itself is unverified until this
  runs for real the first time. Worth a single real smoke-test session
  (one observer call against one real quarantined candidate) before this
  is trusted for a real asset.
- Model choice (`claude-opus-4-8`) is a judgment call for review-quality
  reasons (this is exactly the kind of careful, adversarial visual
  judgment task that benefits from the strongest available model) but is
  not yet configurable per risk tier — Tier 0 decorative assets probably
  don't need the same model as Tier 3 brand-critical ones. Worth revisiting
  once real usage/cost data exists; not a blocker now since image
  publishing itself is still frozen per Maurice's 2026-07-21 instruction.
- `run_observer_session`/`run_judge_session` are not yet wired into
  `cli.py` — no `mediactl observe`/`mediactl judge` subcommands exist yet.
  That wiring is explicitly Commit 8's job, alongside the section 29.5
  code aggregator and the owner queue, per Appendix A's split between
  "Claude agents" (Commit 7, this one) and "Semantic aggregation" (Commit
  8, next).

**Next:** Commit 8 (Semantic aggregation) — `mediactl observe`/`mediactl
judge` CLI wiring consuming this commit's runner functions for real
review packs, plus the code aggregator implementing the section 29.5
policy table (never a model-asserted pass — code computes SEMANTIC_PASS/
FAIL/NEEDS_OWNER/etc. from the ContractJudgment's per-requirement results
and both BlindObservations' forbidden-object findings), plus an owner
queue for the calibration-sample and disagreement cases the risk-tier
table (43.1) describes.
