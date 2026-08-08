from datetime import datetime, timezone

import pytest

from hollersports.dependency import DependencyMethod, DependencyObservation, DependencyStorageError, DependencyStore, LegProbability


def observation(observation_id="dep-1", recorded_at=None):
    observed = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    return DependencyObservation(
        observation_id=observation_id, event_id="event-1", parlay_id="parlay-1",
        observed_at=observed, recorded_at=recorded_at or observed,
        source="fixture", source_hash=f"hash-{observation_id}",
        legs=(LegProbability(leg_id="a", marginal_probability=0.6), LegProbability(leg_id="b", marginal_probability=0.5)),
        method=DependencyMethod.INDEPENDENT, explicitly_allow_independence=True,
    )


def test_dependency_bundle_and_temporal_replay(tmp_path):
    store = DependencyStore(tmp_path)
    item = observation()
    analysis = store.derive(item, "analysis-1", datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc))
    store.append_bundle(item, analysis)
    early = store.latest_at_or_before("event-1", "parlay-1", datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc))
    assert early == (item, None)
    available = store.latest_at_or_before("event-1", "parlay-1", datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc))
    assert available == (item, analysis)
    assert analysis.analysis.joint.joint_probability == pytest.approx(0.3)
    assert store.integrity_issues() == []


def test_dependency_replay_excludes_post_hoc_recording(tmp_path):
    store = DependencyStore(tmp_path)
    item = observation(recorded_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    analysis = store.derive(item, "analysis-1", datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc))
    store.append_bundle(item, analysis)
    assert store.latest_at_or_before("event-1", "parlay-1", datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)) is None


def test_dependency_observation_rejects_duplicate_legs_dangling_edges_and_implicit_independence():
    raw = observation().model_dump()
    raw["legs"] = [raw["legs"][0], raw["legs"][0]]
    with pytest.raises(ValueError, match="unique"):
        DependencyObservation.model_validate(raw)
    raw = observation().model_dump()
    raw["explicitly_allow_independence"] = False
    with pytest.raises(ValueError, match="explicit"):
        DependencyObservation.model_validate(raw)


def test_dependency_store_rejects_tampered_deterministic_analysis(tmp_path):
    store = DependencyStore(tmp_path)
    item = observation()
    analysis = store.derive(item, "analysis-1", datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc))
    tampered_joint = analysis.analysis.joint.model_copy(update={"joint_probability": 0.2})
    tampered_analysis = analysis.analysis.model_copy(update={"joint": tampered_joint})
    tampered = analysis.model_copy(update={"analysis": tampered_analysis})
    with pytest.raises(DependencyStorageError, match="deterministic derivation"):
        store.append_bundle(item, tampered)
    assert store.observations() == []
