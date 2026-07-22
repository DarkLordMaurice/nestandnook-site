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
image."""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from .hashing import sha256_bytes, sha256_canonical_json
from .review_pack import ReviewPack
from .schemas import AssetContract, BlindObservation, ContractJudgment

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
    history, a single stateless turn. Not exercised live in this session (no
    API key configured here) -- see BUILD-LOG's unresolved-risks note."""
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _extract_json(raw_text: str) -> dict[str, Any]:
    """Model responses sometimes wrap JSON in a markdown code fence despite
    explicit instructions not to -- strip that, then take the first balanced
    {...} span rather than assuming the whole string is clean JSON."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise json.JSONDecodeError("no JSON object found in response", text, 0)
    return json.loads(text[start:end + 1])


def run_observer_session(
    review_pack: ReviewPack,
    *,
    executor: SessionExecutor = _default_executor,
    agents_dir: Path = AGENTS_DIR,
) -> BlindObservation:
    """The ONLY inputs this function's signature allows are a ReviewPack and
    an executor override -- there is no parameter through which a caller
    could pass a contract, prompt, or expected-object list even by mistake.
    That is the actual enforcement of Appendix C's 'the observer session
    never sees the contract', not just a comment saying so."""
    role = review_pack.observer_role
    prompt_file = ("adversarial_observer_system_prompt.md" if role == "adversarial_b"
                   else "blind_observer_system_prompt.md")
    system_prompt = _load_system_prompt(prompt_file, agents_dir)

    instruction = "Describe exactly what you observe in this image as structured JSON."
    if role == "adversarial_b":
        instruction += " Actively look for the failure-taxonomy categories described in your instructions."
    user_content = [_image_to_content_block(review_pack.image_path), {"type": "text", "text": instruction}]

    session_id = str(uuid.uuid4())
    raw = ""
    try:
        raw = executor(system_prompt, user_content)
        parsed = _extract_json(raw)
    except Exception as e:
        raise ReviewSessionError(role, f"session failed or returned invalid JSON: {e}", raw_response=raw)

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
        raise ReviewSessionError(role, f"response failed schema validation: {e}", raw_response=raw)


def run_judge_session(
    contract: AssetContract,
    spec_sha256: str,
    blind_observation: BlindObservation,
    adversarial_observation: BlindObservation,
    *,
    executor: SessionExecutor = _default_executor,
    agents_dir: Path = AGENTS_DIR,
) -> ContractJudgment:
    """Sees contract requirements + both observation reports -- never the
    image itself, and never the compiled prompt text. This is the only
    function in this module that is allowed to see requirements, matching
    Appendix D."""
    system_prompt = _load_system_prompt("contract_judge_system_prompt.md", agents_dir)

    payload = {
        "requirements": [r.model_dump(mode="json") for r in contract.requirements],
        "forbidden_objects": contract.forbidden_objects,
        "blind_observation": blind_observation.model_dump(mode="json"),
        "adversarial_observation": adversarial_observation.model_dump(mode="json"),
    }
    user_content = [{"type": "text", "text": json.dumps(payload, indent=2)}]

    session_id = str(uuid.uuid4())
    raw = ""
    try:
        raw = executor(system_prompt, user_content)
        parsed = _extract_json(raw)
    except Exception as e:
        raise ReviewSessionError("judge", f"session failed or returned invalid JSON: {e}", raw_response=raw)

    parsed["candidate_sha256"] = blind_observation.candidate_sha256
    parsed["judge_session_id"] = session_id
    parsed["spec_sha256"] = spec_sha256
    parsed.setdefault("judge_agent_hash",
                       agent_definition_hash("contract_judge_system_prompt.md", agents_dir))
    parsed.setdefault("context_bundle_sha256", sha256_canonical_json(payload))

    try:
        return ContractJudgment.model_validate(parsed)
    except ValidationError as e:
        raise ReviewSessionError("judge", f"response failed schema validation: {e}", raw_response=raw)
