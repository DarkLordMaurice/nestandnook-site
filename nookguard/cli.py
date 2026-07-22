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
from typing import Any

from .adapters import AVAILABLE_ADAPTERS
from .aggregator import aggregate
from .agent_runner import (
    ReviewSessionError,
    run_judge_session,
    run_observer_session,
    run_page_review_session,
)
from .canon import CanonRegistry
from .dedup import DedupRegistry
from .exceptions import (
    HashMismatchError,
    InvalidTransitionError,
    MissingCanonError,
    NookGuardError,
    StaleCanonError,
)
from .hashing import sha256_bytes
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
from .regression_corpus import run_regression_corpus
from .release import ReleaseIntegrityError, publish_candidate
from .review_pack import OBSERVER_ROLES, build_review_pack
from .run_report import write_run_report
from .schemas import AssetContract, GenerationAttempt
from .state_machine import AssetState, transition
from .store import Store
from .validators import image as image_validator

DEFAULT_STORE_ROOT = Path("nookguard_store")
# nookguard/cli.py -> nookguard -> site -> project root
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _store(root: Path) -> Store:
    return Store(root)


def _ledger(root: Path) -> Ledger:
    return Ledger(root / "events.jsonl")


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
    )
    final = AssetState.TECHNICAL_PASS if report["technical_pass"] else AssetState.TECHNICAL_FAIL
    transition(target, final, asset_id=contract.asset_id)
    store.set_state(contract.asset_id, final.value)

    # Only register into the corpus on a real pass — a failed/blank/duplicate
    # candidate shouldn't become a future "known good" comparison point.
    if final == AssetState.TECHNICAL_PASS:
        dedup_registry.register(args.candidate_sha256, candidate_path)

    ledger.append(run_id=args.run_id, event_type="technical_validation.completed",
                  actor_role=args.actor_role, payload={"candidate_sha256": args.candidate_sha256,
                  "result": final.value, "report": report}, asset_id=contract.asset_id)
    return {"ok": True, "asset_id": contract.asset_id, "result": final.value, "report": report}


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

    p = sub.add_parser("judge"); _common(p)
    p.add_argument("--candidate-sha256", required=True)
    p.set_defaults(func=cmd_judge)

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
