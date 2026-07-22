"""Filesystem-backed store for run-time NookGuard artifacts (specs, prompts,
quarantined candidates, attempt records). This is the pre-Commit-14 substitute
for the D1/R2 backend in Appendix H — same content-addressed, immutable-once-
written contract, different storage engine. Nothing outside this module should
know or care which backend is in use."""

from __future__ import annotations

import json
from pathlib import Path

from .exceptions import HashMismatchError
from .hashing import sha256_bytes, sha256_canonical_json
from .review_pack import ReviewPack
from .schemas import AssetContract, GenerationAttempt


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.specs_dir = self.root / "specs"
        self.prompts_dir = self.root / "prompts"
        self.quarantine_dir = self.root / "quarantine"
        self.attempts_dir = self.root / "attempts"
        self.review_packs_dir = self.root / "review_packs"
        for d in (self.specs_dir, self.prompts_dir, self.quarantine_dir, self.attempts_dir,
                  self.review_packs_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def dedup_registry_path(self) -> Path:
        return self.root / "dedup_registry.json"

    # ---- specs ----

    def save_spec(self, contract: AssetContract) -> str:
        """Locks and writes a spec. Returns spec_sha256. Content-addressed and
        immutable: writing the same contract twice is a no-op, not an error."""
        payload = contract.model_dump(mode="json")
        spec_sha256 = sha256_canonical_json(payload)
        path = self.specs_dir / f"{spec_sha256}.json"
        if not path.exists():
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return spec_sha256

    def load_spec(self, spec_sha256: str) -> AssetContract:
        path = self.specs_dir / f"{spec_sha256}.json"
        if not path.exists():
            raise FileNotFoundError(f"No locked spec found for {spec_sha256}")
        data = json.loads(path.read_text(encoding="utf-8"))
        actual = sha256_canonical_json(data)
        if actual != spec_sha256:
            raise HashMismatchError(spec_sha256, actual, context="spec on disk")
        return AssetContract.model_validate(data)

    # ---- prompts ----

    def save_prompt(self, prompt_text: str) -> str:
        prompt_sha256 = sha256_bytes(prompt_text.encode("utf-8"))
        path = self.prompts_dir / f"{prompt_sha256}.txt"
        if not path.exists():
            path.write_text(prompt_text, encoding="utf-8")
        return prompt_sha256

    def load_prompt(self, prompt_sha256: str) -> str:
        path = self.prompts_dir / f"{prompt_sha256}.txt"
        if not path.exists():
            raise FileNotFoundError(f"No compiled prompt found for {prompt_sha256}")
        text = path.read_text(encoding="utf-8")
        actual = sha256_bytes(text.encode("utf-8"))
        if actual != prompt_sha256:
            raise HashMismatchError(prompt_sha256, actual, context="prompt on disk")
        return text

    # ---- candidates (quarantine) + generation attempts ----

    def quarantine_candidate(self, file_bytes: bytes, suffix: str) -> str:
        """Section 27: candidate path includes the full hash; writes ONLY to
        quarantine, never a public path. Returns candidate_sha256."""
        candidate_sha256 = sha256_bytes(file_bytes)
        path = self.quarantine_dir / f"{candidate_sha256}{suffix}"
        if not path.exists():
            path.write_bytes(file_bytes)
        return candidate_sha256

    def candidate_path(self, candidate_sha256: str) -> Path:
        matches = list(self.quarantine_dir.glob(f"{candidate_sha256}.*"))
        if not matches:
            raise FileNotFoundError(f"No quarantined candidate for {candidate_sha256}")
        return matches[0]

    def save_attempt(self, attempt: GenerationAttempt) -> None:
        path = self.attempts_dir / f"{attempt.candidate_sha256}.json"
        if path.exists():
            raise FileExistsError(
                f"Generation attempt {attempt.candidate_sha256} already registered "
                "(section 27: one output, one record — no overwrite)"
            )
        path.write_text(attempt.model_dump_json(indent=2), encoding="utf-8")

    def load_attempt(self, candidate_sha256: str) -> GenerationAttempt:
        path = self.attempts_dir / f"{candidate_sha256}.json"
        if not path.exists():
            raise FileNotFoundError(f"No generation attempt registered for {candidate_sha256}")
        return GenerationAttempt.model_validate_json(path.read_text(encoding="utf-8"))

    # ---- review packs (Commit 6, consumed by Commit 7's observer sessions) ----

    def save_review_pack(self, pack: ReviewPack) -> str:
        path = self.review_packs_dir / f"{pack.review_pack_sha256}.json"
        if not path.exists():
            path.write_text(json.dumps(pack.to_dict(), indent=2), encoding="utf-8")
        return pack.review_pack_sha256

    def load_review_pack(self, review_pack_sha256: str) -> dict:
        path = self.review_packs_dir / f"{review_pack_sha256}.json"
        if not path.exists():
            raise FileNotFoundError(f"No review pack found for {review_pack_sha256}")
        return json.loads(path.read_text(encoding="utf-8"))

    # ---- asset state tracking (drives state_machine.transition() checks) ----

    def get_state(self, asset_id: str) -> str | None:
        path = self.root / "asset_states" / f"{asset_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))["state"]

    def set_state(self, asset_id: str, state: str) -> None:
        d = self.root / "asset_states"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{asset_id}.json").write_text(
            json.dumps({"asset_id": asset_id, "state": state}, indent=2), encoding="utf-8"
        )
