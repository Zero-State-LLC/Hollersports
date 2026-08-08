from hollersports.bookmaker import BookmakerQuote, MarketSnapshotStore, MarketSnapshotV2, OutcomePrice


def _quote(fetched_at: str) -> BookmakerQuote:
    return BookmakerQuote(
        bookmaker="book-a",
        event_id="event-1",
        market_id="market-1",
        market_type="MONEYLINE",
        fetched_at=fetched_at,
        source="fixture",
        source_hash="fixture-sha256",
        outcomes=(
            OutcomePrice(selection="HOME", american_odds=-110),
            OutcomePrice(selection="AWAY", american_odds=-110),
        ),
    )


def test_snapshot_rejects_observation_after_prediction_time():
    try:
        MarketSnapshotV2(
            snapshot_id="future-leak",
            captured_at="2026-01-01T10:00:00Z",
            event_id="event-1",
            market_type="MONEYLINE",
            quotes=(_quote("2026-01-01T10:00:01Z"),),
        )
    except ValueError as exc:
        assert "fetched_at cannot be later" in str(exc)
    else:
        raise AssertionError("future observation was admitted into a historical snapshot")


def test_temporal_replay_excludes_later_snapshot(tmp_path):
    store = MarketSnapshotStore(tmp_path)
    for snapshot_id, timestamp in (
        ("early", "2026-01-01T10:00:00Z"),
        ("late", "2026-01-01T11:00:00Z"),
    ):
        store.append(
            MarketSnapshotV2(
                snapshot_id=snapshot_id,
                captured_at=timestamp,
                event_id="event-1",
                market_type="MONEYLINE",
                quotes=(_quote("2026-01-01T10:00:00Z"),),
            )
        )
    replay = store.query(end_at="2026-01-01T10:30:00Z")
    assert [snapshot.snapshot_id for snapshot in replay] == ["early"]
