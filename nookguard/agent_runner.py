"""Claude review-agent runner (Commit 7). Real vision review sessions go
through the Anthropic Python SDK directly (`anthropic`, confirmed installed
in this environment at 0.76.0) rather than shelling out to the `claude` CLI.
Research done for this commit (see docs/nookguard/BUILD-LOG.md's Commit 7
entry) found the `claude` CLI's headless `-p`/`--print` mode does not feed
local image files into the model's vision input -- its Read tool treats
files as text. True headless vision needs either the separate Claude Agent
SDK package (not installed here) or the base Messages API directly, which IS
installed and is Anthropic's own first-party SDK.

Using the Messages API directly also gives "session separation" for free:
each call here is a single, stateless request with no conversation history
and no tools attached. There is no mechanism by which two role sessions
could share context, even by accident -- there is nothing to share.

Contract with the rest of NookGuard: `run_observer_session()` accepts a
ReviewPack and NOTHING else -- no contract, no prompt text, no requirements.
That's not just documentation, it's the actual function signature, so a
future call site literally cannot pass contract data into an observer call
without a visible type error. `run_judge_session()` is the only function in
this module that ever sees contract requirements, and it never sees the
image.

Commit 19 default-transport change: every function below now defaults to
`cli_reviewer.claude_cli_executor` (fresh, non-interactive `claude -p`
processes, authenticated via the operator's own Claude subscription), not
`_default_executor` (the direct Anthropic Messages API call requiring a
separate ANTHROPIC_API_KEY this environment has never had -- see
docs/nookguard/BUILD-LOG.md's Commit 18 entry, the real finding that
started this commit). `_default_executor` remains fully defined and
importable below -- pass `executor=_default_executor` explicitly at any
call site to opt back into the direct-API transport; nothing about the
function signatures changed, only the default value.

Commit 23 restructuring: every real automated run of NookGuard happens
inside a live, already-authenticated Cowork agent session (this project's
scheduled tasks are Cowork scheduled tasks, not bare cron scripts) -- so
`claude_cli_executor`'s whole reason to exist (get a Claude call without a
live agent session present) was solving a problem this project doesn't
actually have, at the real cost of a second, separate Claude Code CLI
login `mediactl` could never share with the orchestrating session. Each of
`run_observer_session`/`run_judge_session`/`run_page_review_session` below
is now a thin wrapper around a `build_*_prompt()` + executor call +
`finalize_*()`, split out so the middle step -- actually getting a Claude
reply -- can instead be performed by whatever live agent is orchestrating
the run (via its own Task/Agent tool, no subprocess, no separate auth),
with the real system prompt/instruction/image path coming from
`build_*_prompt()` and the raw reply handed back to `finalize_*()` for the
exact same parsing/enrichment/schema-validation this module has always
done. See `cli.py`'s new `observe-prepare`/`observe-submit`/`judge-
prepare`/`judge-submit`/`preview-review-prepare`/`preview-review-submit`
commands -- this is the primary, recommended path for real automation now.
The atomic `run_*_session()` functions and both executors
(`claude_cli_executor`, `_default_executor`) remain fully real, tested,
and available unchanged -- for a genuinely standalone/headless run with no
live agent present, `mediactl observe`/`judge`/`preview-review` (the
original atomic commands) still work exactly as before."""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from .cli_reviewer import claude_cli_executor
from .hashing import sha256_bytes, sha256_canonical_json
from .review_pack import ReviewPack
from .schemas import AssetContract, BlindObservation, ContractJudgment, PageReviewResult

AGENTS_DIR = Path(__file__).resolve().parent / "agents"
MODEL = "claude-opus-4-8"

SessionExecutor = Callable[[str, list[dict[str, Any]]], str]


class ReviewSessionError(Exception):
    """Section 29.5: 'Model JSON invalid or session interrupted ->
    REVIEW_ERROR; no pass inherited.' This exception is that trigger --
    callers must route it to REVIEW_ERROR, never swallow it into a default
    pass/fail."""

    def __init__(self, role: str, reason: str, raw_response: str = ""):
        self.role = role
        self.reason = reason
        self.raw_response = raw_response
        super().__init__(f"Review session error ({role}): {reason}")


def _load_system_prompt(filename: str, agents_dir: Path = AGENTS_DIR) -> str:
    path = agents_dir / filename
    return path.read_text(encoding="utf-8")


def agent_definition_hash(filename: str, agents_dir: Path = AGENTS_DIR) -> str:
    """Hash of an agent's actual instruction text -- Appendix C/D's
    `reviewer_agent_hash`/`judge_agent_hash` fields. A future edit to any of
    these instruction files changes this hash, making a change in review
    behavior attributable instead of invisible."""
    return sha256_bytes(_load_system_prompt(filename, agents_dir).encode("utf-8"))


