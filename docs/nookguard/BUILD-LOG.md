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


## Commit 8: Semantic aggregation — DONE

**Completed:** 2026-07-21

**Changed (`site/nookguard/`):**
- `aggregator.py` (new) — `aggregate(contract, judgment, blind_observation,
  adversarial_observation) -> AggregationResult`, the ONLY place a release
  decision is computed, implementing every row of section 29.5's policy
  table as real, ordered code (critical-false -> FAIL; missing critical
  judgment -> FAIL, same as false, never silently skipped; forbidden object
  >= 0.6 confidence -> FAIL; material/relationship requirement judged true
  with no cited evidence -> FAIL_EVIDENCE; identity/continuity constraints
  present but no satisfying requirement -> FAIL_REFERENCE; count
  disagreement between the two independent observers -> NEEDS_OWNER;
  critical uncertain -> NEEDS_OWNER on Tier 2/3, FAIL on Tier 0/1 rather
  than ever auto-passing; noncritical score below 60% -> FAIL; otherwise
  SEMANTIC_PASS). A dedicated test
  (`test_aggregation_result_never_asserts_pass_from_free_text`) inspects
  the function's own source to confirm it never reads an
  `extra_justification`/override-style field — structurally impossible
  anyway since Commit 2's schemas already reject such a field, but proven
  here rather than just assumed.
  **Documented, deliberate scope decision:** the policy table's "exact-
  count observers disagree -> third adjudicator; if still disputed,
  NEEDS_OWNER" describes a third agent role this commit does not build
  (that would be new session-type scope, not aggregation logic) — a real
  count disagreement routes straight to NEEDS_OWNER, which has the same
  practical effect (a human sees it) without fabricating a call to an
  adjudicator that doesn't exist.
- `owner_queue.py` (new) — `should_queue_for_owner()` encodes the 43.1
  risk-tier calibration table as real code: NEEDS_OWNER always queues;
  Tier 3 always queues even on a pass ("always final approval"); Tier 2
  always queues ("mandatory during launch"); Tier 1 queues on disagreement
  or within its first 20 assets per adapter; Tier 0 queues on disagreement
  or a deterministic every-10th-asset sample within its first 50 (the
  doc's "random 10%" is intentionally NOT implemented as real randomness —
  that would make the function non-deterministic and untestable; the
  bounded, deterministic approximation is documented as a real, stated
  trade-off, not silently substituted). `OwnerQueue` persists to JSON,
  same pattern as `DedupRegistry`/`Ledger`. **Explicit non-gate:** the
  module docstring states plainly that this is a tracking/visibility
  mechanism only — nothing in the CLI checks queue status before allowing
  a release, matching Maurice's 2026-07-21 instruction and the standing
  deferred-gating note in SPEC.md. When that changes, the gate belongs in
  a future release command, not here.
- `state_machine.py` — added `AssetState.REVIEW_ERROR` as a legal target
  from `OBSERVING`, not just `JUDGING`. Found this gap while wiring
  `cmd_observe`: an observer session can fail (bad JSON, interrupted call)
  exactly like a judge session can, and section 29.5 defines REVIEW_ERROR
  as covering "session interrupted" generally — there was no principled
  reason it should only be reachable from the judge step. Added per the
  module's own stated policy ("if a future commit needs a state this
  doesn't have, add it here with a BUILD-LOG note explaining why").
- `store.py` — `save_observation`/`load_observation` (keyed by
  `{candidate_sha256}_{role}`), `save_judgment`/`load_judgment`, and
  `bump_adapter_asset_count()` (a simple persistent per-adapter-version
  counter backing the "first N assets per adapter" calibration rule).
- `cli.py` — `cmd_observe` (state must be `OBSERVING`; runs both observer
  roles for real via `agent_runner.run_observer_session`, using
  `review_pack.build_review_pack()` reconstructed on the fly rather than
  re-loaded from Commit 6's stored pack — the pack is a pure function of
  `(candidate_sha256, image_path, role)`, so no extra index/lookup was
  needed; any single role failure routes the WHOLE asset to REVIEW_ERROR,
  not a partial state) and `cmd_judge` (state must be `JUDGING`; runs
  `run_judge_session`, saves the judgment, calls `aggregate()`, transitions
  to the computed result state, bumps the adapter counter, and enqueues to
  the owner queue when `should_queue_for_owner()` says so). New `observe`/
  `judge` subcommands.
- `nookguard/tests/{test_aggregator.py, test_owner_queue.py}` (new, 27
  tests) plus additions to `test_state_machine.py` (1) and `test_cli.py`
  (2, including a full `spec-lock` through `judge` pipeline test with
  `run_observer_session`/`run_judge_session` monkeypatched on `nookguard.
  cli`'s own imported names — `from .agent_runner import X` binds a local
  reference in `cli.py`, so patching `agent_runner.X` directly would NOT
  have affected `cli.py`'s calls; patched the right target on the first
  attempt by reasoning through the import binding rather than guessing).

**Honest note on my own process:** hit the exact same missing `--run-id`/
`--session-id` bug documented in Commits 3 and 5 a THIRD time, in both new
`test_cli.py` tests this commit — every `run_cli()` call in a test needs
`--run-id` or the ledger's `Event` schema rejects `None`. This is clearly a
recurring authoring mistake on my part, not a one-off; caught immediately
by actually running the suite, same as the prior two times, but worth
naming directly: three strikes on the identical mistake across three
different commits is a pattern, and future test-writing in this project
should default to including `--run-id` from the first draft rather than
discovering the omission via a failing test each time.

**Tests run:** `python -m pytest nookguard/tests -q`
**Result:** 124 passed, 0 failed, 0 warnings (94 from Commits 2-7 + 30
new). Also fixed an overly strict assertion in
`test_aggregation_result_never_asserts_pass_from_free_text` on first run —
it banned the bare substring "override" in `aggregate()`'s source, which
false-flagged the function's own explanatory comments (e.g. "no narrative
override") rather than actual field access; narrowed to `.override`
(attribute-style access) and `override_reason` instead.

**Commit:** `44e8893`, pushed to `origin/main` (`94efaa8..44e8893`).

**Unresolved risks:**
- The "third count adjudicator" gap noted above — a real, cited, deliberate
  scope decision, not an oversight, but flagging again here so a future
  session doesn't assume it exists.
- Tier 0's "random 10%" calibration sampling is approximated as a
  deterministic every-10th-asset rule for testability, not true randomness
  — stated as a real trade-off in the module docstring, not hidden.
- `should_queue_for_owner`'s `is_disagreement` parameter is not yet wired
  from `cmd_judge` to reflect the aggregator's own count-disagreement
  finding (it currently always passes the default `False` for that flag,
  relying on NEEDS_OWNER's own always-queue rule to catch the disagreement
  case in practice, since `aggregate()` already routes disagreements to
  NEEDS_OWNER before `should_queue_for_owner` is ever called with a
  different state). Functionally correct today, but the parameter exists
  for a case (a Tier 0/1 pass that still had a *minor*, non-blocking
  disagreement) this commit doesn't yet produce — worth wiring for real if
  that scenario becomes reachable.
- Owner-queue gating remains explicitly deferred per Maurice's 2026-07-21
  instruction — repeating this once more since it's easy for a future
  session to see a populated queue and assume it's blocking something.

**Next:** Commit 9 (Off the Clock schema + page validators) — content
migration for the Off the Clock section's photo-strip layout schema,
layout tests, and a ban on the legacy raw-media component (hook H009:
"Page adds legacy raw media component -> Fail content lint").


## Commit 9: Off the Clock schema + page validators — DONE

**Completed:** 2026-07-22

**Research done before writing any schema:** dispatched a subagent to read
all 10 real Off the Clock production files in full
(`site/src/content/blog/*.md`) and report the EXACT structure — not assumed
from the main CLAUDE.md's prose description of the 2026-07-18 layout
retool. Confirmed with zero exceptions across all 10 files: every
`photo-single` block contains exactly 1 `<figure>`, every `photo-strip`
block contains exactly 3, and no file contains the retired `polaroid
inset`/`float-left` markup anywhere. This matters because a wrong
assumption here would have produced a validator that hard-fails real,
correct, already-shipped content — the schema this commit encodes is
exactly what the real site does today, confirmed, not a guess at what the
doc's prose implied.

**"Content migration" — nothing to migrate, verified rather than assumed:**
per the main CLAUDE.md, the actual migration off the legacy layout happened
2026-07-18 (commit `f2018f5`), before this project existed. This commit's
job was to build the schema/validator that PROVES that migration is real
and complete, and will catch a regression — not to re-do work that's
already done. Stating this directly rather than silently skipping "content
migration" from Appendix A's line item without explanation.

**Changed (`site/nookguard/`):**
- `off_the_clock_schema.py` (new) — `lint_off_the_clock_page(markdown_body,
  category)` checks three independent things: (1) category is one of the
  two real values (`Life outside the nook`, `Behind the nook`); (2) every
  `photo-single`/`photo-strip` block has the confirmed-correct image count
  (1 / 3 respectively) — the regression fixture's literal "1, 4, or 5 photo
  strips instead of approved structure" case; (3) hook H009's legacy-
  component ban (`polaroid inset`, `polaroid.inset`, `float-left` anywhere
  in the body). `split_frontmatter()`/`extract_category()` are a minimal,
  dependency-free YAML-frontmatter field extraction — deliberately not
  adding a full YAML parser dependency for a single field.
