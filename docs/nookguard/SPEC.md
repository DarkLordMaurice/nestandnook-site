# NookGuard — Condensed Build Spec

Extracted from `NookGuard-Plan.docx` (Appendices A-M) so implementation work doesn't
require re-reading the 53 page-images every session. This is a working reference, not
a replacement for the source doc — check the docx if something here is ambiguous.

## Commit order (Appendix A) — exact MVP build order

| # | Commit | Required outcome |
|---|--------|-------------------|
| 1 | Containment | Archive/hash current automation; production branch separation; paused/prepare-only task |
| 2 | Schemas and ledger | Pydantic models, JSON Schemas, event log, hash helpers, state-machine tests |
| 3 | mediactl | run/spec/prompt/generate/register/validate commands with JSON outputs |
| 4 | Canon and prompt compiler | Canonical registry, stale-source scan, module registry/source map |
| 5 | Generation adapter | HF adapter, quarantine, attempt metadata, immutable paths |
| 6 | Technical validators | Image validators, duplicates, review-pack generator |
| 7 | Claude agents | Agent definitions, Agent SDK/headless runner, session separation, structured schemas |
| 8 | Semantic aggregation | Blind observations, judge, no-override policy, owner queue |
| 9 | Off the Clock schema | Content migration, layout tests, legacy component ban |
| 10 | Preview QA | Playwright desktop/mobile, page contact sheets, page reviewer |
| 11 | CI isolation | GitHub workflows, artifacts, permissions, hooks |
| 12 | Release integrity | Manifest, production branch, versioned assets, production verifier |
| 13 | Regression and canary | Historical fixtures, expected labels, canary release |
| 14+ | Backend | Worker/D1/R2/Access/dashboard and operations (lowest priority, build last) |


## Asset contract schema (Appendix B) — required fields

- asset_id, project_id, page_id, slot_id, media_type, risk_tier
- page_type_contract_version
- source_excerpt + source_excerpt_sha256
- canonical_reference_bundle_sha256
- required subject/action/scene
- requirements[] with id, type, statement, critical, evidence_policy
- allowed_objects[], forbidden_objects[]
- count_constraints[], relationship_constraints[], continuity_constraints[]
- identity_constraints[], composition_constraints[]
- layout_constraints, legal/compliance constraints
- planner_session_id, plan_evaluator_session_id
- created_at, locked_at, spec_sha256