def _image_to_content_block(image_path: str) -> dict[str, Any]:
    data = Path(image_path).read_bytes()
    media_type = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode("ascii")},
    }


def _default_executor(system_prompt: str, user_content: list[dict[str, Any]]) -> str:
    """Real Anthropic Messages API call: no tools attached, no conversation
    history, a single stateless turn. As of Commit 19 this is NO LONGER the
    default `executor=` value on any of the three functions below --
    `cli_reviewer.claude_cli_executor` is -- but this remains a fully real,
    working, opt-in transport (pass `executor=_default_executor`
    explicitly). Not exercised live in this environment (no
    ANTHROPIC_API_KEY configured here, confirmed absent from process/User/
    Machine scopes -- see BUILD-LOG's Commit 18 entry)."""
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _extract_json(raw_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Model responses sometimes wrap JSON in a markdown code fence despite
    explicit instructions not to -- strip that, then take the first balanced
    {...} span rather than assuming the whole string is clean JSON.

    Commit 24, requirement 7: returns (parsed, diagnostics) instead of just
    parsed -- `diagnostics` is the real, checkable record of what parsing
    actually did to the raw text (was a fence stripped, where the brace span
    was found, what top-level keys came out) so a caller can persist it
    SEPARATELY from both the untouched raw response and the final schema-
    validated result, per requirement 7's three-way split."""
    text = raw_text.strip()
    diagnostics: dict[str, Any] = {
        "raw_length": len(raw_text), "stripped_length": len(text), "markdown_fence_stripped": False,
    }
    if text.startswith("```"):
        diagnostics["markdown_fence_stripped"] = True
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    diagnostics["brace_start_index"] = start
    diagnostics["brace_end_index"] = end
    if start == -1 or end == -1 or end < start:
        raise json.JSONDecodeError("no JSON object found in response", text, 0)
    parsed = json.loads(text[start:end + 1])
    diagnostics["parsed_top_level_keys"] = sorted(parsed.keys()) if isinstance(parsed, dict) else None
    return parsed, diagnostics


def build_observer_prompt(review_pack: ReviewPack, *, agents_dir: Path = AGENTS_DIR) -> dict[str, Any]:
    """Everything needed to actually PERFORM an observer session -- without
    performing it. Split out of run_observer_session (Commit 23) so a live
    orchestrating agent's own Task/Agent tool can do the model call itself.
    The ONLY input is a ReviewPack -- same enforcement of Appendix C's 'the
    observer session never sees the contract' as before, just relocated:
    there is still no parameter here through which a contract could leak
    in, even by mistake."""
    role = review_pack.observer_role
    prompt_file = ("adversarial_observer_system_prompt.md" if role == "adversarial_b"
                   else "blind_observer_system_prompt.md")
    system_prompt = _load_system_prompt(prompt_file, agents_dir)

    instruction = "Describe exactly what you observe in this image as structured JSON."
    if role == "adversarial_b":
        instruction += " Actively look for the failure-taxonomy categories described in your instructions."

    return {
        "role": role,
        "prompt_file": prompt_file,
        "system_prompt": system_prompt,
        "instruction": instruction,
        "image_path": review_pack.image_path,
    }


def finalize_observation(
    review_pack: ReviewPack,
    raw_response: str,
    *,
    agents_dir: Path = AGENTS_DIR,
    session_id: str | None = None,
    diagnostics_out: dict[str, Any] | None = None,
) -> BlindObservation:
    """The exact parse/enrich/schema-validate logic run_observer_session has
    always used, taking an already-obtained raw_response instead of calling
    an executor itself -- so a response obtained via a live agent's own
    Task/Agent tool call gets the identical real validation a CLI/API
    executor's response would have gotten. `session_id` is injectable for
    tests; a real caller lets it default to a fresh uuid4, exactly as
    before. `diagnostics_out`, if given a dict, is populated in place with
    `_extract_json`'s parsing diagnostics (Commit 24, requirement 7) --
    optional and additive, every existing call site is unaffected."""
    role = review_pack.observer_role
    prompt_file = ("adversarial_observer_system_prompt.md" if role == "adversarial_b"
                   else "blind_observer_system_prompt.md")
    session_id = session_id or str(uuid.uuid4())

    try:
        parsed, diagnostics = _extract_json(raw_response)
    except Exception as e:
        if diagnostics_out is not None:
            diagnostics_out["error"] = str(e)
        raise ReviewSessionError(role, f"session failed or returned invalid JSON: {e}", raw_response=raw_response)
    if diagnostics_out is not None:
        diagnostics_out.update(diagnostics)

    parsed["candidate_sha256"] = review_pack.candidate_sha256
    parsed["review_pack_sha256"] = review_pack.review_pack_sha256
    parsed["reviewer_session_id"] = session_id
    parsed["observer_role"] = role
    parsed.setdefault("review_id", str(uuid.uuid4()))
    parsed.setdefault("reviewer_agent_hash", agent_definition_hash(prompt_file, agents_dir))
    parsed.setdefault("context_bundle_sha256", review_pack.review_pack_sha256)

    try:
        return BlindObservation.model_validate(parsed)
    except ValidationError as e:
        raise ReviewSessionError(role, f"response failed schema validation: {e}", raw_response=raw_response)


def run_observer_session(
    review_pack: ReviewPack,
    *,
    executor: SessionExecutor = claude_cli_executor,
    agents_dir: Path = AGENTS_DIR,
) -> BlindObservation:
    """Atomic, in-process convenience wrapper (build -> executor -> finalize)
    -- unchanged behavior and signature from before Commit 23, still fully
    real and available for a genuinely standalone/headless run with no live
    agent orchestrating (pass an explicit `executor=` for the CLI or direct-
    API transport). The recommended path for a real automated run -- one
    orchestrated by a live Cowork agent -- is `build_observer_prompt()` +
    the agent's own Task/Agent tool call + `finalize_observation()`, wired
    together by `cli.py`'s `observe-prepare`/`observe-submit`."""
    prompt = build_observer_prompt(review_pack, agents_dir=agents_dir)
    user_content = [_image_to_content_block(prompt["image_path"]), {"type": "text", "text": prompt["instruction"]}]

    raw = ""
    try:
        raw = executor(prompt["system_prompt"], user_content)
    except Exception as e:
        raise ReviewSessionError(prompt["role"], f"session failed or returned invalid JSON: {e}", raw_response=raw)

    return finalize_observation(review_pack, raw, agents_dir=agents_dir)


def build_judge_prompt(
    contract: AssetContract,
    blind_observation: BlindObservation,
    adversarial_observation: BlindObservation,
    *,
    agents_dir: Path = AGENTS_DIR,
) -> dict[str, Any]:
    """Everything needed to actually PERFORM a judge session -- without
    performing it (Commit 23, mirrors build_observer_prompt above). Sees
    contract requirements + both observation reports -- never the image
    itself, and never the compiled prompt text; same Appendix D boundary as
    before, just relocated out of the executor-calling function."""
    system_prompt = _load_system_prompt("contract_judge_system_prompt.md", agents_dir)
    payload = {
        "requirements": [r.model_dump(mode="json") for r in contract.requirements],
        "forbidden_objects": contract.forbidden_objects,
        "blind_observation": blind_observation.model_dump(mode="json"),
        "adversarial_observation": adversarial_observation.model_dump(mode="json"),
    }
    return {"system_prompt": system_prompt, "payload": payload}


def finalize_judgment(
    blind_observation: BlindObservation,
    spec_sha256: str,
    payload: dict[str, Any],
    raw_response: str,
    *,
    agents_dir: Path = AGENTS_DIR,
    session_id: str | None = None,
    diagnostics_out: dict[str, Any] | None = None,
) -> ContractJudgment:
    """The exact parse/enrich/schema-validate logic run_judge_session has
    always used. `payload` is the same dict build_judge_prompt() returned
    (needed again here only to recompute context_bundle_sha256 identically
    to before) -- a caller always has it already, from the prepare step.
    `diagnostics_out` -- see finalize_observation's docstring, same
    contract."""
    session_id = session_id or str(uuid.uuid4())
    try:
        parsed, diagnostics = _extract_json(raw_response)
    except Exception as e:
        if diagnostics_out is not None:
            diagnostics_out["error"] = str(e)
        raise ReviewSessionError("judge", f"session failed or returned invalid JSON: {e}", raw_response=raw_response)
    if diagnostics_out is not None:
        diagnostics_out.update(diagnostics)

    parsed["candidate_sha256"] = blind_observation.candidate_sha256
    parsed["judge_session_id"] = session_id
    parsed["spec_sha256"] = spec_sha256
    parsed.setdefault("judge_agent_hash",
                       agent_definition_hash("contract_judge_system_prompt.md", agents_dir))
    parsed.setdefault("context_bundle_sha256", sha256_canonical_json(payload))

    try:
        return ContractJudgment.model_validate(parsed)
    except ValidationError as e:
        raise ReviewSessionError("judge", f"response failed schema validation: {e}", raw_response=raw_response)


def run_judge_session(
    contract: AssetContract,
    spec_sha256: str,
    blind_observation: BlindObservation,
    adversarial_observation: BlindObservation,
    *,
    executor: SessionExecutor = claude_cli_executor,
    agents_dir: Path = AGENTS_DIR,
) -> ContractJudgment:
    """Atomic, in-process convenience wrapper -- unchanged behavior/signature
    from before Commit 23. See run_observer_session's docstring for the
    same note about the recommended live-agent-orchestrated path instead
    (judge-prepare/judge-submit)."""
    prompt = build_judge_prompt(contract, blind_observation, adversarial_observation, agents_dir=agents_dir)
    user_content = [{"type": "text", "text": json.dumps(prompt["payload"], indent=2)}]

    raw = ""
    try:
        raw = executor(prompt["system_prompt"], user_content)
    except Exception as e:
        raise ReviewSessionError("judge", f"session failed or returned invalid JSON: {e}", raw_response=raw)

    return finalize_judgment(blind_observation, spec_sha256, prompt["payload"], raw, agents_dir=agents_dir)


def build_page_review_prompt(
    contact_sheet_path: str,
    page_url: str,
    viewports_captured: list[str],
    *,
    agents_dir: Path = AGENTS_DIR,
) -> dict[str, Any]:
    """Everything needed to actually PERFORM a page-review session --
    without performing it (Commit 23, mirrors build_observer_prompt).
    Same boundary as before: a contact sheet image (rendered output only)
    and the page URL -- never the page's markdown source, frontmatter, or
    any content-schema expectations."""
    system_prompt = _load_system_prompt("page_reviewer_system_prompt.md", agents_dir)
    instruction = (
        f"Review this contact sheet for page {page_url}. Viewports shown: "
        f"{', '.join(viewports_captured)}."
    )
    return {
        "system_prompt": system_prompt, "instruction": instruction,
        "image_path": contact_sheet_path, "page_url": page_url, "viewports_captured": viewports_captured,
    }


def finalize_page_review(
    page_url: str,
    viewports_captured: list[str],
    contact_sheet_path: str,
    raw_response: str,
    *,
    agents_dir: Path = AGENTS_DIR,
    session_id: str | None = None,
    diagnostics_out: dict[str, Any] | None = None,
) -> PageReviewResult:
    """The exact parse/enrich/schema-validate logic run_page_review_session
    has always used, taking an already-obtained raw_response.
    `diagnostics_out` -- see finalize_observation's docstring, same
    contract."""
    session_id = session_id or str(uuid.uuid4())
    try:
        parsed, diagnostics = _extract_json(raw_response)
    except Exception as e:
        if diagnostics_out is not None:
            diagnostics_out["error"] = str(e)
        raise ReviewSessionError("page_reviewer", f"session failed or returned invalid JSON: {e}",
                                  raw_response=raw_response)
    if diagnostics_out is not None:
        diagnostics_out.update(diagnostics)

    parsed["page_url"] = page_url
    parsed.setdefault("viewports_reviewed", viewports_captured)
    parsed["review_session_id"] = session_id
    parsed.setdefault("reviewer_agent_hash",
                       agent_definition_hash("page_reviewer_system_prompt.md", agents_dir))
    parsed.setdefault("context_bundle_sha256", sha256_bytes(contact_sheet_path.encode("utf-8")))

    try:
        return PageReviewResult.model_validate(parsed)
    except ValidationError as e:
        raise ReviewSessionError("page_reviewer", f"response failed schema validation: {e}",
                                  raw_response=raw_response)


def run_page_review_session(
    contact_sheet_path: str,
    page_url: str,
    viewports_captured: list[str],
    *,
    executor: SessionExecutor = claude_cli_executor,
    agents_dir: Path = AGENTS_DIR,
) -> PageReviewResult:
    """Atomic, in-process convenience wrapper -- unchanged behavior/signature
    from before Commit 23. See run_observer_session's docstring for the
    same note about the recommended live-agent-orchestrated path instead
    (preview-review-prepare/preview-review-submit)."""
    prompt = build_page_review_prompt(contact_sheet_path, page_url, viewports_captured, agents_dir=agents_dir)
    user_content = [_image_to_content_block(prompt["image_path"]), {"type": "text", "text": prompt["instruction"]}]

    raw = ""
    try:
        raw = executor(prompt["system_prompt"], user_content)
    except Exception as e:
        raise ReviewSessionError("page_reviewer", f"session failed or returned invalid JSON: {e}", raw_response=raw)

    return finalize_page_review(page_url, viewports_captured, contact_sheet_path, raw, agents_dir=agents_dir)
