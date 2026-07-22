import tempfile
from pathlib import Path

from nookguard.owner_queue import OwnerQueue, should_queue_for_owner
from nookguard.schemas import RiskTier
from nookguard.state_machine import AssetState


def test_needs_owner_always_queues_regardless_of_tier():
    for tier in RiskTier:
        assert should_queue_for_owner(tier, AssetState.NEEDS_OWNER) is True


def test_tier3_always_queues_even_on_pass():
    assert should_queue_for_owner(RiskTier.TIER_3, AssetState.SEMANTIC_PASS) is True


def test_tier2_always_queues_even_on_pass():
    assert should_queue_for_owner(RiskTier.TIER_2, AssetState.SEMANTIC_PASS) is True


def test_tier1_queues_within_first_20_assets():
    assert should_queue_for_owner(RiskTier.TIER_1, AssetState.SEMANTIC_PASS, assets_seen_for_adapter=5) is True


def test_tier1_does_not_queue_past_first_20_assets():
    assert should_queue_for_owner(RiskTier.TIER_1, AssetState.SEMANTIC_PASS, assets_seen_for_adapter=25) is False


def test_tier1_queues_on_disagreement_regardless_of_count():
    assert should_queue_for_owner(RiskTier.TIER_1, AssetState.SEMANTIC_PASS,
                                   assets_seen_for_adapter=999, is_disagreement=True) is True


def test_tier0_queues_every_tenth_asset_within_first_50():
    assert should_queue_for_owner(RiskTier.TIER_0, AssetState.SEMANTIC_PASS, assets_seen_for_adapter=10) is True
    assert should_queue_for_owner(RiskTier.TIER_0, AssetState.SEMANTIC_PASS, assets_seen_for_adapter=11) is False


def test_tier0_does_not_queue_past_first_50():
    assert should_queue_for_owner(RiskTier.TIER_0, AssetState.SEMANTIC_PASS, assets_seen_for_adapter=60) is False


def test_owner_queue_enqueue_and_list_pending():
    d = Path(tempfile.mkdtemp())
    queue = OwnerQueue(d / "queue.json")
    queue.enqueue("asset-1", "cand-1", ["needs review"], "tier_2_identity_continuity", "needs_owner")
    pending = queue.list_pending()
    assert len(pending) == 1
    assert pending[0]["asset_id"] == "asset-1"
    assert pending[0]["status"] == "pending"


def test_owner_queue_resolve_moves_entry_out_of_pending():
    d = Path(tempfile.mkdtemp())
    queue = OwnerQueue(d / "queue.json")
    queue.enqueue("asset-1", "cand-1", ["needs review"], "tier_2_identity_continuity", "needs_owner")
    resolved = queue.resolve("asset-1", "cand-1", "approved", "maurice")
    assert resolved is True
    assert queue.list_pending() == []


def test_owner_queue_resolve_returns_false_for_unknown_entry():
    d = Path(tempfile.mkdtemp())
    queue = OwnerQueue(d / "queue.json")
    assert queue.resolve("nonexistent", "nonexistent", "approved", "maurice") is False


def test_owner_queue_persists_across_instances():
    d = Path(tempfile.mkdtemp())
    path = d / "queue.json"
    OwnerQueue(path).enqueue("asset-1", "cand-1", ["reason"], "tier_1_routine", "semantic_pass")
    assert len(OwnerQueue(path).list_pending()) == 1