- `cli.py` — `cmd_content_lint` / `mediactl content-lint`, with `--file`
  (single page) or `--dir` (batch mode over every `.md` file in a
  directory, skipping — not failing — files whose category isn't an Off
  the Clock category, so a mixed directory of Guides/recipes/Off-the-Clock
  content doesn't false-fail on out-of-scope files). Batch mode exists
  specifically so this can gate a real content build later (Definition of
  Done: "An Off the Clock page with the wrong strip count fails the
  content build") — not part of the asset state machine, since a page
  isn't a generated-media asset; this is a standalone lint, no store/
  transition involved.
- `nookguard/tests/{test_off_the_clock_schema.py,
  test_off_the_clock_real_content.py}` (new, 25 tests) plus 4 additions to
  `test_cli.py`. `test_off_the_clock_schema.py` is synthetic-fixture unit
  coverage of every rule, including direct regression tests for 1/4/5-image
  strips and a 2-image single. `test_off_the_clock_real_content.py` is the
  actual "layout test" called for in Appendix A — parametrized over all 10
  REAL file paths under `site/src/content/blog/`, asserting each one
  passes content-lint right now, plus a coverage-gap test confirming all 10
  expected filenames still exist on disk (so a rename or deletion is
  caught, not silently under-tested). New `test_cli.py` cases cover single-
  file success/failure, missing-file error handling, and `--dir` batch mode
  against the real blog directory (asserting exactly 5 Guides posts are
  skipped and all 10 Off the Clock posts are linted and pass).

**Tests run:** `python -m pytest nookguard/tests -q`
**Result:** 153 passed, 0 failed, 0 warnings (124 from Commits 2-8 + 29
new). The 10 parametrized real-file tests passing is the concrete,
checkable proof that the live site's Off the Clock section is genuinely
compliant right now, not just that the validator's logic is internally
consistent against fixtures.

**Commit:** `9ba3a3c`, pushed to `origin/main` (`27dcab1..9ba3a3c`).

**Unresolved risks:**
- `mediactl content-lint` is not yet wired into any actual build step
  (`astro build`, a pre-commit hook, or a CI job) — it exists and works,
  but nothing calls it automatically yet. That wiring is naturally Commit
  11's job (CI isolation) or could be added to the daily scheduled task's
  own push step sooner if Maurice wants it enforced before then.
- This commit only covers the Off the Clock section (10 files, per
  Appendix A's explicit scope for this commit). Guides posts and recipes
  have their own documented scaffolds (quick-answer/fix-box/FAQ for
  Guides; the 5-image-field structure for recipes) that aren't validated
  by any NookGuard code yet — out of scope here, not forgotten; flagging
  so a future session doesn't assume page-schema coverage is broader than
  it is.

**Next:** Commit 10 (Preview QA) — Playwright desktop/mobile rendering,
page contact sheets, and a page-preview reviewer, per Appendix A.

---

## Commit 10: Preview QA — DONE

**Completed:** 2026-07-22

**Changed:**
- `nookguard/preview.py` (new) — real Playwright/Chromium page capture.
  `VIEWPORTS` (desktop 1440x900, mobile 390x844 iPhone-class),
  `PageCaptureReport` dataclass, `capture_page_screenshot()` (launches real
  Chromium, listens for console errors and failed network requests,
  evaluates a broken-`<img>` JS check via `naturalWidth === 0`, full-page
  screenshot), `capture_all_viewports()` convenience wrapper. Verified
  end-to-end before writing the module: a throwaway script launched
  Chromium, rendered inline HTML, and wrote a real PNG — confirmed via a
  real `Read` of the output file, not assumed from a clean exit code.
- `nookguard/contact_sheet.py` (new) — `build_contact_sheet()`, a
  self-contained Pillow grid-image builder (uniform thumbnail width,
  per-cell text labels, height-capped at 900px so a tall full-page
  screenshot doesn't blow up the sheet). This is what the page-reviewer
  session actually looks at — one image containing every viewport's
  screenshot, not a raw file list.
- `nookguard/agents/page_reviewer_system_prompt.md` (new) — the fourth
  agent role. Explicitly told it does not know what page this is or what
  content it was supposed to contain, and instructed not to flag
  subjective design taste as a defect — only genuinely broken layout
  (broken_image, overlapping_elements, text_overflow, missing_element,
  spacing_inconsistency, wrong_element_count, other), each attributable to
  a specific viewport.
- `nookguard/schemas.py` — `PageReviewIssue` (category, severity,
  description, viewport) and `PageReviewResult` (page_url,
  viewports_reviewed, review_session_id, reviewer_agent_hash,
  context_bundle_sha256, issues, overall_summary_for_humans,
  `extra="forbid"`). Deliberately no overall-pass field, same pattern as
  `ContractJudgment` — the code aggregator is the only place a verdict is
  computed.
- `nookguard/agent_runner.py` — `run_page_review_session()` appended.
  Signature only accepts a contact-sheet path, page URL, and viewport
  list — structurally cannot see the page's markdown source, frontmatter,
  or any content-schema expectation (e.g. it is never told
  `off_the_clock_schema.py`'s "approved" photo-strip count), matching the
  same structural-enforcement pattern used for the observer/judge
  signatures in Commit 7.
- `nookguard/preview_aggregator.py` (new) — `aggregate_preview()`, the
  `PREVIEWED -> {PREVIEW_REVIEW_PASS, PREVIEW_REVIEW_FAIL}` decision.
  Two independent evidence sources, both code-owned: `PageCaptureReport`
  facts (broken images, console errors, failed requests — any one is an
  automatic fail, no override possible) and `PageReviewResult.issues`
  (only `critical`/`major` severities are blocking; `minor` findings are
  informational, matching the reviewer's own instruction not to flag
  subjective taste). Never reads `overall_summary_for_humans` — confirmed
  by a structural test asserting the string never appears in the
  function's own source, same technique as Commit 8's
  `test_aggregation_result_never_asserts_pass_from_free_text`.
- `nookguard/state_machine.py` — added `PREVIEWED: {..., REVIEW_ERROR}`
  (was `{PREVIEW_REVIEW_PASS, PREVIEW_REVIEW_FAIL}` only). Same rationale
  as Commit 8's `OBSERVING -> REVIEW_ERROR` addition: the page-reviewer
  session can fail the identical way any other agent session can (invalid
  JSON, an interrupted call), and section 29.5's "session interrupted ->
  REVIEW_ERROR" isn't role-scoped to the original three agents.
- `nookguard/store.py` — `preview_dir`, `save_preview_capture()` /
  `load_preview_capture()` (one JSON file per candidate holding every
  viewport's capture report plus the contact sheet path), `save_page_review()`
  / `load_page_review()`.
- `nookguard/cli.py` — three new subcommands. `mediactl integrate`
  (`SEMANTIC_PASS`/`OWNER_APPROVED` -> `INTEGRATED`) is a necessary bridge
  that did not previously exist anywhere in the CLI — NookGuard does not
  write into a page's markdown itself (H006: generator/reviewer never
  writes files directly), so wiring an approved candidate into a real
  page stays the existing, separate site workflow; this command only
  records that integration happened. `mediactl preview-capture`
  (`INTEGRATED -> PREVIEWED`) runs the real Playwright capture across
  every viewport and builds the contact sheet. `mediactl preview-review`
  (`PREVIEWED -> {PREVIEW_REVIEW_PASS, PREVIEW_REVIEW_FAIL, REVIEW_ERROR}`)
  runs the page-reviewer session and calls `aggregate_preview()`.
- New: `nookguard/tests/{test_preview.py, test_contact_sheet.py,
  test_preview_aggregator.py}` (28 tests) plus 9 new tests appended to
  `test_agent_runner.py` (`run_page_review_session`) and 6 new tests
  appended to `test_cli.py` (full `integrate` -> `preview-capture` ->
  `preview-review` pipeline, both a clean pass and a real-broken-image
  fail, plus illegal-transition rejection at both new gates).
  `test_preview.py` and `test_contact_sheet.py` exercise the real
  mechanism end-to-end (real Chromium via `file://` URLs, real Pillow
  image assembly) rather than mocking at the browser/image-library
  boundary — this environment's Playwright + Chromium install is
  confirmed genuinely functional, unlike Commit 5/7's network-dependent
  adapters, which remain unverified live here for lack of configured
  credentials.

**Bugs caught by the real test run (both fixed same session):**
- `test_run_page_review_session_raises_on_schema_validation_failure`'s
  first draft added an unrecognized extra field to a valid issue dict —
  `PageReviewIssue` has no `extra="forbid"` (only `PageReviewResult`
  does), so pydantic silently dropped the field instead of raising.
  Fixed by using a genuine type mismatch (`"issues": "not-a-list"`)
  instead of an extra-field probe.
- `cmd_preview_review` originally tried to `store.load_preview_capture()`
  in the same try block as `load_attempt`/`load_spec`, before ever
  checking the asset's current state — so calling `preview-review` on an
  asset that was never captured returned "No preview capture found for
  ..." instead of the intended "Illegal transition ... -> preview-review"
  message, inconsistent with `cmd_observe`/`cmd_judge`'s established
  check-state-first pattern. Fixed by moving the state check ahead of the
  preview-capture load, matching the existing convention exactly.

**Tests run:** `python -m pytest nookguard/tests -q`
**Result:** 187 passed, 0 failed, 0 warnings (153 from Commits 2-9 + 34
new). Includes real, end-to-end proof (not mocked) that a genuinely
broken `<img>` on a captured page still fails `preview-review` even when
the (monkeypatched) page-reviewer session itself reports zero issues —
confirming the deterministic `PageCaptureReport` facts can never be
overridden by reviewer prose, the core guarantee this commit exists to
provide.

**Commit:** `04ced79`, pushed to `origin/main` (`6ee047f..04ced79`).

**Unresolved risks:**
- `mediactl integrate` is a new, spec-adjacent bridge command, not
  something Appendix A explicitly names — it was added because no
  existing command could reach `INTEGRATED` at all, and `preview-capture`
  needs a real, confirmed page URL to screenshot. It deliberately does
  not touch any page's markdown/frontmatter itself (matching H006); if a
  future commit wants stronger proof that the named `page_url` genuinely
  contains the given candidate (rather than trusting the caller's
  assertion), that check doesn't exist yet.
- Neither `preview-capture` nor `preview-review` is wired into any real
  build/push step yet (same open item as Commit 9's `content-lint`) —
  they exist and work end-to-end through the CLI, but nothing calls them
  automatically as part of publishing a real page. Natural fit for
  Commit 11 (CI isolation) or the daily scheduled task's push step.
- The page-reviewer session itself (real Anthropic API call) is
  unverified live in this environment, same standing caveat as Commits 7
  and 8's judge/observer sessions — no API key configured in-session.
  All tests inject a fake executor per the established dependency-
  injection pattern; the Playwright/Pillow mechanics around it are the
  part that's genuinely verified end-to-end this commit.

**Next:** Commit 11 (CI isolation) — per Appendix A.

---

## Commit 11: CI isolation — DONE

**Completed:** 2026-07-22

**Research done before writing any code:** dispatched a `claude-code-guide`
subagent to confirm real Claude Code hook mechanics (which events can
actually block a tool call, the exact stdin JSON schema per tool, the exact
block-signaling output), since Appendix G says to enforce H001-H010 "via
Claude Code project hooks" and a wrong assumption here would mean the
hooks silently never fire — a worse failure mode than a wrong assumption
that pytest would catch. The subagent's summary of the deny-JSON shape
turned out subtly wrong (flat `{"permissionDecision": "deny", ...}`), so
the real hooks reference (code.claude.com/docs/en/hooks) was fetched and
read directly to get the correct nested shape
(`{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision":
"deny", "permissionDecisionReason": "..."}}`) and the exact `tool_input`
field names per tool (Bash: `command`; Write: `file_path`+`content`; Edit:
`file_path`+`old_string`+`new_string`+`replace_all`) — a concrete example of
why this project's "research before code, don't trust a paraphrase" habit
exists.

**Changed:**
- `nookguard/hooks.py` (new) — pure, unit-testable policy functions
  implementing 6 of Appendix G's 10 hook rules: `check_write_edit_protected_path`
  (H001 — denies raw Write/Edit into `nookguard_store/`, which is content-
  addressed and state-machine-owned by `store.py`; the deny reason names
  the real `mediactl` subcommand to use instead), `check_bash_generation_endpoint`
  (H002 — denies a Bash command that looks like it invokes a generation
  endpoint directly, using paired markers like `gradio_client` + `.predict(`
  rather than a bare package name, so `pip install gradio_client` is never
  false-flagged; suppressed entirely when `mediactl` or `pytest` appear in
  the command), `check_bash_blanket_git_add` (H003 — denies `git add -A`/
  `--all`/bare `.`, mechanically enforcing the standing main-CLAUDE.md rule
  instead of leaving it as prose), `check_bash_production_branch` (H004 —
  denies Bash targeting the `production` branch; the "unless CI release
  role token" exception from Appendix G is NOT implemented, since no
  release-role concept exists yet — see Unresolved risks), `check_write_existing_media_overwrite`
  (H008 — denies a Write that would overwrite an already-existing file
  under a published media directory like `public/winnie/`), and
  `check_content_lint_on_edit` (H009 — for a Write or Edit touching a `.md`
  file, simulates the hypothetical POST-edit content — current on-disk text
  with the Edit's `old_string`/`new_string` applied, or the Write's
  `content` directly — and runs the real `off_the_clock_schema.lint_off_the_clock_page`
  against it, catching a legacy-component or broken-photo-strip regression
  before it lands rather than after a separate `content-lint` run notices
  it). `evaluate_pretooluse()` is the single dispatch entry point.
- `.claude/hooks/pretooluse.py` (new) — thin wrapper implementing the real
  Claude Code command-hook contract: reads `tool_name`/`tool_input` JSON on
  stdin, calls `evaluate_pretooluse()`, prints the deny JSON (or stays
  silent) and always exits 0 (JSON-decision path, not the exit-2 path,
  since it gives a structured reason string instead of only a stderr line).
  Deliberately kept free of policy logic — everything meaningful is in
  `nookguard/hooks.py` where pytest can reach it.
- `.claude/settings.json` (new) — registers the wrapper for the
  `Bash|Write|Edit` matcher group, using exec form (`command: "python"`,
  `args: [...]`) rather than shell form, per the docs' own guidance that
  exec form avoids Windows quoting issues and works identically across
  platforms (relevant here since this project runs the hook locally on
  Windows via Desktop Commander and, once CI exercises it, on a Linux
  runner too — though CI does not currently invoke live Claude Code hooks,
  see Unresolved risks).
- `.github/workflows/nookguard-ci.yml` (new) — real GitHub Actions
  workflow, triggered on push/PR to `main` touching `nookguard/**`,
  `pyproject.toml`, `src/content/blog/**`, or the workflow file itself.
  `permissions: contents: read` only (Appendix A's "permissions" item —
  least-privilege by default, no write access granted since this workflow
  only reads the repo and uploads artifacts). Steps: checkout, Python 3.11
  setup, `pip install -e ".[dev]"`, `playwright install --with-deps
  chromium` (real Chromium binary, since `test_preview.py` does real
  browser rendering, not a mock), `pytest nookguard/tests -q --junitxml=...`,
  `actions/upload-artifact@v4` for the JUnit XML (Appendix A's "artifacts"
  item, `if: always()` so a failing run still uploads results), and a
  final `mediactl content-lint --dir src/content/blog` gate step — this
  closes the "content-lint isn't wired into any real build step yet" gap
  flagged as an unresolved risk in both Commit 9's and Commit 10's
  BUILD-LOG entries; `mediactl` already exits nonzero on `{"ok": false}`
  (see `cli.py`'s `main()`), so no extra plumbing was needed to make a
  lint failure fail the CI job.
- `pyproject.toml` — added `playwright>=1.40` to `dependencies`. This was a
  real, previously-unnoticed gap: Commit 10 added genuine Playwright usage
  in `nookguard/preview.py`, but nothing ever added `playwright` to the
  package's own declared dependencies, so a clean environment following
  only `pip install -e .` (exactly what the new CI workflow does) would
  have failed to import it. Caught while writing the CI workflow, not by
  pytest, since this local environment already had `playwright` installed
  from Commit 10's own verification work — a clean-environment gap pytest
  running in an already-populated environment can't catch on its own.
- `nookguard/tests/test_hooks.py` (new, 42 tests) — exhaustive per-rule
  coverage of every `nookguard/hooks.py` function, including explicit
  false-positive regression tests (`git add .github/workflows/x.yml` must
  NOT trigger H003's blanket-staging check; `pip install gradio_client`
  must NOT trigger H002's generation-endpoint check; editing
  `nookguard/hooks.py` itself must NOT trigger H001's protected-store
  check) — these exist because a hook that's too aggressive is its own
  failure mode, not just one that's too permissive.

**H001-H010 coverage — what's implemented here vs. genuinely out of scope:**
- H001, H002, H003, H004, H008, H009 — real Python logic in `nookguard/hooks.py`,
  wired to fire via a genuine `.claude/settings.json` PreToolUse hook.
- H006 ("Reviewer session attempts Write/Edit/Bash → Deny and invalidate
  review session") — NOT new hook code. Already structurally impossible:
  `agent_runner.py`'s `_default_executor()` (Commit 7) calls the Anthropic
  Messages API with no `tools` parameter attached at all, so a reviewer
  session has no mechanism through which it could even attempt a tool
  call. This is enforcement by absence, which is stronger than a hook that
  has to detect and block an attempt after the fact.
- H007 ("Prompt compile includes superseded source → Fail compile") — NOT
  new hook code. Already real code enforcement via `StaleCanonError` in
  `canon.py`/`prompt_compiler.py` (Commit 4), caught by `cli.py`'s
  `cmd_prompt_compile`. Not a Claude Code hook rule at all, structurally —
  it's a compile-time check inside `mediactl` itself.
- H005 ("Stop with claimed nonterminal job → Block stop, return next
  required command") and H010 ("Run report contains unsupported completion
  claim → Fail report validation") — genuinely NOT implemented this
  commit. The research step surfaced a real, documented limitation: Stop-
  hook blocking behavior is explicitly undocumented/unconfirmed in the
  official Claude Code reference (third-party sources claim exit-code-2
  forces continuation, but Anthropic's own docs don't confirm it), and both
  rules require inspecting session-transcript state (what was actually
  claimed, what the real NookGuard state machine says is true) rather than
  a single tool call's arguments — a materially bigger, higher-risk build
  than H001-H004/H008/H009's per-call checks. Building something on an
  undocumented mechanism I can't verify fires correctly, for a project
  whose whole premise is "don't claim done without evidence," would be the
  exact failure mode this project exists to prevent. Deferred, not
  forgotten — flagged here explicitly per Appendix M's own instruction not
  to silently under-scope a commit.

**Verification done (real, not just pytest):** beyond the unit test suite,
the actual `.claude/hooks/pretooluse.py` wrapper script was invoked as a
real subprocess (via Desktop Commander) with realistic stdin JSON for three
cases — a denied `git add -A`, an allowed `npm run build`, and a denied
Write into `nookguard_store/` — and its stdout/exit code matched the
documented contract exactly in all three cases. What remains genuinely
unverified in this session is narrower than "does the hook work" — it's
specifically whether Claude Code's own hook runtime, inside this exact
Cowork/Agent-SDK environment, actually invokes the wrapper per the
`.claude/settings.json` registration during a live session (the research
step flagged that hook behavior "may differ" between the CLI and SDK
usage). That live-firing question needs a human-observed test inside an
active session, not something provable from inside the session generating
the code.

**Tests run:** `python -m pytest nookguard/tests -q`
**Result:** 229 passed, 0 failed, 0 warnings (187 from Commits 2-10 + 42
new).

**Commit:** `95847b5`, pushed to `origin/main` (`4c056ee..95847b5`).

**Unresolved risks:**
- H005 and H010 are not implemented — see above. Revisit if Maurice wants
  them specifically, with a concrete plan for verifying Stop-hook behavior
  live rather than trusting undocumented third-party claims.
- H004's "unless CI release role token" exception doesn't exist yet — the
  hook denies ALL production-branch Bash operations unconditionally. Once
  Commit 12 (Release integrity) defines a real release-role/token concept,
  H004 should be revisited to allow the sanctioned exception through.
- Whether `.claude/settings.json`'s hook registration actually fires
  inside this Cowork/Agent-SDK session (as opposed to the raw Claude Code
  CLI the docs are written for) is unconfirmed — see "Verification done"
  above. The policy logic and the wrapper script are both real and tested;
  only the live end-to-end firing inside this exact environment is open.
- The GitHub Actions workflow itself has not run on GitHub's real runners
  yet — it was written directly against the real, verified hooks/Actions
  documentation and the workflow's own steps (`pip install -e ".[dev]"`,
  `playwright install --with-deps chromium`, `pytest --junitxml`,
  `mediactl content-lint`) were each individually verified to work in this
  local environment, but the first real CI run (triggered by this commit's
  own push to `main`) is the actual proof; check the Actions tab on
  `github.com/DarkLordMaurice/nestandnook-site` to confirm it went green
  before treating this as fully closed.

**Next:** Commit 12 (Release integrity) — per Appendix A.

---

## Commit 12: Release integrity — DONE

**Completed:** 2026-07-22

**Changed:**
- `nookguard/manifest.py` (new) — `content_hashed_filename(name_hint,
  candidate_sha256, extension)` (section 27's "no filename reuse... public
  filename is assigned only at release": the public filename always embeds
  the real content hash, so two different candidates can never collide on
  a name, and the same candidate always produces the same name — release
  is naturally idempotent, never accidentally destructive) and
  `ReleaseManifestEntry` (Pydantic, `extra="forbid"`, no pass/fail field —
  same "schema carries facts, code computes verdicts" split used
  throughout NookGuard). `release_manifest_sha256` is a computed property,
  not a stored field, so it can never drift out of sync with the entry it
  describes — Definition of Done's "every complete report includes ...
  release manifest hash."
- `nookguard/release.py` (new) — `publish_candidate()`, the only code path
  that ever writes public media bytes. Copies quarantined candidate bytes
  to a content-hashed path under a given `public_dir`. Re-releasing the
  identical candidate is a verified no-op (same hash already there);
  finding *different* bytes already at the exact content-hashed path
  raises `ReleaseIntegrityError` — structurally this should be impossible
  since the filename is hash-derived, so hitting it means real corruption,
  not a name collision to route around silently.
- `nookguard/production_verifier.py` (new) — `verify_against_local_build()`
  (compares a released file's bytes against the equivalent file inside a
  real `astro build` output directory — genuinely runnable and checkable
  in this environment today, no network, nothing mocked) and
  `verify_against_live_url()` (dependency-injected `fetcher`, matching the
  project's standing pattern for every other network-touching component —
  real default fetcher via `urllib.request`, unverified live in this
  session for lack of network access to the real domain, same standing
  caveat as the HF/Anthropic adapters). `verify_production()` dispatches
  between the two modes; a fetch failure or a hash mismatch both resolve
  to `PROD_MISMATCH` — "could not verify" is never silently treated as
  "verified."
- `nookguard/store.py` — `releases_dir`, `save_release_manifest()` /
  `load_release_manifest()`, keyed by `candidate_sha256` like every other
  per-candidate record in this module.
- `nookguard/cli.py` — `mediactl release` (`SEMANTIC_PASS`/`OWNER_APPROVED`/
  `PREVIEW_REVIEW_PASS` → `RELEASED`; publishes real bytes, saves the
  manifest entry, returns `release_manifest_sha256`) and `mediactl
  production-verify` (`RELEASED` → `{PROD_VERIFIED, PROD_MISMATCH}`; takes
  either `--dist-root` + `--public-root` or `--live-url`, mutually
  exclusive). No `state_machine.py` changes were needed this commit — the
  `PREVIEW_REVIEW_PASS → RELEASED` and `RELEASED → {PROD_VERIFIED,
  PROD_MISMATCH}` edges already existed from the Commit 2 synthesis, just
  unreachable through the CLI until now.
- `pyproject.toml` — no changes needed; `production_verifier.py`'s live
  fetcher uses only `urllib.request` (stdlib), no new dependency.
- New: `nookguard/tests/{test_manifest.py, test_release.py,
  test_production_verifier.py}` (25 tests, real filesystem I/O — no
  mocking needed for `publish_candidate()` or `verify_against_local_build()`
  since both are pure file operations) plus 6 new tests appended to
  `test_cli.py` (full `release` → `production-verify` pipeline reaching
  `PROD_VERIFIED` via a real simulated `astro build` output, the exact
  Appendix I regression fixture — "Repository replacement differs from
  Cloudflare-served bytes" — reproduced end-to-end and correctly landing
  on `PROD_MISMATCH`, plus illegal-transition rejection at both new
  gates).

**A real API design bug caught by the test run itself (not by inspection):**
the first draft of `verify_against_local_build()`'s 4th parameter was
named/used as `public_dir` — the exact same name as `release`'s
`--public-dir` flag (the specific leaf directory a file is written into,
e.g. `public/winnie/`). But to correctly compute where a released file
lands under `dist/`, the function actually needs the site's `public/`
**root** (the parent Astro mirrors wholesale into `dist/`), not the leaf
subdirectory — passing the same leaf value to both commands (as the first
draft of the CLI pipeline test did) silently computed the wrong `dist/`
path and produced a false `PROD_MISMATCH` even though the bytes genuinely
matched. Caught immediately because the pipeline test asserted
`prod_verified` and got `prod_mismatch` instead — a concrete example of
why "run the real pipeline test, not just the unit tests in isolation"
matters: `test_production_verifier.py`'s own direct unit tests had already
used the correct root-vs-leaf semantics and would never have caught this,
since they were written by the same reasoning that created the bug. Fixed
by renaming the parameter (and the CLI flag) to `--public-root` everywhere
in `production_verifier.py` and `cli.py`'s `production-verify` subcommand,
with an explicit `help=` string on the flag itself distinguishing it from
`release`'s `--public-dir` so a future session doesn't repeat the mistake
from the CLI's own `--help` output, not just a comment in source.

**Tests run:** `python -m pytest nookguard/tests -q`
**Result:** 258 passed, 0 failed, 0 warnings (229 from Commits 2-11 + 29
new).

**Commit:** `14cfea7`, pushed to `origin/main` (`a1374d3..14cfea7`).

**Unresolved risks:**
- The "complete report" that Definition of Done describes — one document
  carrying run ID, site commit, release manifest hash, deployment ID,
  production verification, regression result, and evidence index all
  together — is NOT assembled anywhere yet. This is a deliberate scope
  decision, not an oversight: "regression result" can't exist before
  Commit 13 (Regression corpus + canary) builds regression testing at all,
  so a capstone report assembling all seven pieces has to wait until that
  data exists to include. The individual pieces this commit produces
  (`release_manifest_sha256`, `PROD_VERIFIED`/`PROD_MISMATCH`) are real
  and available now; only their aggregation into one report is deferred.
- `--live-url` mode (`verify_against_live_url`) is unverified against the
  real, live `nestandnook.org` domain in this session — no network access
  to the real domain here, same standing caveat as the HF/Anthropic
  adapters in Commits 5 and 7. The local-build mode is the one genuinely
  exercised end-to-end this commit and is likely the more useful mode day
  to day anyway (checking a build before it's even deployed).
- No scheduled task or push script calls `mediactl release` /
  `production-verify` yet — same open item as Commits 9, 10, and 11's
  content-lint/preview gates: the mechanism is real and tested, but
  nothing in the actual daily content pipeline invokes it automatically.
  Wiring that in is a natural candidate for whenever this pipeline is
  connected to real site publishing, not necessarily this project's next
  commit.
- `site_commit` on `ReleaseManifestEntry` is an optional, caller-supplied
  field — nothing in this commit automatically populates it with the real
  current git commit SHA. A future call site (e.g. a real publish script)
  should pass `git rev-parse HEAD` in, but no such call site exists yet.

**Next:** Commit 13 (Regression corpus + canary) — per Appendix A.

---

## Commit 13: Regression corpus and canary — DONE

**Completed:** 2026-07-22

**Changed:**
- `nookguard/regression_corpus.py` (new) — the 10 named fixtures from
  Appendix I's real-incident table, each reproducing an actual failure
  mode this pipeline has to catch, dispatched to whichever real subsystem
  would actually have caught it rather than one fake unified test
  function. 8 fixtures exercise `aggregate()` directly (banana foil fused
  to crust → `FAIL_EVIDENCE`; cup collection read as unrequested
  furniture → `SEMANTIC_FAIL`; a cup left in frame after its owner was
  removed from the brief → `SEMANTIC_FAIL`; goat enclosure with a clean
  fence contradicting the reference → `FAIL_REFERENCE`; Halloween apple
  close-ups surviving after the owner was cut from the brief →
  `SEMANTIC_FAIL`; a parade-float dresser that the judge's own prose tries
  to rationalize away as "an altar" → `SEMANTIC_FAIL`, the direct,
  checkable proof that a forbidden-object finding cannot be overridden by
  narrative; and a known-clean control that must come back
  `SEMANTIC_PASS`, proving the corpus isn't just a wall of failures). 1
  fixture exercises `lint_off_the_clock_page()` directly (wrong
  photo-strip count → `LAYOUT_FAIL`). 2 fixtures are filesystem-backed and
  take a real `tmp_path`, exercising `verify_against_local_build()`
  together with `aggregate()`: a stale-bytes-plus-stray-furniture case
  that must independently fail on both semantic grounds and production
  hash grounds at once (`SEMANTIC_FAIL+PROD_MISMATCH`), and a
  repository-replacement case where the file on disk was swapped after
  release but the manifest still points at the old hash
  (`PROD_MISMATCH`). `run_regression_corpus(tmp_dir_factory)` runs all 10
  and reports a `RegressionRunReport` with a `passed` flag per fixture
  plus an `all_passed` rollup — a fixture "passing" means the pipeline
  correctly reproduced the documented real-world failure, not that
  nothing went wrong.
- `nookguard/cli.py` — added `cmd_regression_run` (new `regression-run`
  subcommand, `--tmp-root` optional, defaults to a subdirectory under
  `--store-root`) and `cmd_canary_run` (new `canary-run` subcommand,
  `--canary-page-url` optional, defaults to a local `file://` HTML page
  generated under `--store-root` if not given). `canary-run` is a genuine
  end-to-end smoke test of the pipeline's own wiring: it drives a fixed,
  version-controlled "known clean" asset contract through every real
  stage in order — spec-lock, prompt-compile, generate (stub adapter),
  register, validate, review-pack-build, observe, judge, integrate,
  preview-capture, preview-review, release, production-verify — via
  repeated real `run_cli()` calls, the exact same entry point manual and
  CI invocations use, not a separate or faked code path. It short-circuits
  and reports which named step failed the first time anything returns
  `{"ok": false}`, and on full success returns the candidate SHA-256 and
  the release manifest SHA-256 as checkable evidence the whole chain
  actually ran, not just that no exception was thrown.
- `nookguard/tests/test_regression_corpus.py` (new) — one test per fixture
  asserting it resolves to its documented expected state (plus, for the
  parade-dresser fixture, that the failure detail text actually names the
  forbidden object rather than just failing for an unrelated reason), a
  test confirming the filesystem-fixture registry has exactly its 2
  expected entries, a full-corpus test confirming all 10 run and all 10
  pass, and a categories test cross-checking the corpus's reported
  categories against Appendix I's own table verbatim — so the corpus is
  provably tied to the real spec document, not just internally
  self-consistent.
- `nookguard/tests/test_cli.py` — 4 new tests: `regression-run` reports
  all 10 fixtures passing; `canary-run` completes the full pipeline to
  `prod_verified` with the exact expected 13-step sequence (observer/judge/
  page-review sessions monkeypatched — no real Anthropic call in this
  test); `canary-run` correctly reports which step it failed at when run
  with no monkeypatching (a real, expected Anthropic-credential failure at
  the `observe` step, used here as a check that failure reporting itself
  works, not as a live-network integration test); and a direct regression
  test for the `cmd_register` bug below, confirming it now returns a
  graceful `{"ok": false, "error": ...}` instead of crashing.

**A real bug caught by the canary itself, not by inspection:** `cmd_register`
has required `--session-id` since Commit 3 (`GenerationAttempt.
generator_session_id` is a required, non-Optional Pydantic field) but every
caller in the codebase up to this commit always supplied it, so the gap was
never exercised. `canary-run`'s own register step was the first caller ever
to omit it, and the omission surfaced as a raw, unhandled
`pydantic_core.ValidationError` traceback instead of a clean CLI error —
exactly the kind of ungraceful failure this pipeline is supposed to avoid at
every layer, not just in the generation/review stages. Fixed with an
explicit early-return guard in `cmd_register` (`"register requires
--session-id (GenerationAttempt.generator_session_id is a required field,
not cosmetic)"`), fixed `cmd_canary_run`'s own register step to pass
`--session-id canary-generator` explicitly, and added
`test_register_without_session_id_returns_graceful_error_not_a_crash` so
this can't silently regress.

**Tests run:** `python -m pytest nookguard/tests -q`
**Result:** 275 passed, 0 failed, 0 warnings (258 from Commits 2-12 + 17
new).

**Commit:** `918e8a6`, pushed to `origin/main` (`ee4d711..918e8a6`).

**Unresolved risks:**
- H005/H010 (the two hooks deferred at Commit 11 due to documented
  Stop-hook unreliability) remain unimplemented — unchanged from Commit
  11's own note, not something this commit touches.
- The Definition of Done's "complete report" (run ID, site commit, release
  manifest hash, deployment ID, production verification, regression
  result, evidence index, all in one document) is still not assembled
  anywhere. This commit is what makes it buildable for the first time —
  "regression result" now genuinely exists via `regression-run` — but
  assembling the other six already-real pieces into one document is still
  a separate, not-yet-built step.
- Nothing in the real daily content pipeline calls `regression-run` or
  `canary-run` automatically yet — same standing gap as `release` and
  `production-verify` from Commit 12, and `content-lint`/preview gates
  from Commits 9-11. All four commands are real, tested, and runnable by
  hand or from CI, but no scheduled task invokes any of them yet.
- `canary-run` is deliberately NOT wired into `nookguard-ci.yml` this
  commit, unlike `content-lint` in Commit 11. Reason: `canary-run`'s
  `observe`/`judge` steps make real Anthropic API calls, and the CI
  runner has no credentials configured — adding it as a CI gate would
  just fail every run at the `observe` step, which isn't a useful signal.
  `regression-run` has no such dependency (all 10 fixtures run against
  local aggregator/schema/production-verifier logic only) and would be a
  safe, free CI addition, but wiring it in wasn't done this commit either
  — flagged here as the natural next small addition to `nookguard-ci.yml`,
  not done speculatively alongside a commit whose stated scope was the
  corpus and canary themselves.
- H004's "unless CI release role token" exception (flagged as open at
  Commits 11 and 12) remains unimplemented — could be picked up now that
  both `release` (Commit 12) and a CI-safe regression check (this commit,
  once wired into the workflow) exist, but wasn't part of this commit's
  scope.

**Next:** Commit 14+ (Private backend/dashboard) — per Appendix A, this is
explicitly the lowest-priority remaining item ("build last").

---

## Commit 14: D1-backed ledger Worker — DONE (first of the Commit 14+ series)

**Completed:** 2026-07-22

**Scope decision:** SPEC.md's own commit-order table lists row 14+ as one
line — "Backend — Worker/D1/R2/Access/dashboard and operations" — but
Appendix K's deliverables table and Appendix M's own instruction ("commit
each phase separately with an evidence report") both point the other way:
Appendix K lists Backend (Worker/D1/R2) and Dashboard (Access-protected
Astro UI) as two separate deliverable rows, and the master checklist
(section 47, page 46) lists them as two separate checklist items ("Build
Worker/D1/R2 backend..." then implicitly the dashboard after). Read the
full docx appendices this commit (H, J, K, L, M — not previously
transcribed into SPEC.md) to confirm this before writing any code, per
Appendix M's own "do not redesign the architecture around convenience"
instruction — the goal was to find the real intended split, not invent a
convenient one. This commit is scoped to D1 + the Worker API in front of
it only. R2 (artifact storage) and the Access-protected dashboard are
explicitly out of scope, deferred to Commit 15/16 — see
`nookguard-worker/README.md`'s "Scope of this commit" for the same
statement in the deliverable itself, not just here.

**Changed:**
- `nookguard-worker/migrations/0001_init.sql` (new) — the three tables
  from Appendix H ("Core SQL Sketch for D1"), transcribed column-for-
  column: `events`, `generation_attempts`, `reviews` (with `reviews`'
  `FOREIGN KEY(candidate_sha256) REFERENCES generation_attempts
  (candidate_sha256)`). Added (not in the sketch, which is explicitly a
  sketch, not a finished migration): three `CREATE INDEX` statements for
  the queries this Worker actually needs. No column, table, or constraint
  from the sketch was changed, removed, or renamed.
- `nookguard-worker/src/enforce.mjs` (new) — the two pure policy functions
  from Appendix H's "Enforce in Worker transaction" comment:
  `reviewerSessionDiffersFromGenerator` (a reviewer session can never equal
  the candidate's own `generator_session_id` — the Worker-level twin of
  spec section 27's "No generator review") and
  `requiredStagesPresentAndPolicyPass` (an approval write must name every
  required review stage and cite an aggregator verdict that is actually a
  real pass state — `semantic_pass` or `owner_approved` — not re-derive
  the policy itself; re-implementing `nookguard/aggregator.py`'s full
  policy table in JS would have been exactly the "redesign around
  convenience" Appendix M forbids). Mirrors `nookguard/hooks.py`'s
  established pattern: pure, dependency-free, no I/O.
- `nookguard-worker/src/db.mjs` (new) — data-access functions for all
  three tables, each taking a D1-shaped `db` as its first argument (same
  dependency-injection pattern as every network-touching Python module in
  this project, e.g. `production_verifier.py`'s `fetcher` parameter).
  `insertReview` is where both Appendix H invariants actually get
  enforced: it looks up the referenced `generation_attempts` row before
  inserting (the foreign key, enforced in application code rather than a
  SQLite `PRAGMA foreign_keys` trigger — see the migration file's own
  comment for why), then calls `reviewerSessionDiffersFromGenerator`.
- `nookguard-worker/src/router.mjs` (new) — the real HTTP routing/
  validation logic (`routeRequest(request, db) -> Response`), covering
  `POST`/`GET /events`, `POST /generation_attempts`,
  `GET /generation_attempts/:sha`, `POST /reviews`, `GET /reviews`.
- `nookguard-worker/src/index.mjs` (new) — the real Cloudflare Worker
  entrypoint (`export default { fetch }`), a two-line wrapper around
  `router.mjs` passing `env.DB` in. Deliberately the only untested file in
  the package — see "Unresolved risks."
- `nookguard-worker/wrangler.toml` (new) — real Cloudflare Workers config:
  Worker name, `main` entrypoint, D1 binding named `DB`, `migrations_dir`.
  `database_id` is a placeholder (`REPLACE_WITH_REAL_D1_DATABASE_ID`) —
  provisioning a real D1 database needs Maurice's own Cloudflare account,
  same standing category of gap as Cloudflare Pages' production branch
  source (Commit 1) and `--live-url` verification (Commit 12).
- `nookguard-worker/tests/fakeD1.mjs` (new) — a D1Database-shaped wrapper
  around Node's built-in `node:sqlite`, used only in tests. Real SQLite,
  real migration file, real async method shapes (`prepare().bind().run()/
  .all()/.first()`) matching Cloudflare's actual D1 binding API — what's
  faked is D1's network transport, not any SQL semantics or any of
  NookGuard's own logic, which runs completely unmodified against this
  object.
- `nookguard-worker/tests/{db,enforce,router}.test.mjs` (new) — 27 tests
  total: 6 pure policy tests against `enforce.mjs`; 11 data-layer tests
  against `db.mjs` (round trips, missing-field rejection, duplicate
  primary key rejection, the missing-foreign-key case, and both Appendix H
  invariants exercised through real inserts, not just the pure function in
  isolation); 8 HTTP-shaped tests against `router.mjs` using real global
  `Request`/`Response` objects (Node 22+), including the same reviewer-
  equals-generator rejection exercised end to end over HTTP, a malformed-
  JSON-body case, and an unknown-route case.
- `nookguard-worker/package.json` (new) — **zero dependencies.** See
  "A real environment/tooling problem, not a design choice" below for why.
- `nookguard-worker/README.md` (new) — scope statement (mirrors the top of
  this entry), layout, how to run the tests, and the same "Unresolved
  risks" list as below.
- `.github/workflows/nookguard-worker-ci.yml` (new) — path-scoped to
  `nookguard-worker/**`, least-privilege (`contents: read`), Node 22 via
  `actions/setup-node@v4`, runs `npm test` directly with **no install
  step** — the package has no dependencies to install.

**A real environment/tooling problem, not a design choice — three failed
attempts before landing on the final approach:** the original plan was
`wrangler` + `@cloudflare/vitest-pool-workers` (real Miniflare/workerd
local D1 emulation, the officially recommended way to test Workers+D1
without a live Cloudflare account). `npm install` for that dependency set
repeatedly failed to complete within this session's tooling: the sandbox's
mounted Windows path proved too slow for `wrangler`'s large native-binary
install (`workerd` is 100+MB) — even `rm -rf node_modules` on the partial
install timed out — matching this project's own already-documented finding
that "this session's Cowork sandbox mount showed unreliable file-locking
on bulk git ops" (Commit 1 BUILD-LOG), which turns out to generalize to
any bulk npm-style install too, not just git. Switched all further
Node/npm work to Desktop Commander (the real Windows filesystem), same as
git already does. Second attempt, a lighter `better-sqlite3` + `vitest`
pair, hit two separate problems: (1) both packages silently failed to
install at all — `npm config get omit` returns `dev` in this real
environment, meaning `devDependencies` are skipped by default, exactly the
same gotcha the main project `CLAUDE.md` already documents for `pagefind`
in the site's own build (fixed there by making it a real `dependency`, not
a `devDependency` — applied the identical fix here); (2) once moved to
`dependencies`, `better-sqlite3` still failed — it's a native module and
this machine has no Visual Studio C++ build tools for `node-gyp` to
compile against. Final approach: Node 24 (confirmed running on this
machine) ships `node:sqlite` and `node:test` as real built-in modules —
zero npm install, zero native compilation, and it matches this
repository's own existing convention for JS tests (`tests/tools/*.test.mjs`
already uses `node:test` + `node:assert/strict`, not a third-party
framework — confirmed by reading that file and the site's own
`package.json` `test:tools` script before choosing this, not assumed).

**Tests run:** `node --test tests/*.test.mjs` (via Desktop Commander,
real Windows Node v24.16.0 — this package is separate from the Python
`nookguard/` suite and was not run through `pytest`)
**Result:** 27 passed, 0 failed.

**Commit:** `e167ccc`, pushed to `origin/main` (`20eaf35..e167ccc`).

**Unresolved risks:**
- **No live Cloudflare account access in this sandbox.** `wrangler.toml`'s
  `database_id` is a placeholder; no real D1 database has been
  provisioned, no `wrangler d1 migrations apply` has been run against a
  live database, and no `wrangler deploy` has happened. This Worker exists
  as tested code only, not as a deployed service.
- **No workerd/Miniflare coverage — `src/index.mjs` itself is untested.**
  `tests/fakeD1.mjs` proves the schema and all real logic (`db.mjs`,
  `router.mjs`, `enforce.mjs`) against real SQLite and real
  `Request`/`Response` objects, which is genuine, non-trivial coverage —
  but it does not exercise the actual Cloudflare Workers runtime, D1's
  real network/consistency behavior, or `index.mjs`'s two lines wiring
  `env.DB` in. This is a real, explicitly named gap, not something the
  27 passing tests should be read as covering.
- **`nookguard/ledger.py` has not been cut over.** The Python CLI's
  ledger writes are still 100% local JSON-lines, completely unchanged
  since Commit 2. This Worker is a real, tested, currently-unused parallel
  backend until a future commit wires the CLI to call it over HTTP — the
  note left in Commit 2's own BUILD-LOG entry ("Commit 14 will swap the
  storage backend to D1... schema/contract unchanged") describes an
  eventual cutover that this commit makes possible but does not itself
  perform.
- **No authentication on the Worker API.** Every route in `router.mjs` is
  open — no bearer token, no Cloudflare Access check. Appendix K's
  "Dashboard: Access-protected Astro UI" describes protecting the
  *dashboard* (Commit 16); nothing in Appendix H or K describes the same
  protection for this Worker's own API. Flagged explicitly rather than
  assumed safe — this needs a real decision before this Worker is ever
  deployed to a public URL, not silently deferred.
- R2 (artifact/media byte storage) and the Access-protected dashboard are
  both explicitly out of scope for this commit — see "Scope decision"
  above. Both remain real, unbuilt items.
- `better-sqlite3` and the original `wrangler`/`@cloudflare/vitest-pool-
  workers` dependency set were abandoned for this sandbox's tooling
  reasons (see above), not because they're wrong choices for the real
  deployed system — a future session with a working native-compilation
  toolchain or more reliable large-package install conditions could
  reasonably revisit `@cloudflare/vitest-pool-workers` for genuine
  workerd-level coverage, which would close the "No workerd/Miniflare
  coverage" gap above. Not done this commit; flagged as a real
  improvement, not a rejected idea.

**Next:** Commit 15 (R2 artifact storage) or Commit 16 (Access-protected
Astro dashboard) — per Appendix K's own ordering, R2 is the more natural
next step since the dashboard will want to read/display media the Worker
is tracking.

---

## Commit 15: R2-backed candidate artifact storage — DONE

**Completed:** 2026-07-22

**Scope:** R2 (candidate/artifact byte storage) only, per Commit 14's own
"Next" note and Appendix K's ordering. The Access-protected dashboard
(Commit 16) still depends on this existing first and was not started.

**Changed:**
- `nookguard-worker/src/artifacts.mjs` (new) — `putArtifact`/`getArtifact`/
  `headArtifact`, each taking an R2-shaped `bucket` as their first argument
  (same dependency-injection pattern as `db.mjs`). `putArtifact` computes
  the real SHA-256 of the uploaded bytes via Web Crypto
  (`crypto.subtle.digest`, a real global in both Node and the Workers
  runtime — no npm dependency) and rejects with 422 if it doesn't match
  the hash named in the request path, *before* ever calling `bucket.put()`
  — an R2 PUT with a wrong or forged hash in its URL is exactly what
  content-addressed storage exists to prevent, so this has to be a real
  check, not an assumption. Keys live under a flat `candidates/` prefix,
  addressed by the full untruncated SHA-256 (mirrors
  `nookguard/hashing.py`'s `content_addressed_path()`, Commit 2 — full
  hash for internal/quarantine addressing, vs. `manifest.py`'s
  `content_hashed_filename()`, Commit 12, which truncates for public
  release names; both conventions kept consistent with their Python
  originals rather than inventing a third scheme).
- `nookguard-worker/src/router.mjs` — added `PUT`/`GET`/`HEAD
  /artifacts/:sha256`. Also changed `routeRequest`'s signature from
  `(request, db)` to `(request, env)` where `env = { db, artifacts }` —
  a real interface change made cleanly now, before anything outside this
  package depends on the old positional-`db` shape (nothing does yet; the
  Python side hasn't been wired to call this Worker at all, per Commit
  14's own "not cut over" note), rather than bolting R2 on as a second
  positional parameter.
- `nookguard-worker/src/index.mjs` — updated to build `{ db: env.DB,
  artifacts: env.ARTIFACTS }` from the real Workers env and pass it to
  `routeRequest`.
- `nookguard-worker/wrangler.toml` — added the `[[r2_buckets]]` binding
  (`ARTIFACTS`), `bucket_name` left as an explicit placeholder for the
  same reason `database_id` is (see Commit 14's entry — needs Maurice's
  own Cloudflare account).
- `nookguard-worker/tests/fakeR2.mjs` (new) — an R2Bucket-shaped in-memory
  store (`Map`-backed), implementing exactly the three methods
  `artifacts.mjs` calls (`put`/`get`/`head`) with the same async
  signatures and return shapes as Cloudflare's real R2 binding. Same
  honesty pattern as `fakeD1.mjs`: real hashing, real byte storage and
  retrieval, not R2's real network/durability/consistency behavior.
- `nookguard-worker/tests/artifacts.test.mjs` (new) — 9 tests against
  `artifacts.mjs` directly: correct-hash accept, wrong-hash reject with
  nothing stored, malformed-hash reject (wrong length, non-hex, and
  uppercase hex all explicitly rejected — Python's `hashlib.hexdigest()`
  always produces lowercase, so this stays strict rather than silently
  normalizing a format nothing else in the system produces), empty-body
  reject, idempotent re-upload of identical bytes, byte-for-byte and
  content-type round trip via `getArtifact`, 404 on unknown hash, and
  `headArtifact`'s exists/size/content-type reporting without needing to
  transfer the bytes.
- `nookguard-worker/tests/router.test.mjs` — updated every existing call
  from `routeRequest(request, db)` to `routeRequest(request, env)` (a
  `makeEnv()` helper now builds `{ db: createMigratedFakeD1(), artifacts:
  new FakeR2Bucket() }`), and added 4 new HTTP-shaped tests for the
  `/artifacts/*` routes: a real PUT-then-GET round trip verified against
  an independently-computed hash (not hardcoded, so the test proves
  agreement between two separate hash computations, not just internal
  self-consistency), the 422 wrong-hash rejection over real HTTP, a 404 on
  an unstored hash, and `HEAD` reporting `content-length` with an empty
  body and 404ing cleanly when absent.
- `nookguard-worker/README.md` — scope section updated to describe both
  Commit 14 and 15 together, layout section covers the three new files,
  "Unresolved risks" gained the R2-specific gaps (below) plus a new
  explicit note that this commit deliberately ships no delete/lifecycle
  route for artifacts (content-addressed bytes are meant to be immutable
  once written, per section 27 — a real lifecycle policy for
  never-released quarantine bytes is a genuine future need, not designed
  here).

**Tests run:** `node --test tests/*.test.mjs` (Desktop Commander, real
Windows Node v24.16.0)
**Result:** 40 passed, 0 failed (27 from Commit 14 + 13 new: 9 in
`artifacts.test.mjs`, 4 in `router.test.mjs`).

**Commit:** `019f812`, pushed to `origin/main` (`04d9b9c..019f812`).

**Unresolved risks:**
- Same live-Cloudflare-account gap as Commit 14, now covering R2 too:
  `bucket_name` in `wrangler.toml` is a placeholder, no real bucket has
  been created, nothing has actually been deployed.
- Same no-workerd/Miniflare-coverage gap as Commit 14, now covering
  `artifacts.mjs` too — `tests/fakeR2.mjs` proves the application logic
  against a real in-memory store with real hashing, not R2's actual
  network/consistency behavior.
- No authentication on the new `/artifacts/*` routes either — same open
  gap as the D1 routes, flagged once in Commit 14's entry and not
  re-solved here.
- No object deletion or lifecycle policy for R2 artifacts — see README's
  "Unresolved risks" for the reasoning (content-addressed bytes are meant
  to be immutable; a real lifecycle rule for abandoned quarantine bytes is
  a genuine future need).
- Neither `nookguard/ledger.py` (D1) nor the Python generation adapter's
  local quarantine writes (Commit 5's `store.py`, which would be R2's real
  caller) have been cut over to this Worker. Both remain fully local,
  unchanged.

**Next:** Commit 16 (Access-protected Astro dashboard) — the last item in
the Commit 14+ backend series, reading from this Worker's D1 + R2 APIs.

---

## Commit 16: Access-protected owner-queue dashboard — DONE

**Completed:** 2026-07-22

**Scope:** the last item in the Commit 14+ backend series (Appendix A row
14+; Appendix K's "Backend" and "Dashboard" deliverable rows). Closes out
the series — Commit 17+ (if any) would be a genuinely new phase, not a
continuation of "build the backend."

**Research before code, per Appendix M's own instruction not to redesign
around convenience:** read the docx pages for Appendix E ("Owner Decision
Packet") and Appendix J ("Operational Runbook") in full before writing any
schema, since SPEC.md only ever named them in a summary sentence and never
condensed their actual content (confirmed via `grep -rniE
"owner.?decision.?packet"` across the whole repo returning zero hits
before this commit). Also ran a targeted subagent search of
`nookguard/owner_queue.py` (Python, already existed since before this
commit, wired into `cmd_judge`) to confirm its exact real field names
before designing the D1 table — the subagent's report: a JSON-file-backed
`OwnerQueue` class with `enqueue`/`list_pending`/`resolve`, fields
`asset_id, candidate_sha256, reasons, risk_tier, result_state, status,
queued_at, resolved_at, resolved_by, decision`, explicitly self-documented
as "a TRACKING/VISIBILITY mechanism, not a publish gate," with no CLI
command to list or resolve entries and no Pydantic schema. The new
`owner_queue` D1 table (below) reproduces every one of those fields under
the same name, so a future cutover doesn't have to rename anything, and
adds exactly what Appendix E's own table has that the Python side didn't
yet: `question`, `requirement_id`, `evidence_json`, `consequences_json`.

**Changed — nookguard-worker (D1 + Worker API):**
- `nookguard-worker/migrations/0002_owner_queue.sql` (new) — the
  `owner_queue` table (see file's own comment for the full field-by-field
  reasoning above), plus two indices (`status`, `candidate_sha256`).
  Appendix E's "Options" row (the five valid decisions) is explicitly NOT
  a schema constraint — enforced in application code instead, matching
  Appendix H's already-established "enforce in Worker transaction, not in
  schema" pattern. Appendix E's "No persuasion" row is explicitly NOT
  enforced anywhere — flagged as a genuine, unclosable-by-code gap in
  "Unresolved risks," not silently ignored.
- `nookguard-worker/src/enforce.mjs` — added `OWNER_DECISION_OPTIONS`
  (the five Appendix E values: `approve_exact_hash`, `reject`,
  `revise_spec`, `regenerate`, `defer`) and
  `isValidOwnerDecisionOption()`, same pure-function pattern as the
  existing two rules.
- `nookguard-worker/src/ownerQueue.mjs` (new) — `enqueueOwnerDecision`,
  `listOwnerDecisions` (status: pending/resolved/all), `getOwnerDecision`,
  `resolveOwnerDecision`. Same D1 dependency-injection pattern as
  `db.mjs`. `enqueueOwnerDecision` checks the same FK-in-application-code
  invariant as `insertReview` (candidate_sha256 must reference a real
  `generation_attempts` row). `resolveOwnerDecision` rejects resolving an
  already-resolved entry a second time (409) — a decision packet is acted
  on once, matching section 27's "no fix in place" philosophy applied to
  a new context.
- `nookguard-worker/src/access.mjs` (new) — real Cloudflare Access JWT
  verification: RS256 signature check via Web Crypto
  (`crypto.subtle.importKey`/`.verify`), audience check, expiry check.
  Deliberately fails OPEN (`{ ok: true, skipped: true }`) when no
  `audience` is configured — this Worker has no live Access application
  yet (same standing gap as D1/R2 provisioning), so requiring a JWT
  unconditionally would make every route permanently unusable rather than
  reflecting the honestly-open state already documented in Commits 14/15.
  Becomes mandatory and fails CLOSED (401) once `env.ACCESS_AUD` is a
  real, non-empty value.
- `nookguard-worker/src/router.mjs` — added `POST /owner_queue`,
  `GET /owner_queue?status=`, `POST /owner_queue/:entry_id/resolve` (the
  one route gated behind `verifyAccessJwt` — the only human-triggered
  write action in the whole Worker, per Appendix J: "Maurice can see and
  resolve only the owner queue from the private dashboard"). Also added
  CORS handling (`OPTIONS` preflight, `access-control-allow-*` headers on
  every response) for the dashboard's cross-origin local-dev case — see
  README "Deployment topology" for why this isn't the primary security
  mechanism for the real deployed system. **A real security fix made
  during this commit, not left for later:** the resolve handler
  originally would have trusted a client-supplied `resolved_by` field
  even when Access was configured and verified — fixed so that when
  Access verification actually ran (not skipped), the verified JWT's own
  `email` claim overrides whatever `resolved_by` the client sent,
  preventing anyone who can reach the route from claiming to be Maurice.
  Proven by a real test asserting the persisted record's `resolved_by`
  matches the JWT's email, not the spoofed body value it was sent
  alongside.
- `nookguard-worker/src/index.mjs` — now wires `accessAudience:
  env.ACCESS_AUD` and a real `jwksFetcher` (fetching
  `https://<ACCESS_TEAM_DOMAIN>/cdn-cgi/access/certs`, only constructed
  when `env.ACCESS_TEAM_DOMAIN` is set) into `routeRequest`.
- `nookguard-worker/wrangler.toml` — added the Access config as a
  **commented-out** `[vars]` block, not placeholder strings. **A second
  real bug caught and fixed before it shipped:** the first draft set
  `ACCESS_AUD = "REPLACE_WITH_REAL_..."` as an actual (placeholder)
  value — but `access.mjs` treats ANY truthy `audience` as "verification
  required," so a literal placeholder string would have silently 401'd
  every resolve request forever once deployed, looking configured
  without being configured, which is worse than the genuinely-open
  default already documented since Commits 14/15. Caught by re-reading
  my own comment against my own code's actual `if (!audience)` check
  before moving on, not by a test (there's no test that deploys this
  literal file) — worth noting as a real instance of the standing "verify
  claims against actual behavior" discipline catching a self-authored bug
  in configuration, not just in code.
- `nookguard-worker/tests/fakeD1.mjs` — changed from loading a single
  hardcoded `0001_init.sql` path to loading every `migrations/*.sql` file
  in sorted filename order, matching how `wrangler d1 migrations apply`
  itself works. Necessary the moment a second migration file existed.
- `nookguard-worker/tests/fakeR2.mjs`, `tests/testJwt.mjs` (new) — the
  latter mints real RS256 JWTs via Web Crypto
  (`crypto.subtle.generateKey`/`.sign`) against a self-generated test
  keypair, so `access.test.mjs` exercises genuine cryptographic
  verification, not a stub. Honestly caveated (file's own comment): this
  proves the verification algorithm is correct, not that a real
  Cloudflare-issued token verifies against this code — that needs a live
  Access application.
- `nookguard-worker/tests/{access,ownerQueue}.test.mjs` (new),
  `tests/{enforce,db,router}.test.mjs` (modified) — 29 new tests: 9 for
  `access.mjs` (skip-when-unconfigured, missing header, valid token,
  wrong audience, expired token, wrong-key signature failure, unknown
  kid, malformed token, unsupported alg), 11 for `ownerQueue.mjs`
  (round trip, missing fields, FK check, duplicate entry_id, status
  filtering, successful resolve with consequences, invalid decision
  option, unknown entry_id, double-resolve rejection, missing resolve
  fields, all five options individually accepted), 2 for
  `isValidOwnerDecisionOption`, 1 fixed stale assertion in `db.test.mjs`
  (the "creates all three tables" test needed updating to four once
  `owner_queue` existed), 6 new router-level HTTP tests covering
  `/owner_queue` end to end including the Access-configured-vs-not paths
  and CORS.
- `nookguard-worker/README.md` — scope/layout/unresolved-risks sections
  updated to describe Commit 16 alongside 14/15.

**Changed — nookguard-dashboard (new sibling Astro project):**
- `nookguard-dashboard/` (new package: `package.json`, `astro.config.mjs`,
  `src/pages/index.astro`, `.env.example`, `README.md`). A deliberately
  **separate** Astro project from `nestandnook-site`, not a route folded
  into the public site — see `astro.config.mjs`'s own comment: mixing an
  internal owner-decision dashboard into the same deploy as fully public
  marketing content means an Access misconfiguration on one path could
  expose the other. `astro` is a real `dependency`, not `devDependency`
  (same environment `omit=dev` fix already applied in `nookguard-worker`
  and the main site).
- `src/pages/index.astro` — the entire real UI in one file: a static
  shell (this is a static-build Astro project, same model as the main
  site — no SSR) plus a client-side `<script>` that fetches
  `/owner_queue` from the Worker, renders each pending entry (question,
  asset/candidate IDs, risk tier, result state, reasons as tags, evidence
  in a `<details>` block), and posts resolutions through the five
  Appendix E options plus a consequences summary and permanence field.
  `WORKER_BASE_URL` defaults to `/api` (same-origin, relative) rather
  than an absolute cross-origin URL — see README "Deployment topology"
  for the real reasoning: same-origin means the browser's Access session
  cookie and Cloudflare's edge-attached `Cf-Access-Jwt-Assertion` header
  both just work without CORS/cross-site-cookie complexity, which is why
  the recommended real deployment routes the Worker at a path
  (`admin.nestandnook.org/api/*`) under the same Access-protected
  hostname as the dashboard, not as its own separate origin.
- `.github/workflows/nookguard-dashboard-ci.yml` (new) — path-scoped,
  least-privilege, `npm install && npm run build` (real `astro build`,
  the meaningful gate here since this package has no unit-testable logic
  of its own — everything it calls is already covered by
  `nookguard-worker-ci.yml`).
- `README.md` — the honest, still-open manual steps to make "Access-
  protected" real (Pages project, Access application, route rule), the
  identity-flow explanation (JWT email → `resolved_by`, matching the
  security fix above), and unresolved risks.

**A real, checkable "clean run" for the exit criteria (Appendix M: "do not
claim completion before the phase exit criteria are demonstrated"):**
```
npm install --no-audit --no-fund   # 329 packages, ~15s, no errors
npm run build                       # astro build
```
produced real output: `dist/index.html`, 10,678 bytes, confirmed present
via `Get-ChildItem`/`Get-Content` after the build, not assumed from the
build log alone.

**Tests run:** `node --test tests/*.test.mjs` (nookguard-worker, Desktop
Commander, real Windows Node v24.16.0) + `npm run build`
(nookguard-dashboard, same environment)
**Result:** 69 passed, 0 failed (40 from Commits 14-15 + 29 new). Dashboard
build: 1 page built, 0 errors.

**Commit:** `7441005`, pushed to `origin/main` (`308ca2a..7441005`).

**Unresolved risks:**
- **No live Cloudflare account access in this sandbox** — same standing
  category as every prior commit in this series. No Pages project, no
  Access application, no route rule connecting a real deployed dashboard
  to a real deployed Worker exists. Both packages are tested/built code
  only, not deployed services.
- **No end-to-end browser test of the dashboard against a real or
  Miniflare-emulated Worker.** `astro build` producing real static output
  is verified; a human clicking through an actual resolve flow in a real
  browser against a running backend is not, and can't be from this
  sandbox (no Chrome/Playwright wired to a running `astro preview` +
  `wrangler dev` pair was attempted).
- **Appendix E's "No persuasion" row is not mechanically enforced** —
  there is no reliable code-level test for "is this text persuasive."
  Documented as a genuine, permanent gap in both the migration file's
  comment and the README, not silently assumed solved.
- **`resolved_by` is a trusted client value whenever Access is not yet
  configured** (i.e., today, on every route, matching Commits 14/15's
  existing "no authentication" gap) — the dashboard sends an explicit
  placeholder string (`dashboard-unauthenticated-fallback`) rather than a
  real name specifically to keep this honest in the persisted record
  until Access is actually wired up.
- **No pagination/sorting/search on the dashboard's entries list** — a
  real gap if the owner queue ever grows past the volumes NookGuard's own
  paced-publishing constraints imply for the near term.
- **Neither `nookguard/owner_queue.py` (Python) nor `nookguard/ledger.py`
  nor the generation adapter's local quarantine writes have been cut
  over** to call this Worker. All three remain fully local, unchanged —
  the entire Commit 14+ backend series (D1, R2, this dashboard) is real,
  tested, and currently unused parallel infrastructure until a future
  commit wires the Python CLI to call it instead of writing local files.
  This is the single biggest standing gap across all four commits in this
  series and is worth stating plainly here, not just per-commit: nothing
  in the actual daily NookGuard pipeline talks to any of this yet.

**Next:** the Commit 14+ backend/dashboard series (Appendix A row 14+) is
now complete — D1 (14), R2 (15), and the Access-protected dashboard (16)
all exist as real, tested code. What remains, not yet scoped as a
numbered commit: (1) the Python↔Worker cutover named as the single
biggest gap above, (2) the live Cloudflare provisioning steps documented
in both packages' READMEs, (3) Appendix M's "complete report" aggregating
run ID/site commit/release manifest hash/deployment ID/production
verification/regression result/evidence index into one document (flagged
as buildable-but-not-built since Commit 13). Per Appendix M's own
framing, this project's core promise — "a canary asset travels from
locked contract through fresh Claude reviews, typed page integration,
staging, release manifest, Cloudflare deployment, and exact public byte
verification, while every historical critical regression is correctly
rejected" — was already demonstrated in Commit 13; everything in the
14-16 series is real but genuinely supplementary operational tooling on
top of that already-proven core.

---

## Commit 17: Completion and Evidence Protocol (run-report) — DONE

**Completed:** 2026-07-22

**Why this commit, not something else:** Appendix A's build-order table
has no row after "14+ Backend" — confirmed directly against the source
docx this commit (not just the condensed SPEC.md) via a targeted page-
image read of Appendix A (p.47) and Appendix M (p.53). Appendix M turned
out to be titled "Final Instruction to Claude," not the 16-reference list
SPEC.md's condensation guessed — that reference list actually lives in
Appendix L. With no further pre-specified commit, the one concretely
unbuilt deliverable already named in this project's own spec is Section
24, "Completion and Evidence Protocol" (p.26), quoted in full:

> "Claude's final message is not the record of truth. NookGuard generates
> run-report.json, run-report.md, and a compact owner summary from ledger
> events."
>
> "Claude may say 'complete' only when terminal_status is PROD_VERIFIED.
> Otherwise it must say exactly what remains and link the blocker
> receipt."

with a worked example schema (`run_id, terminal_status, repository_commit,
release_manifest_sha256, production_deployment_id, assets{approved,
rejected, needs_owner, production_verified}, regression_suite{passed,
failed}, evidence_index`). This is the same gap the Commit 16 "Next"
section already flagged as buildable-but-not-built since Commit 13, now
actually built.

**Research before code:** three research subagent passes before writing
anything — (1) confirmed Appendix A has no rows after "14+," and located
the real Section 24 text (the condensed SPEC.md only had a single
paraphrased bullet, not the full passage or example schema) by reading
the source docx's actual page images directly; (2) mapped the existing
`nookguard/` Python package (24 source files, `mediactl` CLI with 20
subcommands, pytest convention, 25 test files) to avoid rebuilding
anything that already exists — confirmed no `run_report`/`evidence_index`/
`terminal_status` concept existed anywhere yet; (3) pulled exact,
verbatim signatures for `state_machine.AssetState` (25 states, real
`TRANSITIONS` graph), every `ledger.append(event_type=...)` literal used
across all 17 call sites in `cli.py`, `manifest.ReleaseManifestEntry`'s
real fields, and `regression_corpus.RegressionRunReport`'s real shape —
specifically to avoid guessing field/state names wrong in a report meant
to be the project's own definition of "actually done."

**Changed files:**
- `nookguard/run_report.py` (new) — the whole feature. `build_run_report()`
  reads a run's real ledger events (`ledger.for_run(run_id)`) plus each
  touched asset's real current state (`store.get_state(asset_id)`) —
  never a session's own narrative — and buckets every asset into
  `approved` / `rejected` / `needs_owner` / `production_verified` /
  `in_progress`, using `state_machine.py`'s own real terminal/non-terminal
  state partition (the 9 no-outgoing-transition "regenerate only" states
  are `rejected`; `PROD_VERIFIED` is the one success terminal; everything
  else buckets off `TRANSITIONS`'s own shape, not a new hand-picked
  taxonomy). `terminal_status` is `PROD_VERIFIED` only when `blocking` is
  empty — computed, never asserted: blocking accumulates one message per
  real reason (no assets recorded, an asset with no state at all in the
  store, any `needs_owner`, any still-mid-pipeline asset, any asset
  `approved` but not yet `production_verified`, or a failing regression
  corpus run). `render_markdown()` and `render_owner_summary()` produce
  the other two named artifacts. `write_run_report()` writes all three
  files (`run-report.json`, `run-report.md`, `owner-summary.txt`) plus
  the evidence index JSON.
  **Three honest, documented gaps against the spec's literal example
  schema** (all in the module's own docstring, not hidden): (1)
  `release_manifest_sha256` is shown as one top-level field in the spec's
  example, but `ReleaseManifestEntry` computes that hash per released
  asset and no single aggregate manifest file exists anywhere in this
  pipeline — this module derives one instead (canonical-JSON SHA-256 of
  the sorted list of every `asset.released` event's own
  `release_manifest_sha256` for the run), documented as a DERIVED value,
  not a pre-existing file's hash. (2) `production_deployment_id` has no
  source anywhere in this Python package (no Cloudflare Pages API call
  exists on this side) — accepted only as an optional caller-supplied
  override via `--production-deployment-id`, defaults to `None`, and
  deliberately never gates `terminal_status` (withholding completion for
  a field this side genuinely cannot produce would be its own kind of
  dishonesty). (3) the spec's example shows `evidence_index` as an
  `r2://...` URL; the Python pipeline is not wired to `nookguard-worker`/
  R2 yet (Commit 16's single biggest standing gap) — this module writes a
  REAL local evidence index JSON (every ledger event for the run, each
  with its own `payload_sha256`) and points `evidence_index` at that real
  local path, not a fabricated `r2://` URL.
- `nookguard/cli.py` — added `cmd_run_report` and the `run-report`
  subparser (`--out-dir`, `--production-deployment-id`), following the
  exact existing `cmd_*` convention (`(args) -> dict[str, Any]`,
  `_ledger(root)`/`_store(root)` access). `ok` mirrors the boxed
  completion rule: `true` only when `terminal_status == "PROD_VERIFIED"`,
  with the full result dict (including `blocking`) always returned
  regardless, matching how `cmd_run_preflight` already returns its full
  `checks` dict on both success and failure.
- `nookguard/tests/test_run_report.py` (new) — 10 tests. Nine are
  unit-level against `build_run_report`/`write_run_report`/
  `render_markdown`/`render_owner_summary` directly, with a stubbed
  `regression_runner` for speed/determinism: empty run → `INCOMPLETE`
  with the right message; a hand-built mix of `PROD_VERIFIED` /
  `OWNER_REJECTED` / `NEEDS_OWNER` / `RELEASED` assets buckets correctly
  and blocks for the right reasons; a passing-assets-but-failing-
  regression case still blocks; an asset referenced in the ledger with no
  recorded store state is surfaced in `unknown_state_assets` and blocks,
  rather than silently vanishing from the counts; the derived
  `release_manifest_sha256` is a real 64-char hex digest that is NOT a
  literal passthrough of the per-asset hash; no releases yields `None`;
  the evidence index is a real file on disk whose contents match the
  real ledger events; markdown/owner-summary rendering reflect blocking
  state correctly. The tenth test is a real end-to-end integration run:
  drives the actual `mediactl` CLI through every real step (`spec-lock`
  through `production-verify`, `observe`/`judge`/`preview-review`
  monkeypatched at `nookguard.cli`'s own imported names — same
  established pattern as `test_cli.py`'s `_drive_to_preview_review_pass`,
  since this sandbox has no live Anthropic credentials for those three
  real Claude-review-agent calls — everything else runs for real,
  including the actual `production-verify` local-build byte comparison),
  then runs the real, unmocked `mediactl run-report` command — including
  the real regression corpus, no stub — and confirms `terminal_status ==
  "PROD_VERIFIED"`, `blocking == []`, and all four output files genuinely
  exist on disk. First attempt at this test used the real (unmocked)
  `observe` command directly and failed with a real, informative error
  ("Could not resolve authentication method") — the fix was switching to
  the established monkeypatch pattern already used elsewhere in this
  codebase's own test suite for exactly this sandbox limitation, not
  inventing a new one.

**Tests run:** `python -m pytest nookguard/tests/test_run_report.py -v`
then the full suite `python -m pytest nookguard/tests/ -q` (both via
Desktop Commander, real Windows Python 3.14.5)
**Result:** 10/10 new tests passed; full suite 285/285 passed, 0 failures
— confirms no regression anywhere else in the package from wiring a new
CLI subcommand and a new import into `cli.py`.

**Commit:** `9587eab`, pushed to `origin/main` (`edfdd0b..9587eab`).

**Unresolved risks:**
- The three documented gaps against the spec's literal example schema
  (derived vs. literal `release_manifest_sha256`, no automatic
  `production_deployment_id`, local vs. `r2://` `evidence_index`) are
  real and permanent until the Python↔Worker cutover named in Commit 16
  happens — they are not bugs to fix later, they are honest reflections
  of what this side of the pipeline can actually produce today.
- `regression_runner` defaults to running the REAL Appendix I corpus
  fresh on every `run-report` call — correct per the "don't trust a
  narrated prior result" principle, but means `run-report` is not free;
  it re-executes all 10 fixtures every time it's called. Not currently a
  problem (the corpus runs in a couple seconds per the existing
  `test_regression_corpus.py` suite), but worth knowing if the corpus
  ever grows substantially.
- No scheduled task or CI step calls `mediactl run-report` yet — it
  exists and is tested, but nothing in the actual daily pipeline
  generates a completion report today. Wiring it into whatever eventually
  drives NookGuard end-to-end in production (still not built — see every
  prior commit's "Python side still not cut over to D1/R2" note) is a
  future step, not this one.
- `assets["in_progress"]` and `unknown_state_assets` are both non-spec
  additions beyond the 7 named fields in Section 24's example — a
  deliberate choice for honesty (nothing about a run's real state should
  be able to silently disappear from the report just because the spec's
  own example didn't anticipate it), documented here in case a future
  reader wonders why the schema has more than 7 top-level report fields.

**Next:** no further commit is pre-specified anywhere in Appendix A or
elsewhere in the spec. The standing, named gaps across the whole Commit
14-17 series remain: the Python↔Worker cutover (D1/R2/Access dashboard
sit as real, tested, currently-unused parallel infrastructure), the live
Cloudflare provisioning steps documented in both `nookguard-worker/` and
`nookguard-dashboard/`'s READMEs, and now also wiring `mediactl
run-report` into whatever process is meant to call it in a real run.
Absent further direction, this project's spec-driven build sequence is
complete — everything named in Appendix A plus Section 24 exists as real,
tested code.

---

## Commit 18: live canary + acceptance test — two real defects found and fixed in `run_report.py`

**Completed:** 2026-07-22

**Context:** Maurice ordered a real, non-simulated operational acceptance
test — a genuine low-risk new asset through the real state machine, real
Hugging Face generation, real fresh Claude observer/judge sessions (no
monkeypatch/stub/simulate), the historical regression corpus through the
real observer/judge process, real `mediactl run-report` evidence, and an
explicit instruction not to declare NookGuard operational unless the real
production hash matches the approved hash and every critical regression
gets its expected verdict. Full results, including the hard technical wall
this run hit and everything it could not verify, are reported to Maurice
directly (not duplicated here) — this entry covers only the real code
changes made as a direct result of running the test for real.

**Two real defects in already-shipped Commit 17 code, both caught only
because the tool was actually run against a real store, not because
anything in its own test suite caught them first:**

1. **A `REVIEW_ERROR` asset could make a run report `terminal_status:
   PROD_VERIFIED` / `ok: true`.** The live canary's single asset hit a
   real Anthropic API authentication failure during `observe` (this
   sandbox has no `ANTHROPIC_API_KEY` anywhere — confirmed absent from
   process, User, and Machine environment scopes) and correctly
   transitioned to `REVIEW_ERROR`. `run_report.py`'s original
   `REJECTED_STATES` set folded `REVIEW_ERROR` in with genuinely resolved
   content rejections (`SEMANTIC_FAIL`, `OWNER_REJECTED`, etc.), and
   nothing in the blocking logic distinguished "the review process itself
   never completed" from "review completed and correctly said no." The
   result: a run whose only asset was never actually reviewed by anything
   still reported itself complete and verified — precisely the
   self-certifying false positive this entire project exists to prevent,
   now found in its own completion-reporting code.
2. **`default_regression_runner` crashed on a second real call against
   the same store.** Re-running `mediactl run-report` — a completely
   normal thing to do — hit a raw `FileExistsError` inside the regression
   corpus's `otter_aviary_stale_bytes_and_furniture` fixture, because the
   scratch directory used for fixture files was reused as-is across calls
   (only `exist_ok=True` at the top level) while that fixture creates its
   own subdirectories assuming a genuinely fresh directory every time —
   true under pytest's `tmp_path`, false on a second real invocation.

**Changed files:**
- `nookguard/run_report.py` — split the old single `REJECTED_STATES` into
  three distinct sets: `CONTENT_REJECTED_STATES` (a real, resolved,
  no-further-action rejection — unchanged behavior), `PROCESS_ERROR_STATES`
  (`REVIEW_ERROR` — always blocks, always surfaced by name, never folded
  into "rejected"), and `PROD_MISMATCH_STATES` (`PROD_MISMATCH` — pulled
  out for the same reason in the other direction: released bytes not
  matching approved must always block a "production verified" claim).
  `RunReport.assets` gained two new keys, `process_error` and
  `prod_mismatch`, in both the dataclass and the markdown/owner-summary
  renderers. `default_regression_runner` now wipes and recreates its
  scratch directory (`shutil.rmtree` + `mkdir`) on every call instead of
  assuming it starts empty — safe, since that directory holds nothing but
  disposable fixture scratch files, never real evidence.
- `nookguard/tests/test_run_report.py` — updated the two existing
  `assets == {...}` dict-equality assertions for the two new keys, and
  added three new regression tests specifically for this incident:
  `test_review_error_never_yields_prod_verified`,
  `test_prod_mismatch_never_yields_prod_verified`, and
  `test_default_regression_runner_is_safe_to_call_twice_against_same_store`
  — all three would have failed against the pre-fix code, and exist so
  this exact class of bug cannot silently regress.

**Tests run:** `python -m pytest nookguard/tests/test_run_report.py -v`
(both immediately after each fix and again after both), then the full
suite `python -m pytest nookguard/tests/ -q` (all via Desktop Commander,
real Windows Python 3.14.5)
**Result:** 12/12 in `test_run_report.py` (up from 10 — 3 new, 1 removed
duplicate count is not applicable, net +3 including the twice-call test);
full suite 288/288 passed, 0 failures (up from 285 — confirms no
regression anywhere else from the bucketing change).

**Real evidence this fix is correct, from the live run itself, not just
from the new unit tests:** re-running `mediactl run-report` against the
actual live-canary store after the fix produced
`"ok": false, "terminal_status": "INCOMPLETE", "assets": {"process_error":
1, ...}, "blocking": ["1 asset(s) hit a review-process error (state:
review_error) -- the review process itself did not complete..."]` — the
honest, correct answer, replacing the pre-fix run's incorrect `"ok": true,
"terminal_status": "PROD_VERIFIED"`.

**Commit:** `0786322`, pushed to `origin/main` (`12e21de..0786322`).

**Unresolved risks:** none new beyond what Commit 17 already documented —
this entry is a correctness fix to already-shipped code, not new scope.
The underlying reason this bug existed to be found — no live
`ANTHROPIC_API_KEY` anywhere in this environment, so `observe`/`judge`
cannot be exercised for real here — remains exactly the standing gap
Commit 7's `agent_runner.py` already documented ("Not exercised live in
this session (no API key configured here)"); this commit does not close
that gap, it only fixes how honestly the reporting layer behaves when
that gap is hit.

**Next:** none pre-specified; see Maurice's direct acceptance-test report
for the full picture of what this live run did and did not verify.

---

## Commit 19: Claude Code CLI reviewer transport + REVIEW_ERROR process recovery — DONE

**Completed:** 2026-07-23

**Why this commit:** Maurice's explicit instruction following the Commit 18
live-canary result — the canary's single hard technical wall was that
`observe`/`judge` go through `agent_runner._default_executor`, a direct
Anthropic Messages API call requiring `ANTHROPIC_API_KEY`, which this
environment has never had (confirmed absent from process/User/Machine
environment scopes). Maurice's instruction: replace that default transport
with fresh, non-interactive Claude Code CLI (`claude -p`) processes running
under the operator's own authenticated Claude subscription instead, make
`REVIEW_ERROR` a recoverable process state (not a dead end) for the exact
unchanged candidate that hit it, add `mediactl auth-check`, and gate real
generation on it passing first.

**Research before code:** read `nookguard/exceptions.py` (the
`NookGuardError` subclass convention), `nookguard/agent_runner.py` in full
(the exact `SessionExecutor = Callable[[str, list[dict]], str]` contract
every transport must match), `nookguard/state_machine.py` in full (the
`TRANSITIONS` dict vs. `_REGENERATE_SOURCES` set are two independent
structures, not derived from each other), `nookguard/ledger.py` in full
(append-only, `for_asset()`, payload shape), and `nookguard/cli.py`'s
`cmd_observe`/`cmd_judge` (confirmed both `observation.error` and
`judgment.error` ledger events already carry `candidate_sha256` in their
payload — no schema change needed to build retry guards on top). Then
empirically probed the real machine (a throwaway script, deleted after):
confirmed the bundled Claude Code CLI is real and present at
`%APPDATA%\Claude\claude-code\2.1.217\claude.exe` (not on PATH by default),
confirmed `claude auth status` returns genuinely unauthenticated
(`{"loggedIn": false, "authMethod": "none"}`), and confirmed the real JSON
envelope shape a `claude -p --output-format json` call returns on an auth
failure: exit code 1, `{"type":"result","is_error":true,"result":"Not
logged in · Please run /login", ...}` — this module's auth-failure
detection is built on that observed shape, not a guess.

**Two real bugs caught by the probe script itself, before any test ever
ran:** (1) `"\C"` inside the module's non-raw docstring (referencing
`%APPDATA%\Claude\...`) produced a real `SyntaxWarning: invalid escape
sequence` — fixed by making the docstring a raw string (`r"""`). (2) the
"disable all tools" case was originally written as `--tools none`, a
guess; re-reading the real `claude --help` output showed the documented
convention is an empty string (`--tools ""`), and a live probe call with
`tools=""` confirmed the CLI accepted it (reached the real
`auth_unavailable` classification rather than an argument-parsing error)
— fixed to always pass `--tools` with the real value, including `""`.

**Changed files:**
- `nookguard/cli_reviewer.py` (new) — the whole `ClaudeCodeCliReviewer`
  transport. `resolve_claude_cli_path()` (explicit override →
  `NOOKGUARD_CLAUDE_CLI_PATH` env var → PATH → bundled desktop-app install
  dir, returns `None` rather than raising, matching
  `adapters/huggingface.py`'s `_resolve_hf_token` convention for a
  different missing-credential problem). `run_claude_cli()` is the one
  real subprocess call site — `subprocess_runner`/`session_id_factory`/
  `claude_path` are all injectable for tests, matching this codebase's
  existing DI convention. Isolation is enforced by the actual argv, not
  documentation: `--no-session-persistence` (nothing saved to resume),
  freshly generated `--session-id` every call, `--tools` as an explicit
  allowlist (`""` = none), no `--mcp-config` (no MCP servers reachable),
  `--system-prompt` (full replace, never `--append-system-prompt`).
  `ClaudeCliError` carries a fixed, checkable `reason` category
  (`cli_not_found`, `spawn_failed`, `timeout`, `nonzero_exit`,
  `malformed_json`, `auth_unavailable`, `cli_reported_error`) so callers
  branch on real classification, never string-matching. `claude_cli_executor()`
  matches `agent_runner.SessionExecutor`'s exact signature; an image
  content block is decoded back to real bytes, written to a real temp
  file (auto-cleaned in a `finally`), and the CLI is pointed at it via
  `--add-dir` + a Read-tool instruction in the prompt text — the judge
  role never receives an image (unchanged from before), so this path is
  simply skipped for judge calls. `check_claude_cli_auth()` is
  `mediactl auth-check`'s real logic — a genuine minimal `-p` smoke test,
  never a config-file check. **One explicitly documented open question,
  honestly flagged rather than assumed:** whether an image handed to the
  CLI via `--add-dir` + Read actually reaches the model's real vision
  input, since `agent_runner.py`'s own Commit 7 docstring warned an older
  CLI behavior read local images as text — every real call in this
  environment fails at the auth step before reaching that question, so it
  remains unverified until real credentials exist.
- `nookguard/agent_runner.py` — `run_observer_session`/`run_judge_session`/
  `run_page_review_session`'s `executor=` default changed from
  `_default_executor` (direct Messages API) to
  `cli_reviewer.claude_cli_executor`. `_default_executor` remains fully
  defined, real, and importable — pass `executor=_default_executor`
  explicitly to opt back into the direct-API transport; no function
  signature changed, only the default value. Full suite re-run
  immediately after this single change confirmed 288/288 still passing
  (every existing observe/judge/preview-review test monkeypatches the
  whole function at `cli.py`'s imported name, so the raw default executor
  is never actually exercised by those tests).
- `nookguard/state_machine.py` — added `AssetState.REVIEW_PENDING`.
  Removed `REVIEW_ERROR` from `_REGENERATE_SOURCES` (a deliberate,
  documented semantic split from every other state in that set: every
  other member means "content was judged and correctly found bad" —
  `REVIEW_ERROR` means "the review process itself never completed," a
  categorically different, process-level failure). Added
  `REVIEW_ERROR: {REVIEW_PENDING}` and `REVIEW_PENDING: {OBSERVING}` to
  `TRANSITIONS` — `REVIEW_PENDING` has exactly one legal forward edge, so
  recovery always re-enters at `OBSERVING` and must earn a real, fresh
  verdict; there is no edge to any PASS/approval state. The state graph
  only proves this edge is legal, not that it's earned — `cmd_review_retry`
  (cli.py) is the sole intended caller, and it enforces the actual
  business guards (unchanged candidate hash, bounded retry count) the
  table itself cannot express.
- `nookguard/cli.py` — `cmd_generate` now calls `check_claude_cli_auth()`
  and refuses to proceed for any non-stub adapter when it fails
  (`{"ok": false, "reason": "auth_check_failed", ...}`) — generating a
  real candidate that could never be reviewed afterward is pure wasted
  cost/risk with no possible resolution. A new `--skip-auth-check` flag
  exists solely so tests can exercise a real adapter call site without a
  real CLI/credential present; it is never valid in real production use.
  Added `MAX_REVIEW_RETRIES = 3`, `_review_error_event_count()` and
  `_last_review_error_candidate()` (both pure ledger reads — no new
  persistent counter, since nothing in the ledger is ever deleted, only
  counted), `cmd_review_retry` (the `REVIEW_ERROR → REVIEW_PENDING →
  OBSERVING` recovery command — rejects with `changed_candidate` if the
  most recent review-failure ledger event names a different candidate
  hash than the one being retried, rejects with `retry_exhausted` at or
  beyond `MAX_REVIEW_RETRIES`, otherwise walks both transitions and logs
  `review.retry_approved`/`review.retry_resumed`), and `cmd_auth_check`
  (a thin wrapper around `cli_reviewer.check_claude_cli_auth`). Added the
  `review-retry` and `auth-check` subparsers.
- `nookguard/tests/test_cli_reviewer.py` (new, 13 tests) — successful CLI
  review, missing authentication, malformed JSON, timeout, nonzero exit
  (with and without an auth marker), spawn failure, CLI-not-found, and
  `check_claude_cli_auth`'s three outcomes (success, auth failure with
  instructions, CLI not found). Every test injects a fake
  `subprocess_runner`; no real CLI or credential is ever touched.
- `nookguard/tests/test_review_retry.py` (new, 7 tests) — unchanged-
  candidate retry succeeds and genuinely resumes real (mocked) observe/
  judge through to `semantic_pass` (not just a state-flag flip); rejected
  when the asset isn't in `review_error`; rejected as `changed_candidate`
  when the ledger's most recent failure names a different candidate;
  rejected as `retry_exhausted` at the bound; `auth-check`'s CLI wrapper;
  `generate`'s real auth-check refusal for a non-stub adapter; and
  `--skip-auth-check` genuinely bypassing the gate (with the huggingface
  adapter's own `generate` also mocked, so this test never attempts a
  real network call).
- `nookguard/tests/test_state_machine.py` — updated
  `test_observing_can_reach_review_error_not_just_judging` (asserts
  `not is_regenerate_source(REVIEW_ERROR)` now, with a comment explaining
  why, instead of the old `is_regenerate_source` assertion this change
  genuinely invalidated) and added
  `test_review_error_recovers_only_to_review_pending_then_observing`
  (proves the graph itself never allows a shortcut from `REVIEW_ERROR`/
  `REVIEW_PENDING` straight to `SEMANTIC_PASS`/`INTEGRATED`/`RELEASED`).
- `nookguard/tests/test_cli.py` — `test_generate_dispatches_to_huggingface_adapter`
  updated to pass `--skip-auth-check` (this test is about adapter
  dispatch, not the new auth gate, which has its own dedicated tests
  above) — this was the one pre-existing test the new gate broke, caught
  by running the full suite, not assumed.

**Tests run:** `python -m pytest nookguard/tests/ -q` (Desktop Commander,
real Windows Python, via a `.ps1` script file rather than an inline
`-Command` string — this session's established fix for PowerShell
quoting failures on multi-statement/quoted inline commands).
**Result:** 308/308 passed, 0 failures (up from 288 — +13
`test_cli_reviewer.py`, +7 `test_review_retry.py`, +1
`test_state_machine.py` new test = +21, net +20 after accounting for the
one pre-existing test that needed `--skip-auth-check` added rather than
counted as new).

**Unresolved risks, carried forward honestly, not closed by this commit:**
whether the CLI's Read-tool image path actually reaches real vision input
(flagged above, unverifiable in this environment); whether
`claude setup-token`/`CLAUDE_CODE_OAUTH_TOKEN` actually authenticates a
real headless/scheduled-task Windows identity the same way an interactive
session would — neither can be confirmed until Maurice runs
`claude setup-token` for real and a live `mediactl auth-check` passes.
Commits 20-22 (live-review regression corpus, public-media containment,
final live canary) all depend on that real authentication existing;
none of it is simulated or assumed here.

**Commit:** `1cbe0c5`, pushed to `origin/main` (`0c151b9..1cbe0c5`).

**Next:** Commit 20 — `mediactl regression --mode live-review` calling the
real (now CLI-based) observer/judge against the real historical regression
corpus image files, plus the OCR validator gap.

---

## Commit 20: Real perception regression + missing OCR validator — DONE

**Completed:** 2026-07-23

**Why this commit:** Maurice's explicit next-step instruction after
Commit 19 — add a real live-review regression mode (never synthetic
observations/judgments), preserve the existing deterministic mode
separately, add a real object-count-contradiction fixture, and close the
`ocr_logo_scan` gap `validators/image.py` had documented as genuinely
unimplemented since Commit 6 (neither `pytesseract` nor a system
`tesseract` binary existed in this environment) — with a hard requirement
that an asset requiring OCR must be BLOCKED, not silently passed, if the
validator can't actually run.

**Real OCR installation, attempted and documented honestly, not just
assumed:**
1. `pip install pytesseract` — succeeded cleanly.
2. `winget install --id UB-Mannheim.TesseractOCR -e --accept-source-
   agreements --accept-package-agreements --silent` — the system-Tesseract
   binary this environment never had. Failed for a real, structural
   reason: `An unexpected error occurred while executing the command:
   0x800704c7 : The operation was canceled by the user` — winget's
   installer requires interactive UAC elevation, which this automation
   channel cannot supply (no dialog to click "Yes" on). Retried with
   `--scope user` to sidestep elevation: `No applicable installer found`
   — this specific package has no non-elevated install path at all.
3. `pip install rapidocr-onnxruntime` — a pure-Python, ONNX-based OCR
   engine with no external system-binary dependency — installed cleanly,
   zero elevation needed.
4. Real smoke test against a real site image before wiring anything:
   `RapidOCR()(...office-hero.jpg)` returned real, correct detections in
   2.29s wall time, including `'MAKE'` (0.79), `'BEAUTIFUL'` (0.84),
   `'THINGS'` (0.85) — genuinely, unpromptedly reading the real "Make
   Beautiful Things" wall-sign fixture documented in the project's own
   room bible (`brand-assets/winnie/Winnies-Home-Room-Bible.md`). This is
   real, working OCR, not a stub — confirmed before any validator code was
   written, not assumed after.

**Changed files:**
- `nookguard/validators/ocr.py` (new) — the real OCR backend.
  `_get_engine()` lazily constructs and process-wide-caches a real
  `RapidOCR` instance (model load is real, measurable work — ~2.3s
  including the smoke test above — so this happens at most once per
  process). `available()`/`scan()` never raise; a failed import/load or a
  real per-image OCR failure is reported as `performed: False` with the
  real exception message, matching this codebase's "classify, don't
  crash" convention (`adapters/huggingface.py`'s `_resolve_hf_token`,
  `cli_reviewer.py`'s `resolve_claude_cli_path`). `reset_engine_cache_
  for_tests()` is a real, documented test-only escape hatch so the
  process-wide cache can't leak between test cases.
- `nookguard/validators/image.py` — `_check_ocr_logo_scan()`'s old
  always-`performed: False` stub is gone; `ocr_logo_scan` in
  `NOT_YET_IMPLEMENTED` is gone (genuinely implemented now — only
  `edge_clipping_risk` remains, for its own, still-valid, already-
  documented reason). `validate()` gained a `require_ocr: bool = False`
  parameter (the technical validator still never sees the contract
  itself, same separation-of-concerns rule this file's own docstring
  states — the caller computes and passes a plain bool). When
  `require_ocr` is True and the real engine could not run,
  `technical_pass` is forced False and the result carries a new top-level
  `"blocking_reason": "VALIDATOR_UNAVAILABLE"` — a required check that
  couldn't run must never be silently treated as passed.
- `nookguard/schemas.py` — `AssetContract` gained `requires_ocr_scan:
  bool = False` (additive, defaults False, every existing contract/test
  unaffected).
- `nookguard/cli.py` — `cmd_validate` now passes `require_ocr=contract.
  requires_ocr_scan` into `image_validator.validate()` and surfaces
  `blocking_reason` at the top level of both the ledger payload and the
  returned dict when it fires, not just buried inside the technical
  report. Added `cmd_regression` (`mediactl regression --mode
  {deterministic,live-review}`, default `deterministic`) and its
  subparser — deliberately no argparse `choices=` constraint (an invalid
  `--mode` returns this module's own `{"ok": false, "error": ...}`
  contract, not a raw `SystemExit`, matching cli.py's own stated
  convention). `deterministic` mode delegates to the exact same
  `run_regression_corpus()` the pre-existing `regression-run` command
  (Commit 13) already uses — no duplicated logic, `regression-run` itself
  untouched and still available. `live-review` mode calls the new
  `run_live_review_regression_corpus()`. Each mode reports its own real
  results under its own `mode` field; neither is ever blended into or
  mislabeled as the other.
- `nookguard/regression_live.py` (new) — the live-review corpus. Every
  fixture calls the REAL `agent_runner.run_observer_session`/
  `run_judge_session` (Commit 19's `claude_cli_executor` default
  transport) against a REAL image file on disk, via a REAL
  `review_pack.build_review_pack()` — no synthetic observation or
  judgment is ever injected; a real `ReviewSessionError` is reported as a
  real `REVIEW_ERROR` with `review_process_completed: False`, never
  papered over. Four fixtures, with image provenance documented plainly
  per-fixture (`image_source_note`) rather than asserted as literal
  historical originals: (1) `known_clean_real_site_photo` — a REAL,
  copy of the actual currently-live `office-hero.jpg`, a genuine
  known-clean control; (2) `object_count_contradiction_real_photo` — the
  new fixture requirement 4 asked for: a purpose-built photo with exactly
  ONE clearly labeled, verifiable object, paired with a contract requiring
  "exactly 5" — a real, unambiguous contradiction; (3)
  `banana_foil_fusion_reproduction` and (4)
  `unexpected_furniture_reproduction` — purpose-built PIL reproductions of
  the two historical incident categories, explicitly documented (in this
  module's own docstring and BUILD-LOG both) as reproductions, not the
  literal original defective bytes, which no longer exist anywhere in
  this repository per the project's own regenerate-only architecture
  (`state_machine.py`'s `_REGENERATE_SOURCES`).
- `nookguard/gen_regression_images.py` (new) — the real, reproducible
  generator for all four regression images (`nookguard/regression_images/`,
  committed as real binary files, not generated at test time). Run
  directly (`python -m nookguard.gen_regression_images`) if a regression
  image is ever lost or needs regenerating.
- `pyproject.toml` — added `rapidocr-onnxruntime>=1.3` (primary OCR
  backend) and `pytesseract>=0.3` (kept as an optional alternate backend
  for a future environment where Tesseract-OCR's system binary is
  actually installed) to real project dependencies.
- `nookguard/tests/test_validators_ocr.py` (new, 4 tests) — `available()`
  true against the real installed engine (no mock), `scan()` against a
  real rendered image with real known text correctly read back, a missing
  file reported as `performed: False` not a crash, and a simulated
  load-failure path via a real `builtins.__import__` patch.
- `nookguard/tests/test_validators_image.py` — replaced the one test whose
  premise ("OCR deps missing") this commit made genuinely false
  (`test_validate_reports_ocr_not_performed_when_deps_missing`) with four
  real tests: OCR now genuinely performs a scan by default; an
  unavailable engine does NOT block when `require_ocr` was never
  requested; an unavailable engine DOES block with
  `VALIDATOR_UNAVAILABLE` when `require_ocr=True` (via a real monkeypatch
  of `ocr_validator.scan`, since the real engine happens to work on this
  machine and the failure path needs to be provable regardless); and the
  inverse (`require_ocr=True` with an available engine does not block).
- `nookguard/tests/test_regression_live.py` (new, 5 tests) — every
  `LIVE_FIXTURES` image genuinely exists on disk and is non-empty; a real,
  fully UNMOCKED run against this actual environment (matching
  `test_cli.py`'s own `test_canary_run_reports_which_step_failed`
  pattern) confirms every fixture honestly reaches
  `review_process_completed: False` / `REVIEW_ERROR` at the real, current
  auth wall — not a wiring bug indistinguishable from it; a monkeypatched
  wiring-proof test confirms the corpus genuinely calls the real
  functions (2 observer calls + 1 judge call per fixture) and aggregates
  a real verdict; a single fixture's real observer failure doesn't crash
  the whole run; a missing-images-directory case reports `IMAGE_MISSING`
  honestly rather than skipping silently.
- `nookguard/tests/test_cli.py` (+3 tests) — `regression --mode
  deterministic` produces byte-identical per-fixture results to the
  pre-existing `regression-run` command; `regression --mode live-review`
  reaches the real corpus unmocked and honestly reports `ok: false` /
  `review_process_completed_count: 0`; an unknown `--mode` is rejected via
  the standard `{"ok": false}` contract, not a `SystemExit`.

**Tests run:** `python -m pytest nookguard/tests/ -q` (Desktop Commander,
real Windows Python, via a `.ps1` script file — this session's established
fix for PowerShell quoting failures on inline `-Command` strings).
**Result:** 323/323 passed, 0 failures (up from 308 — +15: 4
`test_validators_ocr.py`, net +3 `test_validators_image.py` (4 added, 1
replaced), 5 `test_regression_live.py`, 3 `test_cli.py`).

**Honest, explicitly-scoped limitations, not closed by this commit:**
(1) `mediactl regression --mode live-review` cannot currently produce a
real PASS/FAIL verdict on this machine — every fixture legitimately stops
at `REVIEW_ERROR` (auth_unavailable), the identical standing gap Commit
19 documented; this will not change until Maurice runs `claude
setup-token` and a real `mediactl auth-check` passes. (2) Two of the four
live-review fixtures use purpose-built reproductions, not the literal
original historical defective images (which no longer exist anywhere in
this repository, by design — see `_REGENERATE_SOURCES`); this is
documented plainly in both `regression_live.py`'s own docstring and this
entry, not hidden. (3) The system Tesseract-OCR binary remains
uninstalled on this machine — `pytesseract` is a real, installed,
available alternate backend the moment Maurice runs the one-time elevated
`winget install --id UB-Mannheim.TesseractOCR -e` himself, but
`validators/ocr.py` does not depend on it; RapidOCR is the real, working,
zero-elevation backend actually in use.

**Commit:** `5c7d234`, pushed to `origin/main` (`8b3bd6d..5c7d234`).

**Next:** Commit 21 — public-media containment (block any write to a
public media path that isn't an approved, hash-matched NookGuard release
manifest entry) and a controlled Cloudflare release path once Maurice
supplies restricted credentials.

---

## Commit 21: Public-media containment + controlled Cloudflare release — DONE

**Completed:** 2026-07-22

**Why this commit:** Maurice's explicit next-step instruction after
Commit 20 — no new or modified public media may exist unless its exact
hash is approved and present in a NookGuard release manifest; enforce
this locally, in repository validation, and in the production deployment
command; ensure no old generation script can write directly to a public
media path; keep both legacy scheduled tasks disabled; audit every code
path capable of writing to public media or invoking deployment; and
configure preview/production deployment through NookGuard + Wrangler once
restricted Cloudflare credentials are available.

**Critical path-convention bug caught and fixed before any code shipped,
not after:** while wiring the three new CLI commands into `cli.py`, a
real `Glob`/`canon.py` check confirmed `cli.py`'s existing `--project-root`
default (`DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]`)
resolves to the directory ABOVE `site/` — where `brand-assets/` genuinely
lives (`canon.py`'s `CANON_FILES` are all `brand-assets/...`-relative,
confirmed on disk at `Amazon Drop Ship/brand-assets/`, a sibling of
`site/`, not inside it). `public/winnie`, `dist/`, etc. are a DIFFERENT
real directory — inside `site/` itself. Had `cmd_media_audit` inherited
`--project-root`, the containment audit would have silently resolved to a
nonexistent path, scanned zero files, and reported a false `ok: true` — a
dangerously empty-but-passing audit, worse than no audit. Fixed by giving
`public_media_guard.py` and `write_path_audit.py` their own `site_root`
parameter (never `project_root`) defaulting to `Path(__file__).resolve()
.parent.parent` (correctly `site/`, since both modules live in
`nookguard/`), and wiring a separate `--site-root` CLI flag (not
`--project-root`) into `media-audit`, `write-path-audit`, and `deploy`.
Documented permanently in `public_media_guard.py`'s own module comment so
it can't silently regress.

**Two further real bugs caught by this commit's own tests, not shipped
silently:**
1. `cmd_media_audit`'s first version only folded `--store-root` into the
   approved-hash search when `--store-root-extra` was ALSO given — a
   caller passing just `--store-root` (the normal, single-store case) had
   it silently dropped, contradicting the `--store-root-extra` argument's
   own help text ("The primary --store-root is always included"). Caught
   by `test_media_audit_cli_approves_file_released_through_real_store_
   root`. Fixed: `--store-root` is now unconditionally the first entry in
   `store_roots`; `cmd_deploy` was changed to match the same convention
   (previously it ignored `--store-root` entirely, always defaulting to
   `<site_root>/nookguard_store`).
2. `deploy.py`'s deployment-URL regex required exactly two dot-separated
   labels before `.pages.dev` (matching a preview URL like
   `<hash>.<project>.pages.dev`) but would have failed to capture a real
   Cloudflare Pages PRODUCTION url, which has only one label
   (`<project>.pages.dev`). Caught by
   `test_run_wrangler_deploy_missing_id_returns_none_not_guessed`. Fixed
   to accept one-or-more labels.

**Real-environment findings, not code bugs — required for requirements
3-4:**
- Requirement 3 ("no old generation script can write directly to public
  media"): a real repository `Glob` for `scripts/gen_*.py` found NO
  matches — the historical `gen_garage_images.py`/`gen_product_images.py`
  etc. scripts the parent CLAUDE.md documents as live daily-pipeline
  tooling are not present in this checked-out `site/` tree. `write_path_
  audit.py`'s own docstring documents this scope limitation explicitly
  (it can only see this repository, not `C:\Users\weare\Documents\Claude\
  Scheduled\*` or other projects). Containment is therefore enforced going
  forward by the mechanism (H008 hook + `mediactl media-audit` + the
  deploy gate) regardless of what future script might attempt a write, not
  by modifying scripts that don't currently exist here.
- Requirement 4 ("keep both legacy scheduled tasks disabled"): confirmed
  via a real `mcp__scheduled-tasks__list_scheduled_tasks` call — all 6
  Nest & Nook-relevant scheduled tasks (`nest-and-nook-daily-blog-post`,
  `nest-and-nook-daily-image-and-page-build`, plus the 4 VoidCast tasks)
  report `enabled: false`. No code change required; verification only.

**Changed files:**
- `nookguard/public_media_guard.py` (new) — the containment rule
  (requirement 1): a public media file is allowed if EITHER its exact
  (relative_path, sha256) matches the committed baseline snapshot
  (pre-existing, untouched legacy content) OR its real sha256 is present
  in a real `ReleaseManifestEntry.candidate_sha256` from any given
  NookGuard store's `releases/` directory. Anything else — new or
  modified, not approved — is UNAPPROVED and blocks. Exports
  `is_published_media_path()` (used by both this module and `hooks.py`,
  removing the prior duplicated `_MEDIA_EXTENSIONS`/`_PUBLISHED_MEDIA_
  DIRS` constants that used to live only in `hooks.py`),
  `snapshot_public_media()`, `load_baseline()`/`write_baseline()`,
  `collect_approved_hashes()`, `audit_public_media()`.
- `nookguard/public_media_baseline.json` (new) — real, generated snapshot:
  344 real published-media files under `site/public/{winnie,cursors,pins,
  tools,recipes,products}`, each with its real sha256, as of this commit.
- `nookguard/gen_public_media_baseline.py` (new) — the one-time generator
  for the baseline above (`python -m nookguard.gen_public_media_
  baseline`); documented as a deliberate re-baselining tool, not a routine
  step (re-running it after an unapproved write would silently grandfather
  it in).
- `nookguard/write_path_audit.py` (new) — requirement 5's static,
  enumerative audit. Marker-PAIR matching (a write-call marker AND a
  media-path marker must appear on the SAME line — same discipline as
  `hooks.py`'s H002), scanning `.py/.mjs/.js/.ts/.ps1/.sh` files,
  excluding `node_modules/dist/.git/nookguard_store/__pycache__/.astro/
  tests`. The `tests` exclusion was added after this module's own
  CLI-level test caught 5 real matches against the live repo, all of them
  its own test fixtures deliberately constructing synthetic write-call-
  shaped text to prove the detector works — a documented, expected false-
  positive source (cli.py's own `cmd_write_path_audit` docstring already
  flagged "a legitimate test fixture" as a real possibility), not a
  containment gap.
- `nookguard/deploy.py` (new) — requirements 6-8. `check_cloudflare_
  credentials()`: real, multi-scope (Process/User/Machine) Windows
  env-var check for `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID`,
  same "classify, don't crash" pattern as `cli_reviewer.check_claude_cli_
  auth()`. Confirmed via a real, unmocked call on this machine: both
  variables are genuinely absent at every scope. `run_wrangler_deploy()`:
  real, injectable subprocess wrapper around `wrangler pages deploy`,
  parsing the real deployment URL/ID out of wrangler's own stdout — never
  fabricated; a not-yet-observed ID format returns `None`, not a guess.
  Module docstring explicitly documents what this module does NOT and
  cannot do from this environment: disable Cloudflare Pages' automatic
  "deploy on push to main" GitHub integration (requirement 7) — a
  dashboard-only setting reachable only via Maurice's own Cloudflare
  account, with no API token available here to do it programmatically
  either.
- `nookguard/hooks.py` — `check_write_existing_media_overwrite` renamed to
  `check_write_to_published_media` and STRENGTHENED: H008 previously only
  denied overwriting an EXISTING published-media file; it now denies ANY
  Write to a published media path, new file or existing overwrite alike —
  closing the gap where a brand-new unauthorized image could be written
  straight to `public/winnie/` by any live Claude session.
- `nookguard/cli.py` — three new commands: `media-audit` (repository-
  validation gate, delegates to `audit_public_media()`), `write-path-
  audit` (delegates to `run_write_path_audit()`, purely enumerative, `ok`
  is always true), `deploy` (the controlled production-deployment
  command: refuses to proceed past an unapproved-media-audit result,
  refuses to proceed past missing Cloudflare credentials, only then
  attempts a real `wrangler pages deploy` and returns its real
  deployment_id/deployment_url). All three take `--site-root` (default
  `DEFAULT_SITE_ROOT`), never `--project-root` — see the path-convention
  bug above.
- `nookguard/tests/test_hooks.py` — updated for the H008 rename;
  `test_h008_allows_write_of_new_media_file` (asserted the old, weaker
  behavior) replaced with `test_h008_denies_write_of_new_media_file`
  (asserts the new, strengthened behavior).
- `nookguard/tests/test_public_media_guard.py` (new, 15 tests) — real
  filesystem fixtures throughout (real files, real hashes, real
  `ReleaseManifestEntry` records on disk) — no synthetic hash comparisons.
  Covers path matching, snapshot/baseline round-trip, `collect_approved_
  hashes()` across single/multiple/missing/corrupt store roots, and
  `audit_public_media()`'s five real outcomes (baseline-unchanged passes,
  brand-new file fails, baseline file modified-in-place fails, a file
  approved via a real release manifest entry passes, files removed since
  baseline are reported).
- `nookguard/tests/test_write_path_audit.py` (new, 8 tests) — marker-pair
  matching (both markers same line = found; either alone = not found),
  deploy-marker detection, excluded-directory skipping, extension
  filtering, and a real regression-guard test against the actual live
  `site/` tree (0 media-write findings, matching the confirmed manual
  result).
- `nookguard/tests/test_deploy.py` (new, 10 tests) — dependency-injection
  pattern (fake `env`/`subprocess_runner`) for available/missing/
  persistent-scope-fallback/probe-exception credential cases, PLUS one
  real, unmocked `check_cloudflare_credentials()` call confirming this
  machine's genuine absence; `run_wrangler_deploy()` success (real-shaped
  stdout parsing), missing-ID-not-guessed, wrangler-not-found, timeout,
  nonzero-exit, and preview-vs-production branch selection.
- `nookguard/tests/test_cli.py` (+9 tests) — CLI-level coverage for
  `media-audit` (clean-against-baseline, flags-new-unapproved-file,
  approves-via-real-release, and a real run against the actual live
  `site/` tree with its real committed baseline — confirmed clean, 344
  files, 0 unapproved), `write-path-audit` (real site tree clean, plus a
  synthetic-finding case), and `deploy` (refuses on unapproved media; a
  real, unmocked call against the actual site tree honestly stops at
  `cloudflare_credentials_unavailable` — matching the same real-
  environment-failure discipline as `test_canary_run_reports_which_step_
  failed` and `test_regression_live_review_mode_runs_real_corpus_
  unmocked`).

**Tests run:** `python -m pytest nookguard/tests/ -q` (Desktop Commander,
real Windows Python, via a `.ps1` script file). First real run surfaced 4
genuine failures (the store-root bug, the URL-regex bug, and two instances
of the `tests/`-directory self-match, described above) — all fixed, not
worked around, then a second real run surfaced one further self-match (this
module's OWN docstring, in the paragraph explaining the `tests/`
exclusion, literally contained a `.save(`+`public/winnie` example on one
line and matched its own detector) — fixed by splitting the example across
two lines. **Result, final run:** 365/365 passed, 0 failures (up from 323
— +42: 15 `test_public_media_guard.py`, 8 `test_write_path_audit.py`, 10
`test_deploy.py`, 4 `test_hooks.py` net change, 9 `test_cli.py`, minus the
1 replaced `test_hooks.py` case counted once).

**Honest, explicitly-scoped limitations, not closed by this commit:**
(1) Requirement 7 (disable Cloudflare Pages' automatic deploy-on-push)
cannot be performed or verified from this environment — dashboard-only,
Maurice's own Cloudflare account required, no API token available here
either; `deploy.py`'s module docstring documents this rather than
claiming it done. (2) Requirements 6/8 (configure real deployment, capture
a real deployment ID) are built as real, working, tested mechanisms but
have never been exercised end-to-end — Cloudflare credentials are
confirmed genuinely absent on this machine at every scope; `mediactl
deploy` correctly refuses rather than fabricating a deployment. (3)
Requirement 3's "no old generation script can write directly" is
satisfied by there being no such script in this checked-out repository
right now, not by having modified one — see the real-environment finding
above; if a legacy script is ever reintroduced or copied in from another
location, H008 + `media-audit` + the deploy gate are the actual backstop.

**Commit:** `bce19d8`, pushed to `origin/main` (`e5c947f..bce19d8`).

**Next:** Commit 22 — final live canary: reuse or recreate the canary
candidate, run the real Claude observer/judge, run the full live-review
regression corpus, produce real desktop/mobile staging screenshots,
release with a content-hashed filename, deploy through the now-controlled
Cloudflare release path (gated on real credentials, per the limitation
above), fetch and verify real production bytes, and only then evaluate
whether NookGuard meets every one of the nine real conditions required to
be declared OPERATIONAL.

---

## Commit 22: Final live canary — RUN, RESULT: NOT OPERATIONAL (real, honest)

**Completed:** 2026-07-22

**Why this commit:** the final step of the Commit 19-22 sequence — attempt
the complete real pipeline end to end against the actual live canary
asset, using everything built in Commits 19-21 (Claude Code CLI reviewer
transport + REVIEW_ERROR recovery, real live-review regression, public-
media containment, controlled Cloudflare deploy), and only declare
NookGuard OPERATIONAL if every one of the nine real conditions in the
original instruction is genuinely met. This entry reports the real result
of actually running it — not a projection of what would happen once
credentials exist.

**1. Reuse vs. recreate the canary candidate:** REUSED, per instruction —
the state-machine recovery permitted it. A real, pre-existing canary asset
(`nookguard-canary-2026-07-22-pegboard-wall-measure`, candidate
`9be476db40b23998c12efea2990ccdc601ba02ba8a15f1f3c9a8e023ffd10fd7`) was
found sitting in `review_error` in the real local store
(`nookguard_store/asset_states/`), left over from an earlier session. Ran
`mediactl review-retry --candidate-sha256 9be476db...` for real: it
succeeded (`prior_failure_count: 1`, `retries_remaining: 1`), transitioning
the asset `REVIEW_ERROR -> REVIEW_PENDING -> OBSERVING` for this exact,
unchanged candidate — proving Commit 19's recovery mechanism works against
a real, previously-broken asset, not just its own test fixtures. No new
candidate was generated; none was needed.

**2. Run the real Claude observer and judge:** ATTEMPTED FOR REAL, OBSERVER
DID NOT COMPLETE. Ran `mediactl observe` against the recovered candidate.
Real, unmocked result: `"ok": false, "error": "Review session error
(blind_a): session failed or returned invalid JSON: Claude Code CLI
transport failed (auth_unavailable): Not logged in · Please run /login"`.
This is the real Claude Code CLI itself (resolved at `C:\Users\weare\
AppData\Roaming\Claude\claude-code\2.1.217\claude.exe`, confirmed via a
real `mediactl auth-check` run in the same session — `authenticated:
false, reason: auth_unavailable`) reporting it is not logged in under this
Windows identity. Exactly the same standing gap Commits 19-20 already
documented, now hit for real against the real canary asset, not just a
regression fixture. The asset correctly transitioned back to
`REVIEW_ERROR` (confirmed by re-reading its real state file after the
attempt) — one retry consumed, one remaining. Judge was never reached
(observe must complete first). No fabricated PASS was produced anywhere in
this chain.

**3. Run the complete live-review regression corpus:** RUN FOR REAL, ALL 4
FIXTURES HONESTLY REPORT `REVIEW_ERROR`. `mediactl regression --mode
live-review` against the real corpus: `review_process_completed_count: 0`,
`fixture_count: 4`, every fixture's `detail` citing the identical real
`auth_unavailable`/"Not logged in" error as step 2 — consistent, not a
fluke. The separate deterministic regression corpus (unaffected by the
auth gap, exercised via the real `mediactl run-report` call in step 8
below) remains 10/10 passing, matching every prior run since Commit 13.

**4-7. Staging screenshots, release, deploy, production-verify: NOT
ATTEMPTED — correctly blocked upstream, not skipped.** The real pipeline
requires `judge` to reach `SEMANTIC_PASS` before `integrate` (needed for a
real page URL to screenshot), `RELEASED` (needed for a content-hashed
public file), or any downstream step can run. Since the real observer
session never completed (step 2), the candidate never left `REVIEW_ERROR`
and none of these steps had a legal state to run from — `state_machine.py`
would reject the attempt outright. Running them anyway against an
unrelated asset would have produced misleading, non-canary evidence, so
none were attempted. Separately, and independently of the observer gap,
`mediactl deploy` was run for real to confirm Commit 21's deploy gate
itself still behaves correctly: real `media-audit` first (`ok: true`, 344
baseline-unchanged, 0 unapproved — the real live site tree is clean), then
real `deploy` — correctly refused with `"reason":
"cloudflare_credentials_unavailable"`, `"missing": ["CLOUDFLARE_API_TOKEN",
"CLOUDFLARE_ACCOUNT_ID"]`, confirming Commit 21's finding (both variables
genuinely absent at every Windows scope) still holds. `write-path-audit`
was also re-run for real against the live tree: `media_write_count: 0`
(confirms the `tests/` exclusion fix from Commit 21 holds against the real
tree, not just the test suite); `deploy_invocation_count: 49`, all of them
real, expected comment/import/string matches in `deploy.py`/`cli.py`/
`write_path_audit.py`'s own source and the separate `nookguard-worker`
Cloudflare Worker code — enumerative, not a containment failure.

**8. Generate final run-report, owner summary, and evidence index: DONE,
REAL.** `mediactl run-report --run-id nn-commit22-canary` produced real
artifacts at `nookguard_store/reports/nn-commit22-canary/{run-report.json,
run-report.md, owner-summary.txt, evidence-index.json}` (local operational
store, not committed to git — consistent with how every prior canary/
regression run's artifacts have been handled in this project). Real
content, read back after generation to confirm (not assumed):
`"terminal_status": "INCOMPLETE"`, `"ok": false`,
`"release_manifest_sha256": null`, `"production_deployment_id": null`,
`"assets": {"process_error": 1, "approved": 0, "production_verified": 0,
...}`, `"regression_suite": {"passed": 10, "failed": 0, "all_passed":
true}`, `"blocking": ["1 asset(s) hit a review-process error (state:
review_error) -- the review process itself did not complete, so no real
decision was ever reached for these..."]`. The owner-summary.txt reads
plainly: `Run nn-commit22-canary: INCOMPLETE ... review-process errors 1
... Regression suite: 10 passed, 0 failed`.

**9. Operational determination — NOT MET, reported honestly, not
inflated.** Checked against every one of the nine real conditions from the
original instruction:
- Real observer and judge sessions completed — **NO** (observer failed at
  the real auth wall; judge never ran).
- Every critical live regression produced its expected verdict — **NO**
  (all 4 fixtures stopped at `REVIEW_ERROR`, none reached their expected
  `semantic_pass`/`semantic_fail` verdict).
- No public-media bypass remains — **YES** (real `media-audit`: clean;
  real `write-path-audit`: 0 media-write findings; H008 strengthened in
  Commit 21).
- Staging passed — **NOT REACHED** (no candidate ever reached
  `INTEGRATED`/`PREVIEWED` this run).
- Approved and production hashes match — **NOT REACHED** (no release this
  run, so no hash to compare).
- The deployment ID and release-manifest hash are recorded — **NO**
  (`production_deployment_id: null`, `release_manifest_sha256: null`,
  confirmed in the real run-report above; `mediactl deploy` correctly
  refused rather than fabricating either value).

**NookGuard's operational status remains NOT OPERATIONAL.** This is the
correct, honest result given the real state of this environment, not a
regression or a new problem: two genuine, previously-documented external
gaps — (a) the Claude Code CLI is not authenticated under this Windows
identity (`claude setup-token` has not been run by Maurice), and (b) no
Cloudflare API credentials exist on this machine at any scope — block
every step downstream of the real observer call. Every piece of NookGuard
built across Commits 1-21 that COULD be exercised without those two
external actions was exercised for real in this commit and behaved
exactly as designed: recovery of a genuinely broken candidate, honest
non-fabricated failure reporting at the auth wall, a real and correctly
clean containment audit, a real and correctly-refusing deploy gate, and a
real, accurate run-report reflecting all of it. What remains is not more
code — it is two real-world actions only Maurice can take:
1. Run `claude setup-token` (or set `CLAUDE_CODE_OAUTH_TOKEN`) under the
   same Windows identity NookGuard runs as, then re-run `mediactl
   auth-check` to confirm.
2. Create a Cloudflare API token scoped to `Pages:Edit` for the
   `nestandnook-site` project (at
   `https://dash.cloudflare.com/profile/api-tokens`) and the account ID,
   set both as persistent Windows User-level environment variables, then
   re-run `mediactl deploy` to confirm.
Once both are true, re-running this exact canary (`mediactl review-retry`
+ `observe` + `judge` + `integrate` + `preview-capture` + `preview-review`
+ `release` + `deploy` + `production-verify` + `run-report`, in that
order, against either this same recovered candidate — one retry remains —
or a fresh one) is the real, next, and final step toward an honest
OPERATIONAL determination. No code change is anticipated to be required
for that run; this commit is evidence-only.

**Changed files:** none in `nookguard/` itself — this commit is a real
operational run, not a code change. `docs/nookguard/BUILD-LOG.md` (this
entry) is the only file changed.

**Tests run:** `python -m pytest nookguard/tests/ -q`, re-run after this
commit's real operational commands to confirm no regression. **Result:**
365/365 passed, 0 failures — unchanged from Commit 21 (expected, since no
production code changed).

**Commit:** `22caf76`, pushed to `origin/main` (`3b48b16..22caf76`).
