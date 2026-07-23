"""mediactl — the CLI every NookGuard actor (Claude sessions, CI jobs) talks
to. Every command prints exactly one JSON object to stdout as its last line
and returns a matching dict, so both humans/CI (parsing stdout) and tests
(calling the cmd_* functions directly) get the same contract. Commands never
raise on expected/business-logic failures (bad contract, illegal transition,
missing file) — those come back as {"ok": false, "error": ...} with exit code
1. Only truly unexpected errors raise."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .adapters import AVAILABLE_ADAPTERS
from .aggregator import aggregate
from .agent_runner import (
    ReviewSessionError,
    build_judge_prompt,
    build_observer_prompt,
    build_page_review_prompt,
    finalize_judgment,
    finalize_observation,
    finalize_page_review,
    run_judge_session,
    run_observer_session,
    run_page_review_session,
)
from .canon import CanonRegistry
from .cli_reviewer import check_claude_cli_auth
from .containment import (
    ContainmentViolation, close_containment, cleanup_scratch, create_scratch, open_containment,
)
from .dedup import DedupRegistry
from .deploy import WranglerDeployError, check_cloudflare_credentials, run_wrangler_deploy
from .exceptions import (
    HashMismatchError,
    InvalidTransitionError,
    MissingCanonError,
    NookGuardError,
    StaleCanonError,
)
from .hashing import sha256_bytes, sha256_canonical_json
from .ledger import Ledger
from .off_the_clock_schema import (
    OFF_THE_CLOCK_CATEGORIES,
    extract_category,
    lint_off_the_clock_file,
    split_frontmatter,
)
from .manifest import ReleaseManifestEntry
from .owner_queue import OwnerQueue, should_queue_for_owner
from .preview import PageCaptureReport
from .preview_aggregator import aggregate_preview
from .production_verifier import verify_production
from .prompt_compiler import compile_prompt
from .public_media_guard import DEFAULT_SITE_ROOT, audit_public_media
from .regression_corpus import run_regression_corpus
from .regression_live import run_live_review_regression_corpus
from .release import ReleaseIntegrityError, publish_candidate
from .review_pack import OBSERVER_ROLES, build_review_pack
from .run_report import write_run_report
from .schemas import AssetContract, GenerationAttempt
from .state_machine import AssetState, transition
from .store import Store
from .write_path_audit import report_to_dict, run_write_path_audit
from .validators import image as image_validator

DEFAULT_STORE_ROOT = Path("nookguard_store")
# nookguard/cli.py -> nookguard -> site -> project root
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _store(root: Path) -> Store:
    return Store(root)


def _ledger(root: Path) -> Ledger:
    return Ledger(root / "events.jsonl")


# ---- Commit 24: reviewer containment + response custody helpers ----
# Shared by observe-prepare/-submit, judge-prepare/-submit, and
# preview-review-prepare/-submit -- one real implementation of "create a
# scratch dir, open containment, run the reviewer, close containment,
# invalidate on violation" rather than three near-duplicate copies that
# could quietly drift apart.

def _site_root(args: argparse.Namespace) -> Path:
    # cli.py already distinguishes --project-root (business-project root,
    # brand-assets/ etc.) from the real site/ directory -- see
    # public_media_guard.py's own module docstring for why conflating them
    # is a real, previously-hit bug. cmd_media_audit/cmd_deploy already take
    # an explicit --site-root; containment reuses that same convention,
    # defaulting to the real site/ dir when a command has no such flag of
    # its own (observe/judge/preview-review commands don't take --site-root
    # today -- default to public_media_guard.DEFAULT_SITE_ROOT).
    from .public_media_guard import DEFAULT_SITE_ROOT
    return Path(getattr(args, "site_root", None) or DEFAULT_SITE_ROOT)


def _open_review_containment(
    args: argparse.Namespace, root: Path, label: str, candidate_path: Path | None, instructions: str,
) -> tuple[Path, str]:
    scratch_dir = create_scratch(root, label, candidate_path, instructions)
    open_containment(root, scratch_dir, project_root=Path(args.project_root), site_root=_site_root(args))
    return scratch_dir, scratch_dir.name


def _close_review_containment(args: argparse.Namespace, root: Path, containment_id: str):
    """Returns the closed ContainmentRecord on success. Raises
    ContainmentViolation (uncaught here -- every call site below is
    responsible for converting that into a real REVIEW_ERROR-equivalent
    process failure, never a silently-accepted result) if anything outside
    the scratch directory changed during the reviewer's turn."""
    return close_containment(root, containment_id, project_root=Path(args.project_root), site_root=_site_root(args))


def _validate_submit_hashes(
    *, args: argparse.Namespace, response_text: str, expected_review_pack_sha256: str | None = None,
    expected_contact_sheet_sha256: str | None = None,
) -> Optional[dict[str, Any]]:
    """Commit 24, requirements 5-6: every production-mode submit command now
    requires the caller to supply (not just a --response-file, but) the
    reviewer session ID it actually used, the raw response's own sha256, and
    either the review-pack sha256 (observe/judge) or the contact-sheet
    sha256 (preview-review) -- each independently re-verified here against
    the real bytes/values on this side, rather than trusted at face value.
    Returns an {"ok": False, ...} dict (the standard cli.py error contract)
    on any mismatch, or None if everything checks out clean."""
    if not args.reviewer_session_id or not args.reviewer_session_id.strip():
        return {"ok": False, "error": "missing or empty --reviewer-session-id", "reason": "missing_session_id"}

    actual_response_sha256 = sha256_bytes(response_text.encode("utf-8"))
    if actual_response_sha256 != args.raw_response_sha256:
        return {"ok": False, "error": "raw-response-sha256 mismatch: the response file's actual bytes do "
                                       f"not hash to the supplied --raw-response-sha256 (expected "
                                       f"{args.raw_response_sha256}, computed {actual_response_sha256}) -- "
                                       "refusing to trust a response whose custody chain doesn't check out",
                "reason": "raw_response_hash_mismatch",
                "expected_raw_response_sha256": args.raw_response_sha256,
                "actual_raw_response_sha256": actual_response_sha256}

    if expected_review_pack_sha256 is not None:
        supplied = getattr(args, "review_pack_sha256", None)
        if supplied != expected_review_pack_sha256:
            return {"ok": False, "error": "review-pack-sha256 mismatch: the supplied --review-pack-sha256 "
                                           f"({supplied}) does not match the real review pack this candidate/"
                                           f"role actually produces ({expected_review_pack_sha256})",
                    "reason": "review_pack_hash_mismatch",
                    "expected_review_pack_sha256": expected_review_pack_sha256,
                    "supplied_review_pack_sha256": supplied}

    if expected_contact_sheet_sha256 is not None:
        supplied = getattr(args, "contact_sheet_sha256", None)
        if supplied != expected_contact_sheet_sha256:
            return {"ok": False, "error": "contact-sheet-sha256 mismatch: the supplied "
                                           f"--contact-sheet-sha256 ({supplied}) does not match the real "
                                           f"contact sheet on disk ({expected_contact_sheet_sha256})",
                    "reason": "contact_sheet_hash_mismatch",
                    "expected_contact_sheet_sha256": expected_contact_sheet_sha256,
                    "supplied_contact_sheet_sha256": supplied}
    return None


def _persist_review_evidence(
    root: Path, kind: str, key: str, *, raw_response: str, parsed_result: dict[str, Any] | None,
    diagnostics: dict[str, Any],
) -> dict[str, str]:
    """Commit 24, requirement 7: the untouched raw response, the parsed/
    validated result, and the parsing diagnostics are three SEPARATE files
    -- never merged into one, so a later audit can always tell what the
    model literally said apart from what NookGuard's own code concluded
    from it. `kind` is 'observe'/'judge'/'preview_review'; `key` is
    whatever uniquely identifies this specific submission (e.g.
    '{candidate_sha256}_{role}')."""
    evidence_dir = Path(root) / "review_evidence" / kind
    evidence_dir.mkdir(parents=True, exist_ok=True)
    raw_path = evidence_dir / f"{key}.raw_response.txt"
    diag_path = evidence_dir / f"{key}.parsing_diagnostics.json"
    raw_path.write_text(raw_response, encoding="utf-8")
    diag_path.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    result = {"raw_response_path": str(raw_path), "parsing_diagnostics_path": str(diag_path)}
    if parsed_result is not None:
        parsed_path = evidence_dir / f"{key}.parsed_result.json"
        parsed_path.write_text(json.dumps(parsed_result, indent=2, default=str), encoding="utf-8")
        result["parsed_result_path"] = str(parsed_path)
    return result


def cmd_run_start(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.store_root)
    ledger = _ledger(root)
    run_id = args.run_id or f"nn-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"
    ledger.append(run_id=run_id, event_type="run.started", actor_role=args.actor_role,
                  payload={"run_id": run_id}, actor_session_id=args.session_id)
    return {"ok": True, "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat()}


def cmd_run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.store_root)
    checks: dict[str, Any] = {}
    try:
        store = _store(root)
        checks["store_writable"] = True
    except OSError as e:
        checks["store_writable"] = False
        checks["store_error"] = str(e)
    try:
        ledger = _ledger(root)
        ledger.append(run_id=args.run_id, event_type="run.preflight", actor_role=args.actor_role,
                       payload={"checks": "pending"})
        checks["ledger_writable"] = True
    except OSError as e:
        checks["ledger_writable"] = False
        checks["ledger_error"] = str(e)
    preflight_pass = all(v is True for k, v in checks.items() if k.endswith("_writable"))
    return {"ok": preflight_pass, "run_id": args.run_id, "checks": checks}


