# Nest & Nook — Claude Handoff: Visual Stabilization and Growth Continuation

**Prepared:** 2026-07-13 (America/Los_Angeles)  
**Repository:** `DarkLordMaurice/nestandnook-site`  
**Production site:** `https://nestandnook.org`  
**Owner:** Maurice / DarkLordMaurice  
**Read this before editing or deploying.** A recent deployment briefly broke the production stylesheet. The live site has been reverted; the visual-repair work below is local and has **not** been deployed.

---

## 1. Executive status

Nest & Nook is a research-led small-space home site covering home offices, kitchens, pet-care zones, and garages. It uses a consistent illustrated/photographic brand world centered on virtual host **Winnie Hollowell** and has four planning tools.

The current priority is not broad new growth work. It is to finish a **safe visual stabilization pass** for the new tools, verify it carefully on desktop and mobile, and only then deploy. The owner’s feedback was direct and should govern the work:

- Homepage and tool-directory content was oversized; reduce visual scale by roughly 25% where appropriate.
- Tool-directory cards felt visually inconsistent with the rest of the site and consumed too much of the screen.
- Primitive diagram-like card art looked poor and did not communicate the tools well.
- Functional tool diagrams should remain accurate and accessible, but their surrounding presentation needs to look deliberate and modern.
- Do not make the owner repeat manual Git/Powershell merge steps. The owner has authorized normal push/merge/deploy work after appropriate validation, but the recent incident means that **visual and deployment gates are mandatory**.

### Current live source vs. local repair source

| State | Commit / branch | Meaning |
| --- | --- | --- |
| **Production source / `origin/main`** | `9d71012` — `Revert "Refine Workbench visuals and scale"` | Current safe rollback. This is the state that should be treated as live baseline. |
| Earlier successful tool suite | `33bef73` — `Expand and redesign the planning tools suite (#5)` | Added/reworked four tools and associated discovery pages. |
| Bad deployment commit | `5433603` — `Refine Workbench visuals and scale` | Was pushed to `main`, then the live site appeared unstyled. It is reverted by `9d71012`. Do not reintroduce it wholesale. |
| **Local visual-repair candidate** | branch `codex/visual-stabilization-2026-07-13`, commit `f37855a` — `Refine tool visuals and mobile scale` | The next candidate. It is locally committed, ahead of `origin/main`, and **not pushed/deployed**. |
| Separate growth foundation package | `codex/growth-foundation-2026-07-12`, commit `4659916` — `Build growth and discovery foundation` | A separate, validated growth package to integrate only after visual stabilization is safely complete. |

Do not assume a local branch is present in every environment. Start by fetching and inspecting the commits above.

---

## 2. What happened in the deployment incident

This chronology matters because it defines the safety requirements.

1. The planning-tool suite (`33bef73`) was merged and live.
2. The owner reported that the tool cards and tool-page graphics were unattractive/oversized and asked for a visual repair.
3. A small repair bundle was prepared and manually pushed to GitHub due to an authentication/workflow problem. The resulting `main` update was `33bef73..5433603`.
4. Production then rendered as essentially unstyled HTML: no normal backgrounds/layout/type treatment, indicating that CSS assets were not loading or the generated deployment was otherwise incomplete. The user supplied screenshots showing the failure.
5. An immediate rollback was made. `9d71012` reverted `5433603`, restoring the prior safe live source.

### Facts and non-facts

- **Fact:** the site looked unstyled after the `5433603` deployment and was restored after the rollback.
- **Fact:** the normal production build had passed before the bad deployment. A successful local build alone is therefore not sufficient sign-off.
- **Unknown:** the root cause of the CSS failure. Do not state that it was definitively Cloudflare, browser cache, Astro, Pagefind, or the repair CSS. It was not conclusively diagnosed.
- **Fact:** the owner later saw the intended newer tool imagery on desktop after the rollback/recovery period, but did not initially see it in iPhone Safari. This may be cache/deploy propagation behavior, but it is not diagnosed. Treat mobile Safari as a required visual check.

### Deployment rule derived from this incident

Never say a visual change is complete merely because tests/build pass. Before deploying, perform a concrete visual review of the generated pages; after deploying, confirm the production CSS and representative pages load normally. Keep an immediately identifiable rollback commit/reference.

---

