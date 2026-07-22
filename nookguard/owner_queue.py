"""Owner queue (Commit 8) — tracks assets that need Maurice's eyes, per the
risk-tier table (43.1). This is a TRACKING/VISIBILITY mechanism, not a
publish gate: per Maurice's 2026-07-21 instruction and the standing note in
docs/nookguard/SPEC.md, pre-push owner approval is explicitly deferred right
now. An asset can land in this queue and still be released — nothing in the
CLI checks queue status before allowing a release. When that changes (Maurice
says it's time), the gate goes in cli.py's release command, not here; this
module only decides WHEN something is queue-worthy and records it."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schemas import RiskTier
from .state_machine import AssetState


def should_queue_for_owner(
    risk_tier: RiskTier,
    result_state: AssetState,
    *,
    assets_seen_for_adapter: int = 0,
    is_disagreement: bool = False,
) -> bool:
    """Section 43.1's calibration policy, as real code:
    - NEEDS_OWNER always queues, regardless of tier (that's what the state means).
    - Tier 3: always queues, even on SEMANTIC_PASS ("Owner: always final approval").
    - Tier 2: mandatory during launch -> always queues for now (relaxing this
      requires a measured sample + owner approval per the doc, which hasn't
      happened yet).
    - Tier 1: queues on disagreement, or if this is among the first 20 assets
      seen for this adapter ("first 20 assets per adapter").
    - Tier 0: queues on disagreement, or via a random 10% calibration sample
      for the first 50 assets only -- the "random" part is intentionally NOT
      implemented as real randomness here (that would make this function
      non-deterministic and untestable); callers doing Tier 0 calibration
      sampling should decide the random draw themselves and pass the result
      in as `is_disagreement`-equivalent context, or simply queue every
      Nth asset deterministically. This function only encodes the
      first-50-assets bound.
    """
    if result_state == AssetState.NEEDS_OWNER:
        return True
    if risk_tier == RiskTier.TIER_3:
        return True
    if risk_tier == RiskTier.TIER_2:
        return True
    if is_disagreement:
        return True
    if risk_tier == RiskTier.TIER_1:
        return assets_seen_for_adapter < 20
    if risk_tier == RiskTier.TIER_0:
        return assets_seen_for_adapter < 50 and (assets_seen_for_adapter % 10 == 0)
    return False


class OwnerQueue:
    """JSON-file-backed, same pattern as DedupRegistry/Ledger -- a small,
    slow-growing corpus, not a high-throughput store."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, entries: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def enqueue(self, asset_id: str, candidate_sha256: str, reasons: list[str],
                risk_tier: str, result_state: str) -> None:
        entries = self._load()
        entries.append({
            "asset_id": asset_id,
            "candidate_sha256": candidate_sha256,
            "reasons": reasons,
            "risk_tier": risk_tier,
            "result_state": result_state,
            "status": "pending",
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None,
            "resolved_by": None,
            "decision": None,
        })
        self._save(entries)

    def list_pending(self) -> list[dict]:
        return [e for e in self._load() if e["status"] == "pending"]

    def resolve(self, asset_id: str, candidate_sha256: str, decision: str, resolved_by: str) -> bool:
        """decision: 'approved' | 'rejected'. Returns True if a matching
        pending entry was found and resolved."""
        entries = self._load()
        found = False
        for e in entries:
            if e["asset_id"] == asset_id and e["candidate_sha256"] == candidate_sha256 \
                    and e["status"] == "pending":
                e["status"] = "resolved"
                e["decision"] = decision
                e["resolved_by"] = resolved_by
                e["resolved_at"] = datetime.now(timezone.utc).isoformat()
                found = True
        if found:
            self._save(entries)
        return found