def cmd_spec_lock(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    contract_path = Path(args.contract)
    if not contract_path.exists():
        return {"ok": False, "error": f"contract file not found: {contract_path}"}

    raw = json.loads(contract_path.read_text(encoding="utf-8"))
    try:
        contract = AssetContract.model_validate(raw)
    except Exception as e:  # pydantic ValidationError etc.
        return {"ok": False, "error": f"contract failed schema validation: {e}"}

    vague = contract.validate_requirements_are_concrete()
    if vague:
        return {"ok": False, "error": "vague, non-evidence-checkable requirements",
                "vague_requirement_ids": vague}

    canon = CanonRegistry(args.project_root)
    missing = canon.missing_canon_files()
    if missing:
        return {"ok": False, "error": f"missing canon file(s): {missing}",
                "missing_canon_files": missing}
    # Spec-lock always stamps the REAL current canon bundle hash — never trust
    # a caller-supplied value here, since the whole point is that this hash
    # reflects canon as it truly is at lock time (H007's basis).
    contract.canonical_reference_bundle_sha256 = canon.bundle_sha256()

    spec_sha256 = store.save_spec(contract)
    store.set_state(contract.asset_id, AssetState.SPEC_LOCKED.value)
    ledger.append(run_id=args.run_id, event_type="asset.spec_locked", actor_role=args.actor_role,
                  payload={"spec_sha256": spec_sha256, "asset_id": contract.asset_id},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "spec_sha256": spec_sha256}


def cmd_prompt_compile(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        contract = store.load_spec(args.spec)
    except (FileNotFoundError, HashMismatchError) as e:
        return {"ok": False, "error": str(e)}

    current = store.get_state(contract.asset_id)
    try:
        transition(AssetState(current), AssetState.PROMPT_COMPILED, asset_id=contract.asset_id)
    except InvalidTransitionError as e:
        return {"ok": False, "error": str(e)}

    canon = CanonRegistry(args.project_root)
    try:
        prompt_text = compile_prompt(contract, project_root=args.project_root, canon_registry=canon)
    except MissingCanonError as e:
        return {"ok": False, "error": str(e), "missing_canon_files": e.missing}
    except StaleCanonError as e:
        return {"ok": False, "error": str(e), "referenced_bundle_sha256": e.referenced,
                "current_bundle_sha256": e.current}
    except ValueError as e:
        return {"ok": False, "error": f"incompatible prompt modules: {e}"}
    prompt_sha256 = store.save_prompt(prompt_text)
    store.set_state(contract.asset_id, AssetState.PROMPT_COMPILED.value)
    ledger.append(run_id=args.run_id, event_type="prompt.compiled", actor_role=args.actor_role,
                  payload={"spec_sha256": args.spec, "prompt_sha256": prompt_sha256},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "spec_sha256": args.spec,
            "prompt_sha256": prompt_sha256}


def cmd_generate(args: argparse.Namespace) -> dict[str, Any]:
    if args.adapter not in AVAILABLE_ADAPTERS:
        return {"ok": False, "error": (
            f"adapter '{args.adapter}' not available yet — only {sorted(AVAILABLE_ADAPTERS)} "
            "exist until Commit 5 wraps the real Hugging Face pipeline. This command will not "
            "pretend to call a real model."
        )}
    # Commit 19, requirement 7: real generation must not proceed if the
    # candidate it produces could never be reviewed afterward -- that is
    # pure wasted generation cost/risk with no possible resolution. The
    # stub adapter is exempt (it exists purely for tests/dev and is never
    # a real, reviewable asset).
    #
    # Real correctness defect found and corrected 2026-07-23, during the
    # first genuine attempt to generate a fresh candidate after Commit 23:
    # this gate's rationale ("could not be reviewed afterward") was written
    # when `claude_cli_executor` (a separate, manually-authenticated Claude
    # Code CLI process) was the ONLY way review could happen -- so
    # check_claude_cli_auth() was a correct proxy for "can this candidate
    # be reviewed." Commit 23 made that proxy stale without updating this
    # gate: review can now also happen via observe-prepare/-submit and
    # judge-prepare/-submit, driven by a live, already-authenticated Cowork
    # orchestrating agent's own subagents -- a real, working review path
    # that check_claude_cli_auth() knows nothing about and will always
    # report unauthenticated for, even though review genuinely CAN proceed.
    # `--skip-auth-check` was previously documented as test-only; it is now
    # the correct, real flag for exactly this production scenario: a live
    # orchestrating agent calling `generate` is, by construction, already
    # committing to perform observe-prepare/-submit and judge-prepare/
    # -submit itself afterward (Commit 23's whole design), so the
    # candidate is NOT actually unreviewable -- check_claude_cli_auth()
    # was just asking the wrong question. This flag still has no legitimate
    # use for a truly unattended caller with no live agent behind it (a bare
    # scheduled subprocess with nobody able to perform the subagent half) --
    # that caller genuinely cannot complete review either way, and should
    # either use the real CLI-auth path or not generate at all.
    if args.adapter != "stub" and not getattr(args, "skip_auth_check", False):
        auth_result = check_claude_cli_auth()
        if not auth_result["authenticated"]:
            return {"ok": False, "error": "auth-check failed -- refusing to generate a real "
                                           "candidate that could not be reviewed afterward "
                                           f"(reason: {auth_result.get('reason')})",
                    "reason": "auth_check_failed", "auth_check": auth_result}
    root = Path(args.store_root)
    store = _store(root)
    try:
        contract = store.load_spec(args.spec)
        prompt_text = store.load_prompt(args.prompt)
    except (FileNotFoundError, HashMismatchError) as e:
        return {"ok": False, "error": str(e)}

    current = store.get_state(contract.asset_id)
    try:
        transition(AssetState(current), AssetState.GENERATING, asset_id=contract.asset_id)
    except InvalidTransitionError as e:
        return {"ok": False, "error": str(e)}

    if args.adapter == "stub":
        from .adapters import stub as adapter_module
        image_bytes = adapter_module.generate(prompt_text)
        ext = ".png"
    else:  # "huggingface" — the only other member of AVAILABLE_ADAPTERS
        from .adapters import huggingface as adapter_module
        from .adapters.huggingface import AdapterGenerationBlockedError
        try:
            image_bytes = adapter_module.generate(prompt_text)
        except AdapterGenerationBlockedError as e:
            return {"ok": False, "error": str(e), "generation_blocked_reason": e.reason,
                    "attempts": e.attempts}
        ext = ".jpg"

    candidate_sha256 = store.quarantine_candidate(image_bytes, ext)
    store.set_state(contract.asset_id, AssetState.GENERATING.value)

    return {"ok": True, "asset_id": contract.asset_id, "candidate_sha256": candidate_sha256,
            "adapter_version": adapter_module.ADAPTER_VERSION,
            "artifact_uri": str(store.candidate_path(candidate_sha256))}


def cmd_register(args: argparse.Namespace) -> dict[str, Any]:
    # GenerationAttempt.generator_session_id is a required (non-Optional)
    # str field (schemas.py) -- unlike most other commands, --session-id
    # isn't cosmetic here. A caller that omits it used to hit a raw,
    # unhandled pydantic ValidationError, violating this module's own
    # stated contract ("commands never raise on expected/business-logic
    # failures"). Caught by Commit 13's canary-run, whose register step
    # was the first caller in this codebase to ever omit --session-id.
    if not args.session_id:
        return {"ok": False, "error": "register requires --session-id (GenerationAttempt.generator_session_id "
                                       "is a required field, not cosmetic)"}

    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        contract = store.load_spec(args.spec)
    except (FileNotFoundError, HashMismatchError) as e:
        return {"ok": False, "error": str(e)}

    current = store.get_state(contract.asset_id)
    try:
        transition(AssetState(current), AssetState.CANDIDATE_REGISTERED, asset_id=contract.asset_id)
    except InvalidTransitionError as e:
        return {"ok": False, "error": str(e)}

    try:
        store.load_prompt(args.prompt)  # raises if missing/tampered
        candidate_path = store.candidate_path(args.candidate_sha256)
    except (FileNotFoundError, HashMismatchError) as e:
        return {"ok": False, "error": str(e)}

    attempt = GenerationAttempt(
        candidate_sha256=args.candidate_sha256, asset_id=contract.asset_id,
        spec_sha256=args.spec, prompt_sha256=args.prompt, adapter_version=args.adapter_version,
        model_revision=args.model_revision, parameters={}, generator_session_id=args.session_id,
        artifact_uri=str(candidate_path),
    )
    try:
        store.save_attempt(attempt)
    except FileExistsError as e:
        return {"ok": False, "error": str(e)}

    store.set_state(contract.asset_id, AssetState.CANDIDATE_REGISTERED.value)
    ledger.append(run_id=args.run_id, event_type="generation.registered", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "candidate_sha256": args.candidate_sha256}


def cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = store.get_state(contract.asset_id)
    target = AssetState.TECHNICAL_VALIDATING
    try:
        transition(AssetState(current), target, asset_id=contract.asset_id)
    except InvalidTransitionError as e:
        return {"ok": False, "error": str(e)}
    store.set_state(contract.asset_id, target.value)

    dedup_registry = DedupRegistry(store.dedup_registry_path)
    candidate_path = store.candidate_path(args.candidate_sha256)
    report = image_validator.validate(
        candidate_path, dedup_registry=dedup_registry, candidate_sha256=args.candidate_sha256,
        require_ocr=contract.requires_ocr_scan,
    )
    final = AssetState.TECHNICAL_PASS if report["technical_pass"] else AssetState.TECHNICAL_FAIL
    transition(target, final, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, final.value)

    # Only register into the corpus on a real pass — a failed/blank/duplicate
    # candidate shouldn't become a future "known good" comparison point.
    if final == AssetState.TECHNICAL_PASS:
        dedup_registry.register(args.candidate_sha256, candidate_path)

    # Commit 20, requirement 5: surface VALIDATOR_UNAVAILABLE distinctly at
    # the top level (both the ledger payload and the returned dict), not
    # just buried inside report["checks"] -- "block the asset" needs to be
    # a real, checkable signal a caller can branch on without re-deriving
    # it from the full technical report.
    payload = {"candidate_sha256": args.candidate_sha256, "result": final.value, "report": report}
    response = {"ok": True, "asset_id": contract.asset_id, "result": final.value, "report": report}
    if report.get("blocking_reason"):
        payload["blocking_reason"] = report["blocking_reason"]
        response["blocking_reason"] = report["blocking_reason"]

    ledger.append(run_id=args.run_id, event_type="technical_validation.completed",
                  actor_role=args.actor_role, payload=payload, asset_id=contract.asset_id)
    return response


def cmd_review_pack_build(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = store.get_state(contract.asset_id)
    target = AssetState.OBSERVING
    try:
        transition(AssetState(current), target, asset_id=contract.asset_id)
    except InvalidTransitionError as e:
        return {"ok": False, "error": str(e)}

    candidate_path = str(store.candidate_path(args.candidate_sha256))
    packs = {}
    for role in OBSERVER_ROLES:
        pack = build_review_pack(args.candidate_sha256, candidate_path, role)
        review_pack_sha256 = store.save_review_pack(pack)
        packs[role] = {"review_pack_sha256": review_pack_sha256}

    store.set_state(contract.asset_id, target.value)
    ledger.append(run_id=args.run_id, event_type="review_pack.built", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "review_packs": packs},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "review_packs": packs}


def cmd_observe(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
        candidate_path = str(store.candidate_path(args.candidate_sha256))
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.OBSERVING:
        return {"ok": False, "error": f"Illegal transition {current.value} -> observe "
                                       "(asset must be in observing state, set by mediactl review-pack-build)"}

    observations: dict[str, Any] = {}
    for role in OBSERVER_ROLES:
        pack = build_review_pack(args.candidate_sha256, candidate_path, role)
        try:
            obs = run_observer_session(pack)
        except ReviewSessionError as e:
            transition(current, AssetState.REVIEW_ERROR, asset_id=contract.asset_id)
            store.set_state(contract.asset_id, AssetState.REVIEW_ERROR.value)
            ledger.append(run_id=args.run_id, event_type="observation.error", actor_role=args.actor_role,
                          payload={"candidate_sha256": args.candidate_sha256, "role": e.role,
                                   "reason": e.reason}, asset_id=contract.asset_id)
            return {"ok": False, "error": str(e), "role": e.role}
        store.save_observation(obs)
        observations[role] = {"reviewer_session_id": obs.reviewer_session_id}

    transition(current, AssetState.JUDGING, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, AssetState.JUDGING.value)
    ledger.append(run_id=args.run_id, event_type="observation.completed", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "observations": observations},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "observations": observations}


def cmd_observe_prepare(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 23: real automation for this project always runs inside a
    live, already-authenticated Cowork agent session -- so instead of
    `mediactl observe` shelling out to a separate Claude Code CLI process
    (its own, separate login `mediactl` could never share with the
    orchestrating session), the orchestrating agent can now perform the
    actual model call itself, via its own Task/Agent tool, using exactly
    the system prompt/instruction/image path this command returns.

    Commit 24: that "image path" is no longer a path inside the real
    quarantine store. This command now builds a purpose-built, single-use
    reviewer scratch directory (containment.create_scratch) containing only
    a COPY of the candidate bytes plus the instructions, opens containment
    tracking against it (a pre-review snapshot of every protected root,
    excluding that scratch dir), and returns the scratch copy's path as
    `image_path` instead -- the reviewer subagent never receives a path
    that resolves inside nookguard_store/quarantine, the real site source
    tree, or any evidence directory. This command still performs and writes
    NOTHING to any of the protected roots themselves (only the new,
    dedicated scratch dir) -- safe to call repeatedly. Same OBSERVING
    precondition `mediactl observe` has always had."""
    root = Path(args.store_root)
    store = _store(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
        candidate_path = store.candidate_path(args.candidate_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.OBSERVING:
        return {"ok": False, "error": f"Illegal state {current.value} for observe-prepare "
                                       "(asset must be in observing state, set by mediactl review-pack-build)"}
    if args.role not in OBSERVER_ROLES:
        return {"ok": False, "error": f"Unknown --role '{args.role}', expected one of {OBSERVER_ROLES}"}

    pack = build_review_pack(args.candidate_sha256, str(candidate_path), args.role)
    prompt = build_observer_prompt(pack)
    instructions_text = prompt["system_prompt"] + "\n\n---\n\n" + prompt["instruction"]
    scratch_dir, containment_id = _open_review_containment(
        args, root, f"observe-{args.role}-{args.candidate_sha256[:12]}", candidate_path, instructions_text,
    )
    scratch_image_path = scratch_dir / f"candidate{candidate_path.suffix}"
    return {"ok": True, "asset_id": contract.asset_id, "candidate_sha256": args.candidate_sha256,
            "role": prompt["role"], "system_prompt": prompt["system_prompt"],
            "instruction": prompt["instruction"], "image_path": str(scratch_image_path),
            "review_pack_sha256": pack.review_pack_sha256, "containment_id": containment_id,
            "reviewer_scratch_dir": str(scratch_dir)}


def cmd_observe_submit(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 23: takes a raw response the CALLER already obtained (via its
    own live Task/Agent subagent call using observe-prepare's exact
    system_prompt/instruction/image_path) and runs it through the identical
    parse/enrich/schema-validate/save logic `mediactl observe` has always
    used -- this command trusts the caller for the model's raw text only,
    never for the parsed/validated result. Transitions OBSERVING -> JUDGING
    only once BOTH roles have been submitted, mirroring `mediactl observe`'s
    original all-or-nothing behavior, just spread across two calls (in
    either order) instead of one loop.

    Commit 24: production-mode submission now REQUIRES --containment-id
    (from the matching observe-prepare call), --reviewer-session-id,
    --raw-response-sha256, and --review-pack-sha256 -- all independently
    re-verified against real values on this side (never trusted at face
    value), and the response is only ever accepted via --response-file
    (inline JSON on the command line was never supported by this command
    and remains unsupported, per requirement 6). Containment is closed
    (post-review snapshot + diff) before the response is parsed at all --
    a containment violation is a process failure (REVIEW_ERROR-equivalent),
    never a silently-accepted pass or fail."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
        candidate_path = store.candidate_path(args.candidate_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.OBSERVING:
        return {"ok": False, "error": f"Illegal state {current.value} for observe-submit "
                                       "(asset must be in observing state)"}
    if args.role not in OBSERVER_ROLES:
        return {"ok": False, "error": f"Unknown --role '{args.role}', expected one of {OBSERVER_ROLES}"}
    if not args.containment_id:
        return {"ok": False, "error": "missing --containment-id (from the matching observe-prepare call)",
                "reason": "missing_containment_id"}

    response_text = Path(args.response_file).read_text(encoding="utf-8")
    pack = build_review_pack(args.candidate_sha256, str(candidate_path), args.role)

    hash_error = _validate_submit_hashes(
        args=args, response_text=response_text, expected_review_pack_sha256=pack.review_pack_sha256,
    )
    if hash_error is not None:
        return hash_error

    scratch_dir = root / "reviewer_scratch" / args.containment_id
    try:
        _close_review_containment(args, root, args.containment_id)
    except ContainmentViolation as e:
        transition(current, AssetState.REVIEW_ERROR, asset_id=contract.asset_id)
        store.set_state(contract.asset_id, AssetState.REVIEW_ERROR.value)
        ledger.append(run_id=args.run_id, event_type="containment.violation", actor_role=args.actor_role,
                      payload={"candidate_sha256": args.candidate_sha256, "role": args.role,
                               "containment_id": args.containment_id, "violations": e.violations},
                      asset_id=contract.asset_id)
        cleanup_scratch(scratch_dir)
        return {"ok": False, "error": str(e), "reason": "containment_violation", "violations": e.violations}
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "reason": "containment_not_found"}

    diagnostics: dict[str, Any] = {}
    try:
        obs = finalize_observation(pack, response_text, session_id=args.reviewer_session_id,
                                    diagnostics_out=diagnostics)
    except ReviewSessionError as e:
        transition(current, AssetState.REVIEW_ERROR, asset_id=contract.asset_id)
        store.set_state(contract.asset_id, AssetState.REVIEW_ERROR.value)
        ledger.append(run_id=args.run_id, event_type="observation.error", actor_role=args.actor_role,
                      payload={"candidate_sha256": args.candidate_sha256, "role": e.role,
                               "reason": e.reason}, asset_id=contract.asset_id)
        _persist_review_evidence(root, "observe", f"{args.candidate_sha256}_{args.role}",
                                  raw_response=response_text, parsed_result=None, diagnostics=diagnostics)
        cleanup_scratch(scratch_dir)
        return {"ok": False, "error": str(e), "role": e.role}

    store.save_observation(obs)
    _persist_review_evidence(root, "observe", f"{args.candidate_sha256}_{args.role}",
                              raw_response=response_text, parsed_result=obs.model_dump(mode="json"),
                              diagnostics=diagnostics)
    cleanup_scratch(scratch_dir)
    ledger.append(run_id=args.run_id, event_type="observation.submitted", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "role": args.role,
                           "reviewer_session_id": obs.reviewer_session_id, "containment_id": args.containment_id,
                           "raw_response_sha256": args.raw_response_sha256},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)

    other_role = [r for r in OBSERVER_ROLES if r != args.role][0]
    try:
        store.load_observation(args.candidate_sha256, other_role)
    except FileNotFoundError:
        return {"ok": True, "asset_id": contract.asset_id, "role": args.role,
                "reviewer_session_id": obs.reviewer_session_id,
                "waiting_for": other_role, "state": current.value}

    # Both roles now have a saved observation -- complete, exactly like the
    # old atomic mediactl observe did at the end of its loop.
    transition(current, AssetState.JUDGING, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, AssetState.JUDGING.value)
    observations = {
        r: {"reviewer_session_id": store.load_observation(args.candidate_sha256, r).reviewer_session_id}
        for r in OBSERVER_ROLES
    }
    ledger.append(run_id=args.run_id, event_type="observation.completed", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "observations": observations},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "state": AssetState.JUDGING.value,
            "observations": observations}


def cmd_judge(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
        blind_obs = store.load_observation(args.candidate_sha256, "blind_a")
        adversarial_obs = store.load_observation(args.candidate_sha256, "adversarial_b")
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.JUDGING:
        return {"ok": False, "error": f"Illegal transition {current.value} -> judge "
                                       "(asset must be in judging state, set by mediactl observe)"}

    try:
        judgment = run_judge_session(contract, attempt.spec_sha256, blind_obs, adversarial_obs)
    except ReviewSessionError as e:
        transition(current, AssetState.REVIEW_ERROR, asset_id=contract.asset_id)
        store.set_state(contract.asset_id, AssetState.REVIEW_ERROR.value)
        ledger.append(run_id=args.run_id, event_type="judgment.error", actor_role=args.actor_role,
                      payload={"candidate_sha256": args.candidate_sha256, "reason": e.reason},
                      asset_id=contract.asset_id)
        return {"ok": False, "error": str(e), "role": e.role}
    store.save_judgment(judgment)

    result = aggregate(contract, judgment, blind_obs, adversarial_obs)
    transition(AssetState.JUDGING, result.state, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, result.state.value)

    asset_count = store.bump_adapter_asset_count(attempt.adapter_version)
    queued = should_queue_for_owner(contract.risk_tier, result.state,
                                     assets_seen_for_adapter=asset_count)
    if queued:
        OwnerQueue(store.owner_queue_path).enqueue(
            contract.asset_id, args.candidate_sha256, result.reasons,
            contract.risk_tier.value, result.state.value,
        )

    ledger.append(run_id=args.run_id, event_type="judgment.completed", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "result": result.state.value,
                           "reasons": result.reasons, "queued_for_owner": queued},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "result": result.state.value,
            "reasons": result.reasons, "queued_for_owner": queued}


def cmd_judge_prepare(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 23: the judge-side counterpart to observe-prepare. Returns the
    real system prompt and requirement/observation payload a live
    orchestrating agent needs to perform the judge session itself (via its
    own Task/Agent tool) -- writes nothing but the new dedicated scratch dir
    (Commit 24, same pattern as observe-prepare) -- safe to call repeatedly.
    Same JUDGING precondition `mediactl judge` has always had (both
    observations must already be saved, via observe-submit or the atomic
    observe). The judge never sees an image (Appendix D boundary,
    unaffected by containment) -- its scratch dir holds only the system
    prompt + payload as instructions.txt, no candidate copy."""
    root = Path(args.store_root)
    store = _store(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
        blind_obs = store.load_observation(args.candidate_sha256, "blind_a")
        adversarial_obs = store.load_observation(args.candidate_sha256, "adversarial_b")
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.JUDGING:
        return {"ok": False, "error": f"Illegal state {current.value} for judge-prepare "
                                       "(asset must be in judging state, set by mediactl observe/observe-submit)"}

    prompt = build_judge_prompt(contract, blind_obs, adversarial_obs)
    payload_json = json.dumps(prompt["payload"], indent=2)
    review_pack_sha256 = sha256_canonical_json(prompt["payload"])
    instructions_text = prompt["system_prompt"] + "\n\n---\n\n" + payload_json
    _scratch_dir, containment_id = _open_review_containment(
        args, root, f"judge-{args.candidate_sha256[:12]}", None, instructions_text,
    )
    return {"ok": True, "asset_id": contract.asset_id, "candidate_sha256": args.candidate_sha256,
            "system_prompt": prompt["system_prompt"], "payload_json": payload_json,
            "review_pack_sha256": review_pack_sha256, "containment_id": containment_id}


def cmd_judge_submit(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 23: takes a raw response the CALLER already obtained (via its
    own live Task/Agent subagent call using judge-prepare's exact
    system_prompt/payload_json) and runs it through the identical parse/
    enrich/schema-validate/save/aggregate/enqueue logic `mediactl judge`
    has always used.

    Commit 24: same custody requirements as observe-submit --
    --containment-id, --reviewer-session-id, --raw-response-sha256, and
    --review-pack-sha256 (a hash of the exact requirements/forbidden-
    objects/observations payload the judge was shown, matching what
    judge-prepare returned) are all required and independently
    re-verified. Containment is closed before the response is trusted."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
        blind_obs = store.load_observation(args.candidate_sha256, "blind_a")
        adversarial_obs = store.load_observation(args.candidate_sha256, "adversarial_b")
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.JUDGING:
        return {"ok": False, "error": f"Illegal state {current.value} for judge-submit "
                                       "(asset must be in judging state)"}
    if not args.containment_id:
        return {"ok": False, "error": "missing --containment-id (from the matching judge-prepare call)",
                "reason": "missing_containment_id"}

    response_text = Path(args.response_file).read_text(encoding="utf-8")
    prompt = build_judge_prompt(contract, blind_obs, adversarial_obs)
    real_review_pack_sha256 = sha256_canonical_json(prompt["payload"])

    hash_error = _validate_submit_hashes(
        args=args, response_text=response_text, expected_review_pack_sha256=real_review_pack_sha256,
    )
    if hash_error is not None:
        return hash_error

    scratch_dir = root / "reviewer_scratch" / args.containment_id
    try:
        _close_review_containment(args, root, args.containment_id)
    except ContainmentViolation as e:
        transition(current, AssetState.REVIEW_ERROR, asset_id=contract.asset_id)
        store.set_state(contract.asset_id, AssetState.REVIEW_ERROR.value)
        ledger.append(run_id=args.run_id, event_type="containment.violation", actor_role=args.actor_role,
                      payload={"candidate_sha256": args.candidate_sha256, "role": "judge",
                               "containment_id": args.containment_id, "violations": e.violations},
                      asset_id=contract.asset_id)
        cleanup_scratch(scratch_dir)
        return {"ok": False, "error": str(e), "reason": "containment_violation", "violations": e.violations}
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "reason": "containment_not_found"}

    diagnostics: dict[str, Any] = {}
    try:
        judgment = finalize_judgment(blind_obs, attempt.spec_sha256, prompt["payload"], response_text,
                                      session_id=args.reviewer_session_id, diagnostics_out=diagnostics)
    except ReviewSessionError as e:
        transition(current, AssetState.REVIEW_ERROR, asset_id=contract.asset_id)
        store.set_state(contract.asset_id, AssetState.REVIEW_ERROR.value)
        ledger.append(run_id=args.run_id, event_type="judgment.error", actor_role=args.actor_role,
                      payload={"candidate_sha256": args.candidate_sha256, "reason": e.reason},
                      asset_id=contract.asset_id)
        _persist_review_evidence(root, "judge", args.candidate_sha256,
                                  raw_response=response_text, parsed_result=None, diagnostics=diagnostics)
        cleanup_scratch(scratch_dir)
        return {"ok": False, "error": str(e), "role": e.role}
    store.save_judgment(judgment)
    _persist_review_evidence(root, "judge", args.candidate_sha256,
                              raw_response=response_text, parsed_result=judgment.model_dump(mode="json"),
                              diagnostics=diagnostics)
    cleanup_scratch(scratch_dir)

    result = aggregate(contract, judgment, blind_obs, adversarial_obs)
    transition(AssetState.JUDGING, result.state, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, result.state.value)

    asset_count = store.bump_adapter_asset_count(attempt.adapter_version)
    queued = should_queue_for_owner(contract.risk_tier, result.state,
                                     assets_seen_for_adapter=asset_count)
    if queued:
        OwnerQueue(store.owner_queue_path).enqueue(
            contract.asset_id, args.candidate_sha256, result.reasons,
            contract.risk_tier.value, result.state.value,
        )

    ledger.append(run_id=args.run_id, event_type="judgment.completed", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "result": result.state.value,
                           "reasons": result.reasons, "queued_for_owner": queued,
                           "containment_id": args.containment_id, "raw_response_sha256": args.raw_response_sha256},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "result": result.state.value,
            "reasons": result.reasons, "queued_for_owner": queued}


MAX_REVIEW_RETRIES = 3


def _review_error_event_count(ledger: Ledger, asset_id: str, candidate_sha256: str) -> int:
    """Counts every historical review-process-failure event for this exact
    (asset_id, candidate_sha256) pair -- observation.error and
    judgment.error both count, and nothing is ever removed from the ledger,
    so this is a true, tamper-evident count of every past failed attempt at
    reviewing this specific candidate, not a mutable counter that could be
    reset or lost."""
    count = 0
    for event in ledger.for_asset(asset_id):
        if event.event_type in ("observation.error", "judgment.error"):
            if event.payload.get("candidate_sha256") == candidate_sha256:
                count += 1
    return count


def _last_review_error_candidate(ledger: Ledger, asset_id: str) -> Optional[str]:
    """The candidate_sha256 named in the MOST RECENT review-process-failure
    event for this asset -- used to confirm a review-retry request is for
    the exact same candidate that actually failed, not a different (newer or
    older) one that happens to share the asset_id."""
    last: Optional[str] = None
    for event in ledger.for_asset(asset_id):
        if event.event_type in ("observation.error", "judgment.error"):
            last = event.payload.get("candidate_sha256")
    return last


def cmd_review_retry(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 19, requirement 8: REVIEW_ERROR -> REVIEW_PENDING -> OBSERVING
    recovery, permitted ONLY for the exact same, unchanged candidate hash
    that actually failed review, and ONLY within a bounded retry count. This
    is the only place in NookGuard allowed to walk the REVIEW_ERROR ->
    REVIEW_PENDING edge that state_machine.py's TRANSITIONS table makes
    legal -- the table only proves the edge exists, this function proves
    it's earned. After this returns ok:true the asset is sitting in
    OBSERVING exactly as if `review-pack-build` had just run; the existing,
    unmodified `observe` command resumes review from there with no other
    wiring needed, because it always builds review packs fresh from the
    candidate file itself on every call."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.REVIEW_ERROR:
        return {"ok": False, "error": f"Illegal transition {current.value} -> review-retry "
                                       "(asset must be in review_error state)"}

    last_failed_candidate = _last_review_error_candidate(ledger, contract.asset_id)
    if last_failed_candidate is not None and last_failed_candidate != args.candidate_sha256:
        return {"ok": False, "error": "changed_candidate: the candidate that actually failed "
                                       f"review was {last_failed_candidate}, not "
                                       f"{args.candidate_sha256} -- review-retry only recovers "
                                       "the exact, unchanged candidate that failed; a different "
                                       "candidate requires the normal review-pack-build/observe "
                                       "path, not a retry",
                "reason": "changed_candidate"}

    retry_count = _review_error_event_count(ledger, contract.asset_id, args.candidate_sha256)
    if retry_count >= MAX_REVIEW_RETRIES:
        return {"ok": False, "error": f"retry_exhausted: this candidate has already failed review "
                                       f"{retry_count} time(s), at or beyond the bound of "
                                       f"{MAX_REVIEW_RETRIES} -- a new generation attempt is "
                                       "required, this state is no longer recoverable in place",
                "reason": "retry_exhausted", "retry_count": retry_count}

    transition(AssetState.REVIEW_ERROR, AssetState.REVIEW_PENDING, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, AssetState.REVIEW_PENDING.value)
    ledger.append(run_id=args.run_id, event_type="review.retry_approved", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "prior_failure_count": retry_count,
                           "retries_remaining": MAX_REVIEW_RETRIES - retry_count - 1},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)

    transition(AssetState.REVIEW_PENDING, AssetState.OBSERVING, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, AssetState.OBSERVING.value)
    ledger.append(run_id=args.run_id, event_type="review.retry_resumed", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)

    return {"ok": True, "asset_id": contract.asset_id, "state": AssetState.OBSERVING.value,
            "prior_failure_count": retry_count, "retries_remaining": MAX_REVIEW_RETRIES - retry_count - 1}


def cmd_auth_check(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 19, requirement 7: a real, minimal Claude Code CLI smoke test
    -- must run under the same Windows identity and environment the
    scheduled task runs as, and must pass before generation begins (see
    cmd_generate's auth-check gate above). Delegates entirely to
    cli_reviewer.check_claude_cli_auth, which does the real subprocess call
    -- this command is just the CLI-shaped wrapper around it."""
    result = check_claude_cli_auth()
    return {"ok": result["authenticated"], **result}


def cmd_media_audit(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 21, requirements 1-2: the real "repository validation" gate.
    Delegates entirely to public_media_guard.audit_public_media() -- every
    real file currently under the published media directories is checked
    against the committed baseline (pre-existing, untouched legacy content
    is fine) and the union of every NookGuard release manifest across the
    given store root(s) (a real, approved release is fine). Anything else
    -- new or modified, not approved -- is reported by name under
    `unapproved`, and `ok` is false. This is also the exact check
    `cmd_deploy` below runs before it will do anything real.

    Uses `--site-root`, NOT `--project-root` -- public/winnie etc. live
    inside `site/`, a different real directory than `--project-root`'s
    default (the outer business-project root where `brand-assets/`
    lives). See public_media_guard.py's DEFAULT_SITE_ROOT comment for the
    real, confirmed-on-disk reason this distinction exists.

    `--store-root` is ALWAYS included in the approved-hash search (its
    docstring on the `--store-root-extra` argument below promises exactly
    this) -- a real bug caught by this command's own CLI-level test
    (test_media_audit_cli_approves_file_released_through_real_store_root):
    the first version of this function only included `--store-root` when
    `--store-root-extra` was ALSO given, silently dropping the primary
    store root whenever a caller passed just `--store-root` on its own,
    which is the normal, single-store case."""
    site_root = Path(args.site_root)
    store_roots = [Path(args.store_root)]
    if args.store_root_extra:
        store_roots += [Path(r) for r in args.store_root_extra]
    report = audit_public_media(site_root, store_roots=store_roots)
    return report


def cmd_write_path_audit(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 21, requirement 5: enumerates every real code path in this
    repository (scope documented in write_path_audit.py's own docstring)
    that looks capable of writing to a published media path or invoking a
    deployment. Purely additive/enumerative -- see that module's docstring
    for why `ok` isn't a meaningful concept here the way it is for
    media-audit; a real "media_write" finding is worth Maurice's own
    review, not an automatic block, since a false positive (e.g. a
    legitimate test fixture) is a real possibility a static text search
    can't rule out on its own. Uses `--site-root`, same reason as
    cmd_media_audit above."""
    report = run_write_path_audit(Path(args.site_root))
    return {"ok": True, **report_to_dict(report)}


def cmd_deploy(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 21, requirements 2/6/8: the controlled production-deployment
    command. Refuses to run past either real gate:
    1. public_media_guard.audit_public_media() must be clean -- an
       unapproved public media file must never reach a real deployment,
       matching requirement 2's 'enforce this... in the production
       deployment command.'
    2. check_cloudflare_credentials() must report real, available
       credentials -- see deploy.py's own module docstring for why this
       command does not (and, from this environment, cannot) verify or
       perform requirement 7's manual Cloudflare-dashboard step (disabling
       automatic deploy-on-push) itself; refusing to run without real
       credentials is the concrete guard against ever becoming a second,
       uncoordinated deploy path alongside a still-active GitHub
       auto-deploy.
    Only if both pass does this attempt a real `wrangler pages deploy`
    call and return its real deployment_id/deployment_url (requirement 8)
    -- never a fabricated one. Uses `--site-root`, same reason as
    cmd_media_audit above, and the same `--store-root`-is-always-included
    convention as cmd_media_audit's fix above -- the deploy gate must see
    exactly the same approved-hash set `mediactl media-audit` reports, not
    a silently narrower one."""
    site_root = Path(args.site_root)
    audit = audit_public_media(site_root, store_roots=[Path(args.store_root)])
    if not audit["ok"]:
        return {"ok": False, "reason": "unapproved_public_media", "media_audit": audit,
                "error": f"{audit['unapproved_count']} public media file(s) are not approved by any "
                         "NookGuard release manifest or the committed baseline -- refusing to deploy. "
                         "Run `mediactl media-audit` for the full list."}

    cred_check = check_cloudflare_credentials()
    if not cred_check["available"]:
        return {"ok": False, "reason": "cloudflare_credentials_unavailable", "credential_check": cred_check,
                "error": "Cloudflare credentials are not available -- refusing to deploy. "
                         + cred_check["instructions"]}

    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = site_root / dist_dir

    try:
        deploy_result = run_wrangler_deploy(
            dist_dir=str(dist_dir), project_name=args.project_name, env_name=args.env,
        )
    except WranglerDeployError as e:
        return {"ok": False, "reason": e.reason, "error": str(e)}

    return {"ok": True, "media_audit": audit, **deploy_result}


def cmd_integrate(args: argparse.Namespace) -> dict[str, Any]:
    """SEMANTIC_PASS/OWNER_APPROVED -> INTEGRATED (Commit 10). NookGuard does
    not write into a page's markdown itself (H006: generator/reviewer never
    writes files directly) -- wiring an approved candidate into a real page's
    frontmatter/body stays the existing, separate site workflow. This command
    only records that integration happened, so preview-capture has a real,
    confirmed page URL to screenshot rather than being told to trust a guess."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    try:
        transition(current, AssetState.INTEGRATED, asset_id=contract.asset_id)
    except InvalidTransitionError as e:
        return {"ok": False, "error": str(e)}
    store.set_state(contract.asset_id, AssetState.INTEGRATED.value)

    ledger.append(run_id=args.run_id, event_type="asset.integrated", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "page_url": args.page_url},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "page_url": args.page_url}


def cmd_preview_capture(args: argparse.Namespace) -> dict[str, Any]:
    """INTEGRATED -> PREVIEWED. Real Playwright screenshots of every
    viewport in preview.VIEWPORTS, combined into one contact sheet image.
    Broken-image/console-error/failed-request facts are captured here and
    persisted for preview-review's aggregation step -- they are deterministic
    and code-owned, never re-derived from the reviewer's prose."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    try:
        transition(current, AssetState.PREVIEWED, asset_id=contract.asset_id)
    except InvalidTransitionError as e:
        return {"ok": False, "error": str(e)}

    from .contact_sheet import build_contact_sheet
    from .preview import capture_all_viewports

    output_dir = store.preview_dir / args.candidate_sha256
    reports_by_viewport = capture_all_viewports(args.page_url, output_dir, args.candidate_sha256)
    ordered_reports = list(reports_by_viewport.values())
    contact_sheet_path = build_contact_sheet(
        [r.screenshot_path for r in ordered_reports],
        output_dir / "contact_sheet.png",
        labels=[r.viewport_name for r in ordered_reports],
    )

    store.save_preview_capture(args.candidate_sha256, args.page_url, contact_sheet_path, ordered_reports)
    store.set_state(contract.asset_id, AssetState.PREVIEWED.value)

    ledger.append(run_id=args.run_id, event_type="preview.captured", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "page_url": args.page_url,
                           "viewports": list(reports_by_viewport.keys()),
                           "any_broken_images": any(r.broken_images for r in ordered_reports),
                           "any_console_errors": any(r.console_errors for r in ordered_reports),
                           "any_failed_requests": any(r.failed_requests for r in ordered_reports)},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "page_url": args.page_url,
            "viewports": list(reports_by_viewport.keys()), "contact_sheet_path": contact_sheet_path}


def cmd_preview_review(args: argparse.Namespace) -> dict[str, Any]:
    """PREVIEWED -> {PREVIEW_REVIEW_PASS, PREVIEW_REVIEW_FAIL, REVIEW_ERROR}.
    Runs the page-reviewer session against the contact sheet built by
    preview-capture, then hands both that result and the real capture
    reports to preview_aggregator.aggregate_preview -- code, not the model,
    decides the outcome."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.PREVIEWED:
        return {"ok": False, "error": f"Illegal transition {current.value} -> preview-review "
                                       "(asset must be in previewed state, set by mediactl preview-capture)"}

    try:
        capture = store.load_preview_capture(args.candidate_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    capture_reports = [PageCaptureReport(**r) for r in capture["reports"]]
    viewports_captured = [r.viewport_name for r in capture_reports]

    try:
        review = run_page_review_session(capture["contact_sheet_path"], capture["page_url"], viewports_captured)
    except ReviewSessionError as e:
        transition(current, AssetState.REVIEW_ERROR, asset_id=contract.asset_id)
        store.set_state(contract.asset_id, AssetState.REVIEW_ERROR.value)
        ledger.append(run_id=args.run_id, event_type="preview_review.error", actor_role=args.actor_role,
                      payload={"candidate_sha256": args.candidate_sha256, "reason": e.reason},
                      asset_id=contract.asset_id)
        return {"ok": False, "error": str(e), "role": e.role}
    store.save_page_review(args.candidate_sha256, review)

    result = aggregate_preview(capture_reports, review)
    transition(current, result.state, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, result.state.value)

    ledger.append(run_id=args.run_id, event_type="preview_review.completed", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "result": result.state.value,
                           "reasons": result.reasons},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "result": result.state.value, "reasons": result.reasons}


def cmd_preview_review_prepare(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 23: the preview-reviewer counterpart to observe-prepare.
    Returns the real system prompt, instruction, and contact-sheet path a
    live orchestrating agent needs to perform the page-review session
    itself.

    Commit 24: the "contact-sheet path" is now a COPY inside a dedicated
    reviewer scratch directory, same containment pattern as observe-prepare
    -- and per requirement 4, this scratch directory is also the ONLY place
    the reviewer is permitted to create crops (the instructions file says
    so explicitly, and containment's post-review diff enforces it: any
    crop written outside the scratch dir invalidates the review). Writes
    only the new scratch dir -- safe to call repeatedly. Same PREVIEWED
    precondition `mediactl preview-review` has always had."""
    root = Path(args.store_root)
    store = _store(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.PREVIEWED:
        return {"ok": False, "error": f"Illegal state {current.value} for preview-review-prepare "
                                       "(asset must be in previewed state, set by mediactl preview-capture)"}

    try:
        capture = store.load_preview_capture(args.candidate_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    capture_reports = [PageCaptureReport(**r) for r in capture["reports"]]
    viewports_captured = [r.viewport_name for r in capture_reports]
    prompt = build_page_review_prompt(capture["contact_sheet_path"], capture["page_url"], viewports_captured)
    contact_sheet_path = Path(prompt["image_path"])
    contact_sheet_sha256 = sha256_bytes(contact_sheet_path.read_bytes())

    instructions_text = (
        prompt["system_prompt"] + "\n\n---\n\n" + prompt["instruction"]
        + "\n\nIf you need to inspect a region more closely and choose to create a cropped "
          "image, you may create it ONLY inside this same directory as the contact sheet you "
          "were given -- creating any file outside this directory invalidates your review."
    )
    scratch_dir, containment_id = _open_review_containment(
        args, root, f"preview-review-{args.candidate_sha256[:12]}", contact_sheet_path, instructions_text,
    )
    scratch_image_path = scratch_dir / f"candidate{contact_sheet_path.suffix}"
    return {"ok": True, "asset_id": contract.asset_id, "system_prompt": prompt["system_prompt"],
            "instruction": prompt["instruction"], "image_path": str(scratch_image_path),
            "page_url": prompt["page_url"], "viewports_captured": viewports_captured,
            "contact_sheet_sha256": contact_sheet_sha256, "containment_id": containment_id,
            "reviewer_scratch_dir": str(scratch_dir)}


def cmd_preview_review_submit(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 23: takes a raw response the CALLER already obtained (via its
    own live Task/Agent subagent call using preview-review-prepare's exact
    system_prompt/instruction/image_path) and runs it through the identical
    parse/enrich/schema-validate/save/aggregate logic `mediactl preview-
    review` has always used.

    Commit 24: same custody requirements as observe-submit --
    --containment-id, --reviewer-session-id, --raw-response-sha256, and
    --contact-sheet-sha256 (the real contact sheet's own sha256, matching
    what preview-review-prepare returned) are all required and
    independently re-verified. Containment is closed (which also validates
    that any crop the reviewer created landed inside its scratch dir, per
    requirement 4) before the response is trusted."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.PREVIEWED:
        return {"ok": False, "error": f"Illegal state {current.value} for preview-review-submit "
                                       "(asset must be in previewed state)"}
    if not args.containment_id:
        return {"ok": False, "error": "missing --containment-id (from the matching "
                                       "preview-review-prepare call)", "reason": "missing_containment_id"}

    try:
        capture = store.load_preview_capture(args.candidate_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    capture_reports = [PageCaptureReport(**r) for r in capture["reports"]]
    viewports_captured = [r.viewport_name for r in capture_reports]
    response_text = Path(args.response_file).read_text(encoding="utf-8")
    real_contact_sheet_sha256 = sha256_bytes(Path(capture["contact_sheet_path"]).read_bytes())

    hash_error = _validate_submit_hashes(
        args=args, response_text=response_text, expected_contact_sheet_sha256=real_contact_sheet_sha256,
    )
    if hash_error is not None:
        return hash_error

    scratch_dir = root / "reviewer_scratch" / args.containment_id
    try:
        _close_review_containment(args, root, args.containment_id)
    except ContainmentViolation as e:
        transition(current, AssetState.REVIEW_ERROR, asset_id=contract.asset_id)
        store.set_state(contract.asset_id, AssetState.REVIEW_ERROR.value)
        ledger.append(run_id=args.run_id, event_type="containment.violation", actor_role=args.actor_role,
                      payload={"candidate_sha256": args.candidate_sha256, "role": "preview_reviewer",
                               "containment_id": args.containment_id, "violations": e.violations},
                      asset_id=contract.asset_id)
        cleanup_scratch(scratch_dir)
        return {"ok": False, "error": str(e), "reason": "containment_violation", "violations": e.violations}
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e), "reason": "containment_not_found"}

    diagnostics: dict[str, Any] = {}
    try:
        review = finalize_page_review(capture["page_url"], viewports_captured,
                                       capture["contact_sheet_path"], response_text,
                                       session_id=args.reviewer_session_id, diagnostics_out=diagnostics)
    except ReviewSessionError as e:
        transition(current, AssetState.REVIEW_ERROR, asset_id=contract.asset_id)
        store.set_state(contract.asset_id, AssetState.REVIEW_ERROR.value)
        ledger.append(run_id=args.run_id, event_type="preview_review.error", actor_role=args.actor_role,
                      payload={"candidate_sha256": args.candidate_sha256, "reason": e.reason},
                      asset_id=contract.asset_id)
        _persist_review_evidence(root, "preview_review", args.candidate_sha256,
                                  raw_response=response_text, parsed_result=None, diagnostics=diagnostics)
        cleanup_scratch(scratch_dir)
        return {"ok": False, "error": str(e), "role": e.role}
    store.save_page_review(args.candidate_sha256, review)
    _persist_review_evidence(root, "preview_review", args.candidate_sha256,
                              raw_response=response_text, parsed_result=review.model_dump(mode="json"),
                              diagnostics=diagnostics)
    cleanup_scratch(scratch_dir)

    result = aggregate_preview(capture_reports, review)
    transition(current, result.state, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, result.state.value)

    ledger.append(run_id=args.run_id, event_type="preview_review.completed", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "result": result.state.value,
                           "reasons": result.reasons, "containment_id": args.containment_id,
                           "raw_response_sha256": args.raw_response_sha256},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "result": result.state.value, "reasons": result.reasons}


def cmd_release(args: argparse.Namespace) -> dict[str, Any]:
    """PREVIEW_REVIEW_PASS/OWNER_APPROVED -> RELEASED (Commit 12). Copies
    the candidate's real bytes to a content-hashed public path (section
    27's "no filename reuse... public filename is assigned only at
    release") and records a ReleaseManifestEntry -- the durable fact
    `production-verify` checks reality against."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    try:
        transition(current, AssetState.RELEASED, asset_id=contract.asset_id)
    except InvalidTransitionError as e:
        return {"ok": False, "error": str(e)}

    candidate_path = store.candidate_path(args.candidate_sha256)
    try:
        public_path, public_url = publish_candidate(
            candidate_path, args.candidate_sha256, Path(args.public_dir),
            args.public_url_prefix, args.name_hint,
        )
    except ReleaseIntegrityError as e:
        return {"ok": False, "error": str(e)}

    entry = ReleaseManifestEntry(
        release_id=str(uuid.uuid4()), run_id=args.run_id or "unspecified", asset_id=contract.asset_id,
        candidate_sha256=args.candidate_sha256, public_path=str(public_path), public_url=public_url,
        site_commit=args.site_commit,
    )
    store.save_release_manifest(entry)
    store.set_state(contract.asset_id, AssetState.RELEASED.value)

    ledger.append(run_id=args.run_id, event_type="asset.released", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "public_url": public_url,
                           "release_manifest_sha256": entry.release_manifest_sha256},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "public_path": str(public_path),
            "public_url": public_url, "release_manifest_sha256": entry.release_manifest_sha256}


def cmd_production_verify(args: argparse.Namespace) -> dict[str, Any]:
    """RELEASED -> {PROD_VERIFIED, PROD_MISMATCH} (Commit 12). Checks the
    real released bytes against either a real `astro build` output
    (--dist-root) or a live URL (--live-url) -- never trusts the manifest
    entry alone as proof of what's actually being served."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    try:
        attempt = store.load_attempt(args.candidate_sha256)
        contract = store.load_spec(attempt.spec_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    current = AssetState(store.get_state(contract.asset_id))
    if current != AssetState.RELEASED:
        return {"ok": False, "error": f"Illegal transition {current.value} -> production-verify "
                                       "(asset must be in released state, set by mediactl release)"}

    try:
        entry = store.load_release_manifest(args.candidate_sha256)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}

    verify_kwargs: dict[str, Any] = {}
    if args.dist_root:
        verify_kwargs["dist_root"] = Path(args.dist_root)
        verify_kwargs["public_root"] = Path(args.public_root)
    if args.live_url:
        verify_kwargs["live_url"] = args.live_url

    result = verify_production(Path(entry.public_path), args.candidate_sha256, **verify_kwargs)
    transition(current, result.state, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, result.state.value)

    ledger.append(run_id=args.run_id, event_type="production_verify.completed", actor_role=args.actor_role,
                  payload={"candidate_sha256": args.candidate_sha256, "result": result.state.value,
                           "reason": result.reason},
                  asset_id=contract.asset_id, actor_session_id=args.session_id)
    return {"ok": True, "asset_id": contract.asset_id, "result": result.state.value, "reason": result.reason}


def cmd_regression_run(args: argparse.Namespace) -> dict[str, Any]:
    """Appendix A's "historical fixtures, expected labels": runs the full
    Appendix I regression corpus (10 named real-incident fixtures spanning
    aggregate(), off_the_clock_schema, and production_verifier) and returns
    a per-fixture pass/fail plus an overall verdict. `ok: false` on any
    regressed fixture -- via mediactl's own main(), that's a nonzero exit
    code, so this can gate CI exactly like content-lint already does."""
    base = Path(args.tmp_root) if args.tmp_root else Path(args.store_root) / "_regression_tmp"
    base.mkdir(parents=True, exist_ok=True)

    def tmp_dir_factory(name: str) -> Path:
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    report = run_regression_corpus(tmp_dir_factory)
    return {
        "ok": report.all_passed,
        "results": [
            {"fixture_id": r.fixture_id, "description": r.description, "category": r.category,
             "expected_state": r.expected_state, "actual_state": r.actual_state, "passed": r.passed,
             "detail": r.detail}
            for r in report.results
        ],
    }


def cmd_regression(args: argparse.Namespace) -> dict[str, Any]:
    """Commit 20, requirements 1/3/6: `mediactl regression --mode
    {deterministic,live-review}`. `deterministic` (default) delegates to
    the exact same `run_regression_corpus()` the pre-existing
    `regression-run` command (Commit 13, above) already uses -- no
    duplicated logic, no behavior change for existing callers of
    `regression-run`, which remains available unchanged. `live-review`
    calls `run_live_review_regression_corpus()` (regression_live.py): real
    observer/judge sessions against real image files on disk, never
    synthetic observations or judgments. Each mode's result is returned
    under its own `mode` field and its own real `ok`/results -- this
    command never blends the two or reports one's coverage as the other's;
    a caller wanting both must call this command twice, once per mode."""
    if args.mode == "deterministic":
        base = Path(args.tmp_root) if args.tmp_root else Path(args.store_root) / "_regression_tmp"
        base.mkdir(parents=True, exist_ok=True)

        def tmp_dir_factory(name: str) -> Path:
            d = base / name
            d.mkdir(parents=True, exist_ok=True)
            return d

        det_report = run_regression_corpus(tmp_dir_factory)
        return {
            "ok": det_report.all_passed, "mode": "deterministic",
            "results": [
                {"fixture_id": r.fixture_id, "description": r.description, "category": r.category,
                 "expected_state": r.expected_state, "actual_state": r.actual_state, "passed": r.passed,
                 "detail": r.detail}
                for r in det_report.results
            ],
        }

    if args.mode == "live-review":
        live_report = run_live_review_regression_corpus()
        return {
            "ok": live_report.all_passed, "mode": "live-review",
            "review_process_completed_count": live_report.review_process_completed_count,
            "fixture_count": len(live_report.results),
            "results": [
                {"fixture_id": r.fixture_id, "description": r.description, "category": r.category,
                 "expected_state": r.expected_state, "actual_state": r.actual_state, "passed": r.passed,
                 "detail": r.detail, "review_process_completed": r.review_process_completed}
                for r in live_report.results
            ],
        }

    return {"ok": False, "error": f"unknown --mode '{args.mode}', expected 'deterministic' or 'live-review'"}


_CANARY_ASSET_ID = "canary-known-clean"


def _canary_contract_dict() -> dict[str, Any]:
    return {
        "asset_id": _CANARY_ASSET_ID, "project_id": "nest-and-nook", "page_id": "canary",
        "slot_id": "canary", "media_type": "image", "risk_tier": "tier_0_decorative",
        "page_type_contract_version": "1", "source_excerpt": "canary release payload",
        "source_excerpt_sha256": "canary", "canonical_reference_bundle_sha256": "canary",
        "subject": "Winnie", "action": "holding a tape measure", "scene": "office",
        "planner_session_id": "canary-planner", "plan_evaluator_session_id": "canary-evaluator",
        "requirements": [
            {"requirement_id": "r1", "type": "count", "statement": "exactly 1 tape measure visible",
             "critical": True}
        ],
        "forbidden_objects": [],
    }


def cmd_canary_run(args: argparse.Namespace) -> dict[str, Any]:
    """Appendix A's "canary release": runs the FULL pipeline end-to-end --
    spec-lock through production-verify -- for a fixed, version-controlled
    "known clean" payload (the same fixture as the regression corpus's
    control case). If this stops passing, something broke in the
    pipeline's own wiring, independent of any real content.

    Every step below calls `run_cli()`, the exact same entry point a
    manual `mediactl` invocation or a real CI job uses -- a canary pass is
    genuine evidence the real commands still chain together correctly, not
    a separate/fake code path built just for this check."""
    steps: list[dict[str, Any]] = []

    def do(argv: list[str]) -> dict[str, Any]:
        result = run_cli(argv)
        steps.append({"command": argv[0], "ok": result.get("ok", False)})
        return result

    common = ["--store-root", args.store_root, "--run-id", args.run_id or "canary",
              "--actor-role", "canary", "--project-root", args.project_root]

    store_root = Path(args.store_root)
    store_root.mkdir(parents=True, exist_ok=True)
    contract_path = store_root / "_canary_contract.json"
    contract_path.write_text(json.dumps(_canary_contract_dict()), encoding="utf-8")

    spec = do(["spec-lock", *common, "--contract", str(contract_path)])
    if not spec["ok"]:
        return {"ok": False, "error": "canary failed at spec-lock", "steps": steps, "detail": spec}

    prompt = do(["prompt-compile", *common, "--spec", spec["spec_sha256"]])
    if not prompt["ok"]:
        return {"ok": False, "error": "canary failed at prompt-compile", "steps": steps, "detail": prompt}

    gen = do(["generate", *common, "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"],
              "--adapter", "stub"])
    if not gen["ok"]:
        return {"ok": False, "error": "canary failed at generate", "steps": steps, "detail": gen}
    candidate_sha = gen["candidate_sha256"]

    reg = do(["register", *common, "--spec", spec["spec_sha256"], "--prompt", prompt["prompt_sha256"],
              "--candidate-sha256", candidate_sha, "--adapter-version", gen["adapter_version"],
              "--session-id", "canary-generator"])
    if not reg["ok"]:
        return {"ok": False, "error": "canary failed at register", "steps": steps, "detail": reg}

    val = do(["validate", *common, "--candidate-sha256", candidate_sha])
    if not val["ok"] or val.get("result") != "technical_pass":
        return {"ok": False, "error": "canary failed at validate", "steps": steps, "detail": val}

    pack = do(["review-pack-build", *common, "--candidate-sha256", candidate_sha])
    if not pack["ok"]:
        return {"ok": False, "error": "canary failed at review-pack-build", "steps": steps, "detail": pack}

    obs = do(["observe", *common, "--candidate-sha256", candidate_sha])
    if not obs["ok"]:
        return {"ok": False, "error": "canary failed at observe", "steps": steps, "detail": obs}

    judge = do(["judge", *common, "--candidate-sha256", candidate_sha])
    if not judge["ok"] or judge.get("result") != "semantic_pass":
        return {"ok": False, "error": "canary failed at judge", "steps": steps, "detail": judge}

    integ = do(["integrate", *common, "--candidate-sha256", candidate_sha])
    if not integ["ok"]:
        return {"ok": False, "error": "canary failed at integrate", "steps": steps, "detail": integ}

    page_url = args.canary_page_url
    if not page_url:
        page_path = store_root / "_canary_page.html"
        page_path.write_text("<html><body><h1>Canary page</h1></body></html>", encoding="utf-8")
        page_url = page_path.resolve().as_uri()

    cap = do(["preview-capture", *common, "--candidate-sha256", candidate_sha, "--page-url", page_url])
    if not cap["ok"]:
        return {"ok": False, "error": "canary failed at preview-capture", "steps": steps, "detail": cap}

    rev = do(["preview-review", *common, "--candidate-sha256", candidate_sha])
    if not rev["ok"] or rev.get("result") != "preview_review_pass":
        return {"ok": False, "error": "canary failed at preview-review", "steps": steps, "detail": rev}

    public_root = store_root / "_canary_public"
    public_dir = public_root / "winnie"
    rel = do(["release", *common, "--candidate-sha256", candidate_sha, "--public-dir", str(public_dir),
              "--public-url-prefix", "/winnie", "--name-hint", "canary"])
    if not rel["ok"]:
        return {"ok": False, "error": "canary failed at release", "steps": steps, "detail": rel}

    # Simulate a real `astro build` having copied the released file into
    # dist/ verbatim, so production-verify's real local-build code path
    # gets exercised without requiring an actual Astro build in this
    # smoke-test context.
    dist_root = store_root / "_canary_dist"
    released_file = Path(rel["public_path"])
    relative = released_file.resolve().relative_to(public_root.resolve())
    dist_target = dist_root / relative
    dist_target.parent.mkdir(parents=True, exist_ok=True)
    dist_target.write_bytes(released_file.read_bytes())

    verify = do(["production-verify", *common, "--candidate-sha256", candidate_sha,
                 "--public-root", str(public_root), "--dist-root", str(dist_root)])
    if not verify["ok"] or verify.get("result") != "prod_verified":
        return {"ok": False, "error": "canary failed at production-verify", "steps": steps, "detail": verify}

    return {"ok": True, "steps": steps, "candidate_sha256": candidate_sha,
            "release_manifest_sha256": rel["release_manifest_sha256"]}


def cmd_run_report(args: argparse.Namespace) -> dict[str, Any]:
    """Section 24, "Completion and Evidence Protocol": "Claude's final
    message is not the record of truth. NookGuard generates run-report.json,
    run-report.md, and a compact owner summary from ledger events." Builds
    all three from this run's real ledger events + each touched asset's
    real current store state, plus a freshly-executed regression corpus run
    (see run_report.default_regression_runner -- nothing about "still
    passing" is trusted from a prior narrated result). `ok` mirrors the
    boxed rule on the same page: only true when terminal_status is
    PROD_VERIFIED -- otherwise `blocking` says exactly what remains, same
    contract this command's own JSON already gives a caller either way."""
    root = Path(args.store_root)
    store, ledger = _store(root), _ledger(root)
    out_dir = Path(args.out_dir) if args.out_dir else root / "reports" / args.run_id
    result = write_run_report(
        store, ledger, args.run_id, out_dir,
        project_root=Path(args.project_root),
        production_deployment_id=args.production_deployment_id,
    )
    return {"ok": result["terminal_status"] == "PROD_VERIFIED", **result}


def _content_lint_one(file_path: Path) -> dict[str, Any]:
    try:
        report = lint_off_the_clock_file(str(file_path))
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "file": str(file_path), "error": str(e)}
    return {
        "ok": report.passed,
        "file": str(file_path),
        "category_ok": report.category_ok,
        "blocks": [{"block_type": b.block_type, "image_count": b.image_count,
                     "expected_count": b.expected_count, "passed": b.passed} for b in report.blocks],
        "legacy_pattern_findings": report.legacy_pattern_findings,
        "reasons": report.reasons,
    }


def cmd_content_lint(args: argparse.Namespace) -> dict[str, Any]:
    """Hook H009: 'Page adds legacy raw media component -> Fail content
    lint.' Standalone content check -- not part of the asset state machine
    (a page isn't a generated-media asset), so no store/transition involved,
    just a pass/fail report over real file(s) on disk. `--dir` batch mode
    exists so this can gate a real content build (Definition of Done: 'An
    Off the Clock page with the wrong strip count fails the content
    build') -- files with no recognized category are skipped (reported, not
    failed), since a directory of mixed content types (Guides, recipes)
    shouldn't fail this lint just for not being an Off the Clock page."""
    if args.dir:
        results = []
        for file_path in sorted(Path(args.dir).glob("*.md")):
            try:
                frontmatter_text, _ = split_frontmatter(file_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, ValueError) as e:
                results.append({"ok": False, "file": str(file_path), "error": str(e)})
                continue
            category = extract_category(frontmatter_text)
            if category not in OFF_THE_CLOCK_CATEGORIES:
                results.append({"ok": True, "file": str(file_path), "skipped": True,
                                 "reason": f"category '{category}' not in scope for this lint"})
                continue
            results.append(_content_lint_one(file_path))
        overall_ok = all(r["ok"] for r in results)
        return {"ok": overall_ok, "files_checked": len(results), "results": results}

    return _content_lint_one(Path(args.file))


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--store-root", default=str(DEFAULT_STORE_ROOT))
    p.add_argument("--run-id", default=None)
    p.add_argument("--actor-role", default="unspecified")
    p.add_argument("--session-id", default=None)
    p.add_argument("--project-root", default=str(DEFAULT_PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mediactl")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run-start"); _common(p); p.set_defaults(func=cmd_run_start)
    p = sub.add_parser("run-preflight"); _common(p); p.set_defaults(func=cmd_run_preflight)

    p = sub.add_parser("spec-lock"); _common(p)
    p.add_argument("--contract", required=True)
    p.set_defaults(func=cmd_spec_lock)

    p = sub.add_parser("prompt-compile"); _common(p)
    p.add_argument("--spec", required=True)
    p.set_defaults(func=cmd_prompt_compile)

    p = sub.add_parser("generate"); _common(p)
    p.add_argument("--spec", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--adapter", default="stub")
    # Commit 19: real (non-stub) generation refuses to run unless a real
    # auth-check passes first -- see cmd_generate's docstring, and its
    # Commit 23 correction: this flag is legitimate real-production usage
    # when the caller is a live orchestrating agent that will itself
    # perform observe-prepare/-submit and judge-prepare/-submit afterward
    # (Commit 23's subagent-driven review) -- NOT legitimate for a bare
    # unattended caller with no live agent able to complete review either
    # way.
    p.add_argument("--skip-auth-check", action="store_true", default=False)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("register"); _common(p)
    p.add_argument("--spec", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--candidate-sha256", required=True)
    p.add_argument("--adapter-version", required=True)
    p.add_argument("--model-revision", default="n/a")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("validate"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("review-pack-build"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.set_defaults(func=cmd_review_pack_build)

    p = sub.add_parser("observe"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.set_defaults(func=cmd_observe)

    # Commit 23: agent-native counterparts to observe/judge/preview-review
    # above -- the recommended path when a live Cowork agent (this one, or
    # a scheduled task) is orchestrating the run, since it removes the
    # separate Claude Code CLI login `observe`/`judge`/`preview-review`
    # need. `--role` is required on the observe- pair since each real call
    # covers exactly one observer role; the caller makes two calls (either
    # order) to cover both.
    p = sub.add_parser("observe-prepare"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    # Deliberately no argparse `choices=` here -- same reasoning as
    # cmd_regression's own --mode argument above: an invalid --role should
    # come back as this module's standard {"ok": false, "error": ...}
    # contract (cmd_observe_prepare/cmd_observe_submit's own graceful
    # `role not in OBSERVER_ROLES` check), not a raw argparse SystemExit.
    p.add_argument("--role", required=True)
    p.add_argument("--site-root", default=None,
                    help="Optional override for the site tree Commit 24 containment snapshots/diffs "
                         "against (defaults to the real site/ directory, public_media_guard."
                         "DEFAULT_SITE_ROOT). Exists so tests and dry runs can point containment at a "
                         "small fixture directory instead of hashing the entire real site tree on "
                         "every call -- production use should leave this unset.")
    p.set_defaults(func=cmd_observe_prepare)

    p = sub.add_parser("observe-submit"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    # Deliberately no argparse `choices=` here -- same reasoning as
    # cmd_regression's own --mode argument above: an invalid --role should
    # come back as this module's standard {"ok": false, "error": ...}
    # contract (cmd_observe_prepare/cmd_observe_submit's own graceful
    # `role not in OBSERVER_ROLES` check), not a raw argparse SystemExit.
    p.add_argument("--role", required=True)
    p.add_argument("--response-file", required=True,
                    help="Path to a file containing the raw model response text obtained via the "
                         "caller's own Task/Agent subagent call using observe-prepare's system_prompt.")
    p.add_argument("--containment-id", required=True,
                    help="The containment_id returned by observe-prepare. Custody chain: submit closes "
                         "this containment and rejects the review if anything outside the reviewer's "
                         "scratch directory changed (Commit 24 requirement 2).")
    p.add_argument("--reviewer-session-id", required=True,
                    help="Opaque identifier for the actual reviewer session/subagent invocation that "
                         "produced --response-file (Commit 24 requirement 5).")
    p.add_argument("--raw-response-sha256", required=True,
                    help="SHA-256 of the exact bytes in --response-file, computed by the caller before "
                         "submission. Must match a fresh hash of --response-file's contents or the "
                         "submission is rejected -- this is the check for tampering/substitution between "
                         "prepare and submit (Commit 24 requirement 5).")
    p.add_argument("--review-pack-sha256", required=True,
                    help="The review_pack_sha256 the caller was shown at observe-prepare time. Must "
                         "match the pack's real, freshly recomputed hash or the submission is rejected "
                         "(Commit 24 requirement 5).")
    p.add_argument("--site-root", default=None,
                    help="Must match the --site-root the matching observe-prepare call used (both "
                         "default to the real site/ directory when unset). See observe-prepare's own "
                         "--site-root help for why this override exists.")
    p.set_defaults(func=cmd_observe_submit)

    p = sub.add_parser("judge"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("judge-prepare"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.add_argument("--site-root", default=None,
                    help="Optional containment site-root override -- see observe-prepare's own "
                         "--site-root help.")
    p.set_defaults(func=cmd_judge_prepare)

    p = sub.add_parser("judge-submit"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.add_argument("--response-file", required=True,
                    help="Path to a file containing the raw model response text obtained via the "
                         "caller's own Task/Agent subagent call using judge-prepare's system_prompt.")
    p.add_argument("--containment-id", required=True,
                    help="The containment_id returned by judge-prepare. Custody chain: submit closes "
                         "this containment and rejects the review if anything outside the reviewer's "
                         "scratch directory changed (Commit 24 requirement 2).")
    p.add_argument("--reviewer-session-id", required=True,
                    help="Opaque identifier for the actual reviewer session/subagent invocation that "
                         "produced --response-file (Commit 24 requirement 5).")
    p.add_argument("--raw-response-sha256", required=True,
                    help="SHA-256 of the exact bytes in --response-file, computed by the caller before "
                         "submission. Must match a fresh hash of --response-file's contents or the "
                         "submission is rejected (Commit 24 requirement 5).")
    p.add_argument("--review-pack-sha256", required=True,
                    help="The review_pack_sha256 (sha256_canonical_json of the judge payload) the "
                         "caller was shown at judge-prepare time. Must match the freshly recomputed "
                         "hash of the real payload or the submission is rejected (Commit 24 "
                         "requirement 5).")
    p.add_argument("--site-root", default=None,
                    help="Must match the --site-root the matching judge-prepare call used -- see "
                         "observe-prepare's own --site-root help.")
    p.set_defaults(func=cmd_judge_submit)

    p = sub.add_parser("review-retry"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.set_defaults(func=cmd_review_retry)

    p = sub.add_parser("auth-check"); _common(p)
    p.set_defaults(func=cmd_auth_check)

    p = sub.add_parser("media-audit"); _common(p)
    # --site-root, NOT --project-root -- see cmd_media_audit's own
    # docstring and public_media_guard.py's DEFAULT_SITE_ROOT comment for
    # the real, confirmed-on-disk reason these are different directories.
    p.add_argument("--site-root", default=str(DEFAULT_SITE_ROOT))
    p.add_argument("--store-root-extra", action="append", default=None,
                    help="Additional NookGuard store root(s) whose release manifests also count as "
                         "approved (repeatable). The primary --store-root is always included.")
    p.set_defaults(func=cmd_media_audit)

    p = sub.add_parser("write-path-audit"); _common(p)
    p.add_argument("--site-root", default=str(DEFAULT_SITE_ROOT))
    p.set_defaults(func=cmd_write_path_audit)

    p = sub.add_parser("deploy"); _common(p)
    p.add_argument("--site-root", default=str(DEFAULT_SITE_ROOT))
    p.add_argument("--dist-dir", default="dist")
    p.add_argument("--project-name", default="nestandnook-site")
    p.add_argument("--env", default="production", choices=["production", "preview"])
    p.set_defaults(func=cmd_deploy)

    p = sub.add_parser("integrate"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.add_argument("--page-url", default=None)
    p.set_defaults(func=cmd_integrate)

    p = sub.add_parser("preview-capture"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.add_argument("--page-url", required=True)
    p.set_defaults(func=cmd_preview_capture)

    p = sub.add_parser("preview-review"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.set_defaults(func=cmd_preview_review)

    p = sub.add_parser("preview-review-prepare"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.add_argument("--site-root", default=None,
                    help="Optional containment site-root override -- see observe-prepare's own "
                         "--site-root help.")
    p.set_defaults(func=cmd_preview_review_prepare)

    p = sub.add_parser("preview-review-submit"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.add_argument("--response-file", required=True,
                    help="Path to a file containing the raw model response text obtained via the "
                         "caller's own Task/Agent subagent call using preview-review-prepare's system_prompt.")
    p.add_argument("--containment-id", required=True,
                    help="The containment_id returned by preview-review-prepare. Custody chain: submit "
                         "closes this containment and rejects the review if anything outside the "
                         "reviewer's scratch directory changed -- including any crop file created "
                         "outside that directory (Commit 24 requirements 2 and 4).")
    p.add_argument("--reviewer-session-id", required=True,
                    help="Opaque identifier for the actual reviewer session/subagent invocation that "
                         "produced --response-file (Commit 24 requirement 5).")
    p.add_argument("--raw-response-sha256", required=True,
                    help="SHA-256 of the exact bytes in --response-file, computed by the caller before "
                         "submission. Must match a fresh hash of --response-file's contents or the "
                         "submission is rejected (Commit 24 requirement 5).")
    p.add_argument("--contact-sheet-sha256", required=True,
                    help="SHA-256 of the contact sheet image the caller was shown at "
                         "preview-review-prepare time. Must match a fresh hash of the real contact "
                         "sheet file or the submission is rejected (Commit 24 requirement 5).")
    p.add_argument("--site-root", default=None,
                    help="Must match the --site-root the matching preview-review-prepare call used -- "
                         "see observe-prepare's own --site-root help.")
    p.set_defaults(func=cmd_preview_review_submit)

    p = sub.add_parser("release"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.add_argument("--public-dir", required=True)
    p.add_argument("--public-url-prefix", required=True)
    p.add_argument("--name-hint", required=True)
    p.add_argument("--site-commit", default=None)
    p.set_defaults(func=cmd_release)

    p = sub.add_parser("production-verify"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.add_argument("--public-root", default=None,
                    help="Site's public/ directory (parent of winnie/, cursors/, etc.) -- required "
                         "with --dist-root, not used with --live-url. NOT the same as release's "
                         "--public-dir, which is the specific leaf subdirectory a file was written into.")
    verify_group = p.add_mutually_exclusive_group(required=True)
    verify_group.add_argument("--dist-root")
    verify_group.add_argument("--live-url")
    p.set_defaults(func=cmd_production_verify)

    p = sub.add_parser("regression-run"); _common(p)
    p.add_argument("--tmp-root", default=None,
                    help="Real writable dir for the two filesystem-backed fixtures. Defaults to a "
                         "subdirectory under --store-root.")
    p.set_defaults(func=cmd_regression_run)

    p = sub.add_parser("regression"); _common(p)
    # Deliberately no argparse `choices=` here -- an invalid --mode should
    # come back as this module's standard {"ok": false, "error": ...}
    # contract (see cmd_regression's own validation below), not a raw
    # argparse SystemExit, matching this file's own stated convention that
    # commands never raise on expected/business-logic failures.
    p.add_argument("--mode", default="deterministic")
    p.add_argument("--tmp-root", default=None,
                    help="Real writable dir for deterministic mode's two filesystem-backed fixtures. "
                         "Defaults to a subdirectory under --store-root. Ignored in live-review mode.")
    p.set_defaults(func=cmd_regression)

    p = sub.add_parser("canary-run"); _common(p)
    p.add_argument("--canary-page-url", default=None,
                    help="Real URL for preview-capture to screenshot. Defaults to a minimal local "
                         "HTML file generated under --store-root.")
    p.set_defaults(func=cmd_canary_run)

    p = sub.add_parser("run-report"); _common(p)
    p.add_argument("--out-dir", default=None,
                    help="Where to write run-report.json/.md + owner-summary.txt. Defaults to "
                         "<store-root>/reports/<run-id>/.")
    p.add_argument("--production-deployment-id", default=None,
                    help="Optional caller-supplied Cloudflare Pages deployment ID -- this side has "
                         "no way to derive it automatically (no live Cloudflare API call exists "
                         "here yet). Never gates terminal_status.")
    p.set_defaults(func=cmd_run_report)

    p = sub.add_parser("content-lint")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--file")
    group.add_argument("--dir")
    p.set_defaults(func=cmd_content_lint)

    return parser


def run_cli(argv: list[str]) -> dict[str, Any]:
    """Testable entry point: parse argv, dispatch, return the result dict
    without touching stdout. `main()` below wraps this for real CLI use."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except NookGuardError as e:
        return {"ok": False, "error": str(e)}


def main(argv: list[str] | None = None) -> int:
    result = run_cli(sys.argv[1:] if argv is None else argv)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
