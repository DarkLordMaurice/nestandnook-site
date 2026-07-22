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
