import tempfile
from pathlib import Path

from nookguard.ledger import Ledger


def test_append_and_read_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        ledger = Ledger(Path(d) / "events.jsonl")
        e = ledger.append(
            run_id="run1", event_type="asset.spec_locked", actor_role="planner",
            payload={"asset_id": "a1"}, asset_id="a1", actor_session_id="s1",
        )
        events = list(ledger.read_all())
        assert len(events) == 1
        assert events[0].event_id == e.event_id
        assert events[0].asset_id == "a1"


def test_ledger_is_append_only_and_ordered():
    with tempfile.TemporaryDirectory() as d:
        ledger = Ledger(Path(d) / "events.jsonl")
        for i in range(3):
            ledger.append(run_id="run1", event_type=f"evt{i}", actor_role="x", payload={"i": i})
        events = list(ledger.read_all())
        assert [e.payload["i"] for e in events] == [0, 1, 2]


def test_verify_integrity_detects_tamper():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "events.jsonl"
        ledger = Ledger(path)
        e = ledger.append(run_id="run1", event_type="x", actor_role="y", payload={"a": 1})
        assert ledger.verify_integrity() == []

        raw = path.read_text().replace('"a":1', '"a":999')
        path.write_text(raw)
        assert e.event_id in ledger.verify_integrity()
