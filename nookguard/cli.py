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
from .agent_runner import ReviewSessionError, run_judge_session, run_observer_session
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
from .owner_queue import OwnerQueue, should_queue_for_owner
from .prompt_compiler import compile_prompt
from .review_pack import OBSERVER_ROLES, build_review_pack
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