## 3. Current visual-repair candidate (`f37855a`)

### Intent

`f37855a` is a focused repair, not a redesign of the planning tools’ functionality. It replaces crude promotional card art with existing high-quality on-brand Winnie scene photography, compacts the directory/home tool presentation, and makes the functional diagrams less chunky without replacing precise diagrams with unreliable generated art.

### Changes included

#### A. Tool discovery cards: real contextual scenes, compact scale

The new component `src/components/tools/ToolScene.astro` and revised `src/components/tools/ToolCard.astro` use existing scene assets instead of toy-like illustrations:

| Tool | Photo selected | Why it fits |
| --- | --- | --- |
| Counter Footprint Simulator | `compact-air-fryer-counter-clearance-check.jpg` | Shows a real counter-clearance/appliance decision. |
| Desk Fit Reality Check | `winnie-office-small-desk-posture.jpg` | Shows seated desk ergonomics in context. |
| Apartment Pet Zone Planner | `small-space-pet-care-setup-guide-scene1.jpg` | Shows pet-care setup in a small space. |
| Fold-Away Workbench Fit Planner | `garage-workbench-car-clearance-check.jpg` | Shows garage workbench/clearance context. |

The cards are designed to be two columns on desktop rather than giant tall panels, while remaining one column and compact on mobile. CTA copy is simplified to “Open tool.”

#### B. Tool-page context panel

Each tool page imports `ToolScene.astro`, adding a short, compact photo/caption panel beneath its hero so the tool has an attractive, immediately legible context without compromising the measurement UI.

Affected pages:

- `src/pages/tools/counter-footprint-simulator.astro`
- `src/pages/tools/desk-fit-reality-check.astro`
- `src/pages/tools/apartment-pet-zone-planner.astro`
- `src/pages/tools/fold-away-workbench-fit-planner.astro`

#### C. Homepage scale reduction

The homepage brand wordmark, hero spacing, and hero image height were reduced approximately 25%:

- wordmark: `clamp(3.2rem, 7vw, 5rem)` → `clamp(2.4rem, 5.25vw, 3.75rem)`
- hero gap: `2.25rem` → `1.5rem`
- hero image max-height: `350px`

This addresses the owner’s “everything is really large” feedback while preserving hierarchy.

#### D. Functional diagram treatment

The pet-zone and workbench surfaces were refined with less oversized spacing, stronger boundaries/grid treatment, and smaller UI proportions:

- `src/styles/pet-zone-planner-addon.css`
- `src/styles/workbench-planner-addon.css`

Do **not** replace functional clearance/measurement diagrams with generic generated images. These diagrams need to remain semantically clear, responsive, and accurate. Photo imagery belongs in context/promotion; code-native diagrams belong in interactive measurement work.

### Files changed by `f37855a`

```text
src/components/tools/ToolCard.astro
src/components/tools/ToolScene.astro                 (new)
src/pages/tools/counter-footprint-simulator.astro
src/pages/tools/desk-fit-reality-check.astro
src/pages/tools/apartment-pet-zone-planner.astro
src/pages/tools/fold-away-workbench-fit-planner.astro
src/styles/global.css
src/styles/tools.css
src/styles/pet-zone-planner-addon.css
src/styles/workbench-planner-addon.css
```

### Validation already completed for `f37855a`

The following passed locally:

```bash
ASTRO_TELEMETRY_DISABLED=1 npm run build
```

Results:

- readiness audit completed with the repository’s **12 pre-existing, non-blocking warnings** (contact email verification, two intentionally queued photo items, and update-date warnings)
- **37/37 tool tests passed**
- Astro generated **130 pages**
- Pagefind indexed **130 pages**
- `git diff --check` passed before commit

### Build-environment note

Astro telemetry attempted to write under `/root/.config/astro` in this environment. Disabling telemetry with `ASTRO_TELEMETRY_DISABLED=1` avoids that environment-specific failure. This is not evidence of a production problem.

---

## 4. Visual verification is still required

No one should claim that `f37855a` was visually verified live. It was not.

An attempt was made to use the hosted/cloud browser for visual screenshots, as requested by the owner. Both `https://nestandnook.org` and a local preview were blocked by the browser environment’s security policy. The browser reported a policy block; this should be treated as a tooling/session limitation, not proof that the site is inaccessible or misconfigured. A local Astro preview also had an environment-specific interface error. Therefore, no authoritative automated screenshots were captured from this environment.

