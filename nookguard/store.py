"""Filesystem-backed store for run-time NookGuard artifacts (specs, prompts,
quarantined candidates, attempt records). This is the pre-Commit-14 substitute
for the D1/R2 backend in Appendix H — same content-addressed, immutable-once-
written contract, different storage engine. Nothing outside this module should
know or care which backend is in use."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .exceptions import HashMismatchError
from .hashing import sha256_bytes, sha256_canonical_json
from .manifest import ReleaseManifestEntry
from .preview import PageCaptureReport
from .review_pack import ReviewPack
from .schemas import AssetContract, BlindObservation, ContractJudgment, GenerationAttempt, PageReviewResult


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.specs_dir = self.root / "specs"
        self.prompts_dir = self.root / "prompts"
        self.quarantine_dir = self.root / "quarantine"
        self.attempts_dir = self.root / "attempts"
        self.review_packs_dir = self.root / "review_packs"
        self.observations_dir = self.root / "observations"
        self.judgments_dir = self.root / "judgments"
        self.preview_dir = self.root / "preview"
        self.releases_dir = self.root / "releases"
        for d in (self.specs_dir, self.prompts_dir, self.quarantine_dir, self.attempts_dir,
                  self.review_packs_dir, self.observations_dir, self.judgments_dir, self.preview_dir,
                  self.releases_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def dedup_registry_path(self) -> Path:
        return self.root / "dedup_registry.json"

    @property
    def owner_queue_path(self) -> Path:
        return self.root / "owner_queue.json"

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

    # ---- observations + judgments (Commit 8) ----

    def save_observation(self, observation: BlindObservation) -> str:
        """Keyed by candidate_sha256 + role -- one observation per role per
        candidate, overwritable only by a genuinely new session (same key
        always means 'the latest observation for this candidate/role')."""
        key = f"{observation.candidate_sha256}_{observation.observer_role}"
        path = self.observations_dir / f"{key}.json"
        path.write_text(observation.model_dump_json(indent=2), encoding="utf-8")
        return key

    def load_observation(self, candidate_sha256: str, role: str) -> BlindObservation:
        key = f"{candidate_sha256}_{role}"
        path = self.observations_dir / f"{key}.json"
        if not path.exists():
            raise FileNotFoundError(f"No {role} observation found for {candidate_sha256}")
        return BlindObservation.model_validate_json(path.read_text(encoding="utf-8"))

    def save_judgment(self, judgment: ContractJudgment) -> str:
        path = self.judgments_dir / f"{judgment.candidate_sha256}.json"
        path.write_text(judgment.model_dump_json(indent=2), encoding="utf-8")
        return judgment.candidate_sha256

    def load_judgment(self, candidate_sha256: str) -> ContractJudgment:
        path = self.judgments_dir / f"{candidate_sha256}.json"
        if not path.exists():
            raise FileNotFoundError(f"No judgment found for {candidate_sha256}")
        return ContractJudgment.model_validate_json(path.read_text(encoding="utf-8"))

    # ---- per-adapter asset counters (Commit 8 owner-queue calibration) ----

    def bump_adapter_asset_count(self, adapter_version: str) -> int:
        """Returns the count AFTER incrementing -- 'this is the Nth asset
        seen for this adapter', 1-indexed, used by owner_queue's
        should_queue_for_owner() to implement the 'first N assets per
        adapter' calibration rule (43.1)."""
        path = self.root / "adapter_counts.json"
        counts = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        counts[adapter_version] = counts.get(adapter_version, 0) + 1
        path.write_text(json.dumps(counts, indent=2), encoding="utf-8")
        return counts[adapter_version]

    # ---- preview capture + page review (Commit 10) ----

    def save_preview_capture(
        self, candidate_sha256: str, page_url: str, contact_sheet_path: str,
        reports: list[PageCaptureReport],
    ) -> str:
        """One JSON file per candidate holding every viewport's capture
        report plus the contact sheet built from them -- read back whole by
        preview-review, which never re-captures, only re-reads."""
        path = self.preview_dir / f"{candidate_sha256}.json"
        payload = {
            "candidate_sha256": candidate_sha256,
            "page_url": page_url,
            "contact_sheet_path": contact_sheet_path,
            "reports": [asdict(r) for r in reports],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def load_preview_capture(self, candidate_sha256: str) -> dict:
        path = self.preview_dir / f"{candidate_sha256}.json"
        if not path.exists():
            raise FileNotFoundError(f"No preview capture found for {candidate_sha256}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save_page_review(self, candidate_sha256: str, review: PageReviewResult) -> str:
        path = self.preview_dir / f"{candidate_sha256}_review.json"
        path.write_text(review.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def load_page_review(self, candidate_sha256: str) -> PageReviewResult:
        path = self.preview_dir / f"{candidate_sha256}_review.json"
        if not path.exists():
            raise FileNotFoundError(f"No page review found for {candidate_sha256}")
        return PageReviewResult.model_validate_json(path.read_text(encoding="utf-8"))

    # ---- release manifest entries (Commit 12) ----

    def save_release_manifest(self, entry: ReleaseManifestEntry) -> str:
        path = self.releases_dir / f"{entry.candidate_sha256}.json"
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def load_release_manifest(self, candidate_sha256: str) -> ReleaseManifestEntry:
        path = self.releases_dir / f"{candidate_sha256}.json"
        if not path.exists():
            raise FileNotFoundError(f"No release manifest entry found for {candidate_sha256}")
        return ReleaseManifestEntry.model_validate_json(path.read_text(encoding="utf-8"))

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
