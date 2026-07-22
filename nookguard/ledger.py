"""Append-only event ledger. JSON-lines file for now (Commit 14 migrates the
storage backend to Cloudflare D1 per Appendix H's SQL sketch, but the schema
and the append-only contract stay the same — nothing here should assume the
file backend specifically)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Iterator, Optional

from .hashing import sha256_canonical_json
from .schemas import Event, utcnow_iso


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(
        self,
        *,
        run_id: str,
        event_type: str,
        actor_role: str,
        payload: dict[str, Any],
        asset_id: Optional[str] = None,
        actor_session_id: Optional[str] = None,
    ) -> Event:
        event = Event(
            event_id=str(uuid.uuid4()),
            run_id=run_id,
            asset_id=asset_id,
            event_type=event_type,
            actor_role=actor_role,
            actor_session_id=actor_session_id,
            payload=payload,
            payload_sha256=sha256_canonical_json(payload),
            created_at=utcnow_iso(),
        )
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
        return event

    def read_all(self) -> Iterator[Event]:
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield Event.model_validate(json.loads(line))

    def for_asset(self, asset_id: str) -> list[Event]:
        return [e for e in self.read_all() if e.asset_id == asset_id]

    def for_run(self, run_id: str) -> list[Event]:
        return [e for e in self.read_all() if e.run_id == run_id]

    def verify_integrity(self) -> list[str]:
        """Recompute payload_sha256 for every event and return event_ids whose
        stored hash no longer matches — the ledger's own tamper check."""
        bad: list[str] = []
        for event in self.read_all():
            if sha256_canonical_json(event.payload) != event.payload_sha256:
                bad.append(event.event_id)
        return bad
