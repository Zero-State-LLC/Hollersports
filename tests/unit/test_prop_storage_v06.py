from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hollersports.props.models import PropLadder, PropThreshold
from hollersports.props.storage import (
    DerivedPropSurfaceObservation,
    DuplicateObservationError,
    PropLadderObservation,
    PropPersistenceStore,
    PropStorageError,
)
from hollersports.props.surface import reconstruct_survival


def _ladder_observation(observation_id: str, observed_at: datetime, *, threshold_offset: float = 0.0) -> PropLadderObservation:
    ladder = PropLadder(
        event_id="event-1",
        market="player_points",
        player="player-1",
        thresholds=(
            PropThreshold(threshold=19.5 + threshold_offset, fair_probability=0.56, source="fixture"),
            PropThreshold(threshold=24.5 + threshold_offset, fair_probability=0.42, source="fixture"),
        ),
    )
    return PropLadderObservation(
        observation_id=observation_id,
        market_id="market-1",
        book_id="book-a",
        event_id="event-1",
        player_id="player-1",
        player_name="Sample Player",
        stat_type="points",
        observed_at=observed_at,
        source="fixture://props/book-a/event-1/player-1/points",
        source_hash="sha256:source-fixture",
        ladder=ladder,
    )


def test_append_only_ladder_jsonl_rejects_duplicate_ids(tmp_path):
    store = PropPersistenceStore(tmp_path)
    observation = _ladder_observation("obs-1", datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc))

    fingerprint = store.append_ladder_observation(observation)

    assert fingerprint == observation.fingerprint
    assert store.ladders_path.read_text(encoding="utf-8").count("\n") == 1
    with pytest.raises(DuplicateObservationError):
        store.append_ladder_observation(observation)
    assert store.ladders_path.read_text(encoding="utf-8").count("\n") == 1


def test_temporal_query_returns_latest_observation_at_or_before_only(tmp_path):
    store = PropPersistenceStore(tmp_path)
    early = _ladder_observation("obs-early", datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc))
    middle = _ladder_observation("obs-middle", datetime(2026, 8, 8, 11, 0, tzinfo=timezone.utc), threshold_offset=1.0)
    future = _ladder_observation("obs-future", datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc), threshold_offset=2.0)
    for observation in (early, middle, future):
        store.append_ladder_observation(observation)

    found = store.latest_ladder_at_or_before(
        market_id="market-1",
        book_id="book-a",
        event_id="event-1",
        player_id="player-1",
        stat_type="points",
        as_of=datetime(2026, 8, 8, 11, 30, tzinfo=timezone.utc),
    )

    assert found == middle
    assert found is not None
    assert found.observation_id == "obs-middle"
    assert store.latest_ladder_at_or_before(
        market_id="market-1",
        book_id="book-a",
        event_id="event-1",
        player_id="player-1",
        stat_type="points",
        as_of=datetime(2026, 8, 8, 9, 59, tzinfo=timezone.utc),
    ) is None


def test_ladder_fingerprint_is_stable_across_roundtrip(tmp_path):
    store = PropPersistenceStore(tmp_path)
    observation = _ladder_observation("obs-1", datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc))
    written_fingerprint = store.append_ladder_observation(observation)

    reloaded = store.get_ladder_observation("obs-1")

    assert reloaded is not None
    assert reloaded.fingerprint == written_fingerprint
    assert reloaded.model_dump(mode="json") == observation.model_dump(mode="json")


def test_surface_persistence_references_ladder_fingerprint_and_never_derives_from_future(tmp_path):
    store = PropPersistenceStore(tmp_path)
    observation = _ladder_observation("obs-1", datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc))
    ladder_fingerprint = store.append_ladder_observation(observation)
    surface = DerivedPropSurfaceObservation(
        surface_id="surface-1",
        observation_id=observation.observation_id,
        ladder_fingerprint=ladder_fingerprint,
        market_id=observation.market_id,
        book_id=observation.book_id,
        event_id=observation.event_id,
        player_id=observation.player_id,
        player_name=observation.player_name,
        stat_type=observation.stat_type,
        observed_at=observation.observed_at,
        derived_at=datetime(2026, 8, 8, 10, 1, tzinfo=timezone.utc),
        surface=reconstruct_survival(observation.ladder),
    )

    surface_fingerprint = store.append_surface_observation(surface)

    stored_surfaces = store.iter_surface_observations()
    assert stored_surfaces == [surface]
    assert stored_surfaces[0].ladder_fingerprint == ladder_fingerprint
    assert stored_surfaces[0].fingerprint == surface_fingerprint
    assert store.get_ladder_observation("obs-1") == observation

    future_surface = surface.model_copy(update={"surface_id": "surface-2", "observed_at": datetime(2026, 8, 8, 10, 30, tzinfo=timezone.utc)})
    with pytest.raises(PropStorageError, match="observed_at must match"):
        store.append_surface_observation(future_surface)


def test_observed_at_must_be_timezone_aware():
    with pytest.raises(ValueError, match="timezone-aware"):
        _ladder_observation("obs-naive", datetime(2026, 8, 8, 10, 0))