Schema validation must reject vague requirements ("looks good", "cozy", "matches
prompt") unless decomposed into observable criteria — a requirement must state what
evidence would make it true or false.

## Blind observation schema (Appendix C) — required fields

- review_id, candidate_sha256, review_pack_sha256
- reviewer_agent_hash, reviewer_session_id, context_bundle_sha256
- people[], visible_entities[] {label, count, boxes, confidence}
- materials[], relationships[] {subject, predicate, object, boxes, confidence}
- readable_text[], anomalies[] {category, severity, observation, boxes, confidence}
- uncertain_regions[]
- NO pass/fail or expected-object fields — the observer never sees the contract

Observer A: no expected-object list, inventories only, cannot approve.
Observer B: given a general failure taxonomy (unexpected furniture, material fusion,
duplicated items, malformed anatomy/hands, impossible physics, branded/readable text,
environment contradiction, repeated composition) but still no prompt/expected answer.
Actively tries to falsify quality.

## Contract judgment schema (Appendix D) — required fields

- candidate_sha256, spec_sha256
- judge_session_id, judge_agent_hash, context_bundle_sha256
- requirements[] { requirement_id, result: true|false|uncertain|not_applicable,
  evidence_observation_ids[], evidence_boxes[], confidence, concise_reason }
- forbidden_object_findings[]
- NO overall pass field, NO extra_justification / narrative-override field — code
  computes the final result from the policy table below, never the model.

## Code-aggregator policy table (section 29.5)

| Condition | Computed result |
|---|---|
| Any critical requirement = false | FAIL |
| Any critical requirement = uncertain | NEEDS_OWNER or FAIL by risk policy; never auto-pass |
| Either blind observer reports a forbidden object >= confidence threshold | FAIL, no free-text justification |
| Exact-count observers disagree | Third count adjudicator; if still disputed, NEEDS_OWNER |
| Material/relationship requirement lacks evidence box | FAIL_EVIDENCE |
| Identity/location reference required but missing | FAIL_REFERENCE |
| All critical true; noncritical score above threshold; no forbidden object | SEMANTIC_PASS |
| Model JSON invalid or session interrupted | REVIEW_ERROR; no pass inherited |

## Risk tiers (43.1) — who reviews before release

- Tier 0 decorative/simple: technical pass + two observers no critical anomaly + judge
  all critical true. Owner: random 10% calibration sample for first 50 assets only.
- Tier 1 routine supporting media: Tier 0 + narrative fit + page preview pass. Owner:
  reviews disagreements + first 20 assets per adapter.
- Tier 2 identity/continuity/relationships/counts: two observers + judge + reference
  review + page review; no critical uncertainty. Owner: mandatory during launch, may
  relax only after a measured sample and owner approval.
- Tier 3 brand-critical/high consequence: all automated checks. Owner: always final
  approval.

STANDING NOTE (2026-07-21, Maurice): pre-push owner gating (the Tier 2/3 mandatory-
approval-before-release behavior above) is explicitly DEFERRED per his instruction —
build the full pipeline including the gate logic, but do not treat "Maurice must
approve before this ships" as blocking right now. Revisit when he says it's time.

## Technical validators (section 28) — deterministic, code-owned

- Image: open/decode, dimensions, aspect ratio, color mode, min resolution, alpha
  policy, file-size anomaly, exact hash duplicate, perceptual near-duplicate,
  EXIF/privacy, blank/solid image, edge clipping risk, OCR/logo scan.
- Video: container/codec, duration, frame count, corrupted/black/frozen frames,
  loudness, audio stream, caption parse, first/last-frame extraction, scene-cut index.
- Audio: codec, duration, loudness, clipping, excessive silence, abrupt start/end,
  channel count, transcript availability.
- Document/PDF: opens, page count, fonts embedded, render every page, no blank pages,
  image resolution, metadata scrub, accessibility.
- Slides: slide count, render every slide, overflow/overlap, missing media, speaker
  note policy, font fallback.
- Page integration: all asset refs resolve, expected groups/counts, dimensions set,
  alt/caption present, no legacy path, no duplicate IDs, build succeeds.

Reminder from the doc: "technical pass is not semantic pass" — a valid JPEG with
correct dimensions can still contain a dresser in an animal enclosure. Keep these two
stages separate in the state machine, never conflate "file is well-formed" with
"content matches the contract."

## Generation attempt rules (section 27)

- One output, one record — even in a batch, each file is registered individually
  before any review.
- No filename reuse — candidate path includes the full hash; public filename is
  assigned only at release.
- No automatic "fix in place" — a repair creates a new prompt artifact or new attempt
  and preserves the rejected one.
- No generator review — the generation session may report tool errors but cannot
  submit quality evidence about its own output.
- Rate-limit safety — adapter errors retry with bounded backoff; exhausted retries
  mark GENERATION_BLOCKED, never "quota exceeded" unless the authenticated response
  actually proves it (see HF_TOKEN sourcing gotcha in the main project CLAUDE.md).

## Core hook rules (Appendix G) — enforce via Claude Code project hooks

| Rule | Trigger | Action |
|---|---|---|
| H001 | Write/Edit to protected path | Deny; return required `mediactl` command |
| H002 | Bash calls generation endpoint directly | Deny; only adapter command allowed |
| H003 | Bash uses blanket Git staging (`git add -A`/`.`) | Deny |
| H004 | Bash targets production branch | Deny unless CI release role token |
| H005 | Stop with claimed nonterminal job | Block stop, return next required command |
| H006 | Reviewer session attempts Write/Edit/Bash | Deny and invalidate review session |
| H007 | Prompt compile includes superseded source | Fail compile |
| H008 | Existing public media path bytes change | Deny overwrite |
| H009 | Page adds legacy raw media component | Fail content lint |
| H010 | Run report contains unsupported completion claim | Fail report validation |

H003 already matches the standing project rule in the main CLAUDE.md ("never
`git add -A`/`git add .`") — NookGuard makes it a mechanically enforced hook instead
of a prose instruction, closing the exact gap the main CLAUDE.md flags repeatedly
("an unenforced instruction gets skipped, an enforced one doesn't").

## Regression corpus seed (Appendix I) — from real incidents already in main CLAUDE.md

| Fixture | Expected | Category |
|---|---|---|
| Banana bread with foil visually fused to crust | FAIL | Material boundary/relationship |
| Cup collection with unrequested living-room furniture | FAIL | Unexpected objects/scene purity |
| Cup page using singular cup after owner removed concept | FAIL | Owner exclusion/page integration |
| Goat enclosure with clean fence instead of real reference rails/mesh | FAIL | Location continuity |
| Otter/aviary with older production bytes containing furniture | FAIL | Production integrity + unexpected objects |
| Halloween apple closeups after owner removed apple concept | FAIL | Narrative/owner instruction |
| Parade float dresser rationalized as altar | FAIL | Unexpected object; no narrative override |
| Off the Clock page with 1, 4, or 5 photo strips instead of approved structure | FAIL | Layout schema |
| Repository replacement differs from Cloudflare-served bytes | FAIL | Production hash mismatch |
| Known clean image, correct scene, no critical defects | PASS | Correct control |

## Definition of done (section 46) — do not claim a phase complete without these

- A scheduled Claude run can create a new asset from queue through production without
  free-form bypass.
- Generator and all reviewers have distinct recorded session IDs and role-scoped
  context bundles.
- A candidate byte change invalidates review/integration automatically.
- A shared style module cannot inject an unapproved object without compiler or
  semantic failure.
- A forbidden-object finding from either blind observer cannot be overridden by prose.
- The banana-foil and goat-fence regression fixtures both correctly FAIL.
- An Off the Clock page with the wrong strip count fails the content build.
- A direct write to an existing public media URL is blocked.
- Cloudflare serving stale/wrong bytes produces PROD_MISMATCH and blocks "done".
- A release uses a new content-hashed URL and public bytes match the release manifest.
- Every "complete" report includes run ID, site commit, release manifest hash,
  deployment ID, production verification, regression result, evidence index.

See `NookGuard-Plan.docx` in this folder for full appendices A-M, SQL sketch
(Appendix H), scheduled-task handoff prompt (Appendix F), owner decision packet
(Appendix E), and the 16 cited Anthropic references (Appendix L).
