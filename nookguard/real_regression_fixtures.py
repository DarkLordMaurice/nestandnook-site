"""Commit 25: real, unlabeled visual regression corpus setup.

Registers 8 real fixtures (4 confirmed real historical defects + 4 real
clean controls, all extracted byte-for-byte from git history -- see
docs/nookguard/BUILD-LOG.md's Commit 25 entry for the exact commits/paths)
into a FRESH store root (nookguard_store_real_regression/, sibling to
this file's parent), driving each through
spec-lock -> register -> validate -> review-pack-build. observe/judge are
deliberately NOT done here -- those require a live Task/Agent subagent
spawn from the orchestrating Cowork session itself, done separately per
fixture per run (see run_observe_judge_round.py).

Real provenance (git blob extraction, verified byte-for-byte against the
sizes reported in `git show --stat` for each commit, and visually
re-inspected image-by-image before being wired in here):
  - furniture_enclosure: real defect, black indoor cabinet/nightstand
    furniture hallucinated into a real outdoor aviary/bird enclosure
    photo (commit 34700dae, parent of its revert). Clean control is the
    same real scene, correctly regenerated (HEAD) -- enrichment perches
    only, no furniture.
  - banana_foil: real defect, foil "gift loaf" wrap only covering one
    end, majority of the loaf bare (commit 02cf5e9, parent of its fix
    6df32f3). Clean control is the same real scene, correctly
    regenerated (HEAD) -- foil now covers the entire loaf end-to-end.
  - object_count: real defect, cup collection meant to read as varied/
    uncoordinated instead showing a tight repeating 2-color alternating
    pattern (commit 02cf5e9, parent of fix 6df32f3). Clean control is
    the same real scene, correctly regenerated (HEAD) -- 8 individually
    distinct colors, no repeat.
  - reference_mismatch: real defect, an outdoor picnic-bench shape
    appearing inside what is otherwise a real indoor domestic room photo
    (commit 02cf5e9, parent of fix 6df32f3). Clean control is the same
    real scene, correctly regenerated (HEAD) -- no picnic furniture.
    Honest note: this is the closest verified real, git-preserved
    incident to the "goat-fence/reference mismatch" defect family named
    in the operational-acceptance instruction -- no literally goat-
    specific fence-mismatch defect was ever committed to this
    repository (per CLAUDE.md, scene_manifest.py's pre-generation gate
    is documented as having caught continuity issues for goat/location
    shots BEFORE generation, meaning no defective bytes for that literal
    case were ever produced or committed). This substitution is labeled
    honestly here and in the run report, not silently presented as a
    literal goat-fence photo.

Contracts deliberately do not reveal the expected verdict to blind
observers (requirement 5) -- each requirement/forbidden-object is framed
as a neutral, checkable claim about the image, not a statement that the
image is known-defective. Neither observer nor judge role ever receives
this module's fixture-id, "defective"/"clean" label, or provenance note
-- see run_observe_judge_round.py, which strips all of that before
building each review pack / contract payload.

Correction log:
  - banana_foil r1 (round 1 only): the original statement said the wrap
    must cover "the entire loaf... majority of the loaf's surface not
    left bare" without addressing the loaf's two cut end-faces, which
    are legitimately exposed on a correctly-wrapped loaf (foil wraps the
    cylindrical body, not the flat cut ends). Both round-1 observers
    accurately reported the clean control's exposed end-faces, and the
    judge (correctly, given the wording as written) read that as a
    coverage violation -- SEMANTIC_FAIL on a clean control, a false
    positive traced to ambiguous contract authorship, not a pipeline or
    reviewer defect. Reworded before round 2 to explicitly except the
    two end-faces while still failing the real defect (foil covering
    only ~10-15% of the loaf, one end only, per round 1's defective-
    variant observer reports). Round 1's banana_foil result stands as
    reported against the original wording; rounds 2+ use the corrected
    wording above -- see the Commit 25 report for both, disclosed
    separately, not blended.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent
REAL_IMAGES_DIR = SITE_ROOT / "nookguard" / "regression_images_real"
STORE_ROOT = SITE_ROOT / "nookguard_store_real_regression"

FIXTURES = [
    {
        "id": "furniture_enclosure",
        "asset_id": "real-regr-furniture-enclosure",
        "defective_file": "furniture_enclosure_defective.jpg",
        "clean_file": "furniture_enclosure_clean.jpg",
        "subject": "an outdoor animal enclosure",
        "action": "photographed for a facility overview",
        "scene": "an outdoor aviary-style animal enclosure with mesh walls and enrichment perches",
        "requirements": [],
        "forbidden_objects": [
            "indoor household furniture (a cabinet, nightstand, dresser, or similar case furniture) "
            "placed inside the outdoor enclosure"
        ],
    },
    {
        "id": "banana_foil",
        "asset_id": "real-regr-banana-foil",
        "defective_file": "banana_foil_defective.jpg",
        "clean_file": "banana_foil_clean.jpg",
        "subject": "a wrapped gift loaf of bread",
        "action": "resting on a table, styled for a gift-giving photo",
        "scene": "a wooden table, styled kitchen/gift setting",
        "requirements": [
            {"requirement_id": "r1", "type": "material_boundary",
             "statement": "the loaf's wrapping/packaging covers the loaf's full lengthwise body -- its top "
                          "and both long sides, running the entire length of the loaf from one end to the "
                          "other. It is normal and acceptable for the two small end-faces where the loaf "
                          "was cut/sliced to remain visibly open (this is an expected feature of a wrapped "
                          "loaf, not a coverage gap). What fails this requirement is: the wrap only encases "
                          "one end or a narrow band around the middle, leaving a long stretch of the top or "
                          "side surface -- running any significant portion of the loaf's length -- bare.",
             "critical": True},
        ],
        "forbidden_objects": [],
    },
    {
        "id": "object_count",
        "asset_id": "real-regr-object-count",
        "defective_file": "object_count_defective.jpg",
        "clean_file": "object_count_clean.jpg",
        "subject": "a collection of reusable cups displayed on a table",
        "action": "arranged in a row for a keepsake/collection photo",
        "scene": "a wooden bench or low table",
        "requirements": [
            {"requirement_id": "r1", "type": "count",
             "statement": "each cup in the row is visually distinct from its immediate neighbors -- no "
                          "simple repeating two-color alternating pattern across the collection",
             "critical": True},
        ],
        "forbidden_objects": [],
    },
    {
        "id": "reference_mismatch",
        "asset_id": "real-regr-reference-mismatch",
        "defective_file": "reference_mismatch_defective.jpg",
        "clean_file": "reference_mismatch_clean.jpg",
        "subject": "a festive drink cup with a decorative straw topper",
        "action": "placed on a coffee table",
        "scene": "an indoor domestic living room",
        "requirements": [],
        "forbidden_objects": [
            "outdoor picnic/patio furniture (a picnic table or bench) visible anywhere in the indoor "
            "room's background"
        ],
    },
]


def run_cli(args: list[str]) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "nookguard.cli", *args],
        cwd=str(SITE_ROOT), capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"unexpected exit {proc.returncode} for {args}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"non-JSON output for {args}\nstdout={proc.stdout}\nstderr={proc.stderr}")


def _add_round_marker(data: bytes, round_num: int) -> bytes:
    """store.save_attempt is deliberately content-addressed and immutable
    (section 27: "one output, one record -- no overwrite"), keyed on
    candidate_sha256 ALONE, globally across the whole store -- not scoped
    per asset_id. That is a real, intentional anti-tamper property (round
    2 hit it directly: re-quarantining round 1's literal real file bytes
    under a new asset_id collided on the existing attempt record for that
    same sha256). Weakening that invariant to make this corpus easier to
    run would be exactly the kind of shortcut the operational-acceptance
    instruction exists to prevent, so it is left untouched.

    Instead, for round_num >= 2 only, this inserts a JPEG COM (comment)
    marker segment (0xFFFE) directly after the SOI marker (0xFFD8) --
    verified byte-for-byte (see docs/nookguard/BUILD-LOG.md's Commit 25
    round-2 entry) to change the file's sha256 while leaving the decoded
    pixel data 100% identical to the original historical bytes (no
    re-encoding, no PIL re-save, no compression change -- this is a raw
    byte insertion of an ignorable metadata segment, not an image edit).
    The reviewer never sees file metadata, only the decoded image, so
    this cannot leak the round number or expected verdict to a blind
    observer. Round 1 keeps the original, unmarked, literal historical
    bytes for continuity with its already-recorded results."""
    assert data[:2] == b"\xff\xd8", "not a JPEG (missing SOI marker)"
    comment = f"nookguard-commit25-round{round_num}-session-marker".encode("ascii")
    seg = b"\xff\xfe" + (len(comment) + 2).to_bytes(2, "big") + comment
    return data[:2] + seg + data[2:]


def quarantine_real_bytes(image_path: Path, round_num: int = 1) -> str:
    """Uses the real Store.quarantine_candidate primitive directly (not
    `generate`, since these are real historical bytes, not adapter
    output) to register the file's real sha256 as a real candidate.
    round_num >= 2 applies _add_round_marker first (see its docstring)."""
    sys.path.insert(0, str(SITE_ROOT))
    from nookguard.store import Store
    store = Store(STORE_ROOT)
    data = image_path.read_bytes()
    if round_num >= 2:
        data = _add_round_marker(data, round_num)
    return store.quarantine_candidate(data, image_path.suffix)


def setup_one(fixture: dict, variant: str, round_num: int = 1) -> dict:
    """variant is 'defective' or 'clean'. round_num >= 2 mints a fully
    independent asset_id/run_id suffixed "-rN" so each of the >=3
    required independent session sets (requirement 7) gets its own
    fresh spec-lock -> generate(stub, discarded) -> real-bytes
    quarantine -> register -> validate -> review-pack-build lifecycle,
    never reusing round 1's asset state. round_num == 1 keeps the
    original unsuffixed asset_id for continuity with already-recorded
    round-1 results. Returns a dict of identifiers needed for the
    observe/judge phase (asset_id, candidate_sha256)."""
    suffix = "" if round_num == 1 else f"-r{round_num}"
    asset_id = f"{fixture['asset_id']}-{variant}{suffix}"
    image_file = fixture["defective_file"] if variant == "defective" else fixture["clean_file"]
    image_path = REAL_IMAGES_DIR / image_file

    contract = {
        "asset_id": asset_id, "project_id": "nest-and-nook", "page_id": "regression-corpus-real",
        "slot_id": "real-fixture", "media_type": "image", "risk_tier": "tier_1_routine",
        "page_type_contract_version": "1",
        "source_excerpt": f"Real historical {fixture['id']} fixture, Commit 25 operational acceptance -- "
                           "see real_regression_fixtures.py module docstring for provenance.",
        "source_excerpt_sha256": f"real-regression-{fixture['id']}-{variant}",
        "canonical_reference_bundle_sha256": "real-regression-corpus",
        "subject": fixture["subject"], "action": fixture["action"], "scene": fixture["scene"],
        "planner_session_id": "cowork-orchestrator-commit25", "plan_evaluator_session_id": "cowork-orchestrator-commit25",
        "requirements": fixture["requirements"], "forbidden_objects": fixture["forbidden_objects"],
    }
    contract_path = STORE_ROOT / f"_contract_{asset_id}.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    run_id = f"commit25-{asset_id}"
    spec = run_cli(["spec-lock", "--store-root", str(STORE_ROOT), "--run-id", run_id, "--contract", str(contract_path)])
    if not spec.get("ok"):
        return {"ok": False, "step": "spec-lock", "asset_id": asset_id, "error": spec}
    spec_sha = spec["spec_sha256"]

    prompt = run_cli(["prompt-compile", "--store-root", str(STORE_ROOT), "--run-id", run_id, "--spec", spec_sha])
    if not prompt.get("ok"):
        return {"ok": False, "step": "prompt-compile", "asset_id": asset_id, "error": prompt}
    prompt_sha = prompt["prompt_sha256"]

    # The state machine only allows CANDIDATE_REGISTERED from GENERATING
    # (PROMPT_COMPILED -> GENERATING -> CANDIDATE_REGISTERED), and the only
    # legal way to reach GENERATING is `generate`. We are deliberately NOT
    # registering the stub adapter's own throwaway output as the real
    # candidate -- that would defeat the entire point of this module (real
    # historical bytes, not adapter output). Instead: run `generate
    # --adapter stub` purely to walk the asset's state machine into
    # GENERATING (its own quarantined stub bytes are discarded, never
    # referenced again), then separately quarantine the REAL historical
    # image bytes under their own real sha256 and register THAT hash as
    # the actual candidate. `register` only requires that a) the asset is
    # in GENERATING state and b) a quarantined file exists at the given
    # --candidate-sha256 -- both are satisfied without ever calling the
    # adapter on the real bytes.
    gen = run_cli(["generate", "--store-root", str(STORE_ROOT), "--run-id", run_id,
                    "--spec", spec_sha, "--prompt", prompt_sha, "--adapter", "stub"])
    if not gen.get("ok"):
        return {"ok": False, "step": "generate-stub-state-transition", "asset_id": asset_id, "error": gen}

    candidate_sha256 = quarantine_real_bytes(image_path, round_num=round_num)

    reg = run_cli([
        "register", "--store-root", str(STORE_ROOT), "--run-id", run_id,
        "--spec", spec_sha, "--prompt", prompt_sha, "--candidate-sha256", candidate_sha256,
        "--adapter-version", "real-historical-incident-v1", "--session-id", f"real-fixture-{asset_id}",
    ])
    if not reg.get("ok"):
        return {"ok": False, "step": "register", "asset_id": asset_id, "error": reg}

    val = run_cli(["validate", "--store-root", str(STORE_ROOT), "--run-id", run_id, "--candidate-sha256", candidate_sha256])
    if not val.get("ok") or val.get("result") != "technical_pass":
        return {"ok": False, "step": "validate", "asset_id": asset_id, "error": val}

    pack = run_cli([
        "review-pack-build", "--store-root", str(STORE_ROOT), "--run-id", run_id,
        "--candidate-sha256", candidate_sha256,
    ])
    if not pack.get("ok"):
        return {"ok": False, "step": "review-pack-build", "asset_id": asset_id, "error": pack}

    return {
        "ok": True, "asset_id": asset_id, "candidate_sha256": candidate_sha256,
        "fixture_id": fixture["id"], "variant": variant, "run_id": run_id,
        "image_path": str(image_path), "spec_sha256": spec_sha, "prompt_sha256": prompt_sha,
    }


def main():
    """Usage: python -m nookguard.real_regression_fixtures [round_num]
    round_num defaults to 1 (original unsuffixed asset_ids, kept for
    continuity with already-recorded round-1 results). round_num 2/3
    mint fresh "-rN"-suffixed assets for a genuinely independent
    session set per requirement 7."""
    round_num = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    STORE_ROOT.mkdir(parents=True, exist_ok=True)
    results = []
    for fixture in FIXTURES:
        for variant in ("defective", "clean"):
            r = setup_one(fixture, variant, round_num=round_num)
            results.append(r)
            print(json.dumps(r, indent=2))
    ok_count = sum(1 for r in results if r.get("ok"))
    print(f"\n{ok_count}/{len(results)} fixtures reached OBSERVING state cleanly (round {round_num}).")
    out_path = STORE_ROOT / f"_setup_results_round{round_num}.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