In a fresh Claude environment, try normal visual capture again. If browser capture is unavailable, use a reliable local rendering or ask the owner only for a short visual confirmation after providing a safe preview/deployment. Do not fabricate screenshot evidence.

### Mandatory pre-deploy visual matrix

Render/build and inspect at minimum the following at desktop and a narrow mobile viewport:

| Route | Must confirm |
| --- | --- |
| `/` | CSS/background loads; hero is materially more compact; planning-tools section fits the site’s visual language; cards are not screen-filling. |
| `/tools/` | Four cards form a coherent compact grid on desktop; images crop cleanly; card CTA/heading text remains legible; single-column mobile layout works. |
| `/tools/counter-footprint-simulator/` | Context photo, inputs, result state, printable/result presentation, responsive layout. |
| `/tools/desk-fit-reality-check/` | Context photo, validation state, realistic result state, responsive layout. |
| `/tools/apartment-pet-zone-planner/` | Context photo, zone placement/interaction, no clipped map/UI at mobile size. |
| `/tools/fold-away-workbench-fit-planner/` | Context photo, open/folded modes, result/clearance UI, no clipped map/UI at mobile size. |

For each page, also confirm that the primary CSS bundle returns successfully and that there is no fallback unstyled page. A visual check must include at least one hard refresh / clean browsing context after deploy, particularly for Safari.

### Mandatory post-deploy gate

Immediately after a deployment:

1. Open `/` and one article/commercial page to confirm global styles, fonts, backgrounds, and images load.
2. Open `/tools/` and each of the four tool routes.
3. Confirm a key interaction in each tool.
4. Check desktop and mobile/Safari if possible.
5. If production looks unstyled or key assets fail, revert promptly to the known safe source (`9d71012` or its then-current descendant) and investigate from logs/build artifacts rather than guessing.

---

## 5. Safe continuation sequence

### Phase 0 — orient safely

1. Fetch repository state and confirm the live/default branch is still based on `9d71012` (or identify any legitimate later work).
2. Inspect `f37855a` as a focused diff against the live baseline. Do not blindly replay `5433603`.
3. Confirm there are no unrelated working-tree changes before touching files.
4. Preserve a rollback reference before deployment.

### Phase 1 — finish and ship visual stabilization

1. Build `f37855a` using the telemetry-disabled command above.
2. Complete the visual matrix. Fix only demonstrated visual/accessibility/responsiveness defects.
3. Ensure tool functionality remains covered by the existing test suite.
4. Rebase/merge carefully against current `origin/main`, commit intentionally, and deploy using the repository’s normal authenticated workflow.
5. Perform the post-deploy gate. Do not report completion until CSS and tool pages are visually confirmed.

The owner has asked that normal validated work be pushed/merged without making them manually drive Git. Respect that intent where authenticated tooling actually permits it. However, do not promise push/deploy capability that the session does not have, and do not bypass validation because of that authorization.

### Phase 2 — integrate the growth foundation package

After Phase 1 is stable, inspect/rebase the separate foundation branch:

- branch: `codex/growth-foundation-2026-07-12`
- commit: `4659916` — `Build growth and discovery foundation`

Known handoff/support files associated with that package:

```text
GROWTH_FOUNDATION_HANDOFF_2026-07-12.md
PRINTABLE_ASSET_PRODUCTION_SPEC.md
TOOL_ADJACENT_CONTENT_QUEUE.md
PINTEREST_DISTRIBUTION_SYSTEM.md
ANALYTICS_EVENT_DICTIONARY.md
ACCOUNT_SETUP_CHECKLIST.md
```

The package reportedly includes improved small-space positioning, homepage metadata/copy/schema, a “Start Here” problem finder, a registry-driven solve-before-you-shop area, privacy-safe analytics infrastructure, reusable evidence blocks, content/printable/Pinterest plans, and account setup instructions. It was previously validated with 18/18 tool tests, a successful production build, 128 pages, and Pagefind indexing at the time it was made.

Because the tool suite changed afterward, **do not merge it blindly**. Reconcile conflicts intentionally, retain the current visual-stabilization decisions, rerun the full build/test suite, and review the homepage/tool sections visually.

### Phase 3 — highest-value content and conversion work

