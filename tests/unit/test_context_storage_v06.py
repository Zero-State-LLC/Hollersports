from datetime import datetime, timezone

import pytest

from hollersports.context import ContextDerivation, ContextObservation, ContextStorageError, ContextStore, Provenance, TravelState, compute_travel_load


def observation(observation_id="ctx-1", observed_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)):
    return ContextObservation(
        observation_id=observation_id,
        event_id="event-1",
        entity_id="team-a",
        context_type="TRAVEL",
        observed_at=observed_at,
        source="fixture",
        source_hash=f"hash-{observation_id}",
        payload=TravelState(
            team_id="team-a", miles_last_72h=1200, timezone_delta_hours=2, rest_hours=28,
            controlled_sample_size=5, history_sample_size=10,
            provenance=[Provenance(source="fixture", observed_at=observed_at)],
        ),
    )


def test_context_store_replays_only_available_derivations(tmp_path):
    store = ContextStore(tmp_path)
    item = observation()
    fingerprint = store.append_observation(item)
    derivation = ContextDerivation(
        derivation_id="derived-1", observation_id=item.observation_id, observation_fingerprint=fingerprint,
        event_id=item.event_id, entity_id=item.entity_id, context_type=item.context_type,
        observed_at=item.observed_at, derived_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        result=compute_travel_load(item.payload),
    )
    store.append_derivation(derivation)

    early = store.latest_at_or_before(event_id="event-1", entity_id="team-a", context_type="TRAVEL", as_of=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc))
    assert early == (item, None)
    available = store.latest_at_or_before(event_id="event-1", entity_id="team-a", context_type="TRAVEL", as_of=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc))
    assert available == (item, derivation)


def test_context_observation_rejects_future_provenance_and_identity_mismatch():
    with pytest.raises(ValueError, match="postdate"):
        ContextObservation(
            observation_id="future", event_id="event-1", entity_id="team-a", context_type="TRAVEL",
            observed_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc), source="fixture", source_hash="hash",
            payload=TravelState(team_id="team-a", provenance=[Provenance(source="fixture", observed_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc))]),
        )
    with pytest.raises(ValueError, match="identity"):
        observation().model_copy(update={"entity_id": "team-b"}).__class__.model_validate(
            {**observation().model_dump(), "entity_id": "team-b"}
        )


def test_context_derivation_requires_matching_immutable_observation(tmp_path):
    store = ContextStore(tmp_path)
    item = observation()
    store.append_observation(item)
    bad = ContextDerivation(
        derivation_id="derived-1", observation_id=item.observation_id, observation_fingerprint="wrong",
        event_id=item.event_id, entity_id=item.entity_id, context_type=item.context_type,
        observed_at=item.observed_at, derived_at=item.observed_at, result=compute_travel_load(item.payload),
    )
    with pytest.raises(ContextStorageError, match="fingerprint"):
        store.append_derivation(bad)