Once visual stability and the foundation package are safely integrated:

1. Build the actual **Desk Fit Measurement Sheet** as an accessible HTML page with a low-ink printable version.
2. Build the **Counter Appliance Footprint Template**.
3. Draft and publish the first two tool-adjacent search articles:
   - *How to Measure Desk Underside Clearance*
   - *How Much Kitchen Counter Should Remain Clear?*
4. Add privacy-safe event hooks for tool completion, result printing, related-guide clicks, and affiliate clicks. Never collect user measurements in analytics.
5. Prepare Pinterest creative briefs and exact copy variants.
6. Apply the reusable commercial-page evidence block to priority commercial pages.

### Work requiring account access

Do not represent these as completed until authenticated and verified:

- Google Search Console and Bing verification
- Cloudflare dashboard/CDN verification
- IndexNow configuration
- Pinterest domain claiming and account configuration
- email-provider configuration
- Amazon Associates approval/tag activation

---

## 6. Content, research, and Winnie rules

### Editorial rules

Nest & Nook must be useful, research-led, and scenario-based. Do not:

- invent personal product testing, customer reviews, prices, availability, ASINs, or product specifications;
- claim Winnie personally tested a product when she did not;
- turn a recommendation page into unsupported marketing copy;
- collect personal room/body measurements in analytics.

When making commercial recommendations, state the decision criteria and trade-offs clearly. Use evidence and primary sources where feasible.

### Winnie Hollowell is a virtual host

Winnie is a consistent, intentionally fictional visual persona—not a real person or real hands-on tester. Key canonical characteristics include:

- approximately 43 years old / appears 42–44; never write “late 40s”;
- warm medium-brown skin, lean/athletic build, hands appropriate to early 40s;
- voluminous copper-red curly updo with magenta streaks;
- patterned jewel-toned scarf, tortoiseshell glasses, brass/gold jewelry;
- warm, curated home-office/studio aesthetic.

Before generating any new Winnie image, read:

- `Character-Bible.md`
- `Winnie_Hollowell_Image_Generation_Rules_v2.docx`
- `Nest_and_Nook_SEO_Image_Production_Strategy_v1.docx`

Use the required reference/slot preflight: page/title/image number/filename, role, pose, wardrobe, location/zone, and action. The owner has strong visual standards and specifically rejected generic or toy-like tool art. Prefer existing polished scene photography when it already fits the need.

The three supplied portrait references are available under `project_sources/` and should be treated as identity/style references, not arbitrary stock photography.

---

## 7. Useful repository and source files

Review these before broad changes:

- `README.md`, `package.json`, and deployment configuration/workflows
- tool components under `src/components/tools/`
- the four tool routes under `src/pages/tools/`
- `src/styles/global.css`, `src/styles/tools.css`, and tool-specific addon CSS
- `GROWTH_FOUNDATION_HANDOFF_2026-07-12.md` and the related growth files listed above
- `Character-Bible.md`
- strategy documents in `project_sources/`, especially the SEO execution, AI search, Amazon Associates, evidence/citation, sustainable asset-machine, and image-production documents.

No external credentials, private tokens, or account secrets should be copied into commits or handoff files.

---

## 8. Definition of done for the current repair

The visual-stabilization task is complete only when all of the following are true:

- `f37855a` (or a carefully reviewed successor) is merged without pulling in the failed `5433603` behavior.
- production stylesheet, fonts, backgrounds, and imagery load normally after deployment;
- homepage and tool directory are visibly more compact and coherent;
- tool cards use the selected real scene imagery and retain readable text/CTA at desktop and mobile;
- all four tools work at representative input states;
- full build, tests, Pagefind, and readiness audit pass;
- desktop plus mobile/Safari visual review is recorded honestly;
- rollback target is known before deploy and no unstyled production regression remains.

---

## 9. Suggested first prompt to Claude

> Read `CLAUDE_HANDOFF_VISUAL_STABILIZATION_2026-07-13.md` in full. First inspect `origin/main`, `9d71012`, `f37855a`, and `4659916` without changing anything. Confirm the current production baseline and the exact diff for the local visual-repair candidate. Then run the prescribed build/tests and perform a visual review of the route matrix before proposing or deploying any merge. Do not claim a visual check occurred unless you have actual rendered evidence.

