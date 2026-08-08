from hollersports.bookmaker import (
    BookmakerQuote,
    MarketSnapshotStore,
    MarketSnapshotV2,
    OutcomePrice,
)
from hollersports.bookmaker.devig import proportional_devig


def _quote(book="book-a", market_id="m1"):
    return BookmakerQuote(
        bookmaker=book,
        event_id="event-1",
        market_id=market_id,
        market_type="MONEYLINE",
        fetched_at="2026-01-01T10:00:00Z",
        source="fixture",
        outcomes=(
            OutcomePrice(selection="HOME", american_odds=-110),
            OutcomePrice(selection="AWAY", american_odds=-110),
        ),
    )


def test_devig_fair_probabilities_are_bounded_and_sum_to_one():
    fair = proportional_devig(_quote().outcomes)
    assert fair is not None
    assert all(0.0 <= value <= 1.0 for value in fair.values())
    assert abs(sum(fair.values()) - 1.0) < 1e-12


def test_market_memory_is_append_only_and_temporally_queryable(tmp_path):
    store = MarketSnapshotStore(tmp_path)
    early = MarketSnapshotV2(
        snapshot_id="snap-1",
        captured_at="2026-01-01T10:00:00Z",
        event_id="event-1",
        market_type="MONEYLINE",
        quotes=(_quote(),),
    )
    late = MarketSnapshotV2(
        snapshot_id="snap-2",
        captured_at="2026-01-01T11:00:00Z",
        event_id="event-1",
        market_type="MONEYLINE",
        quotes=(_quote(),),
    )
    first = store.append(early)
    store.append(late)
    replay = store.query(end_at="2026-01-01T10:30:00Z")
    assert [item.snapshot_id for item in replay] == ["snap-1"]
    assert first["fingerprint"] == replay[0].fingerprint
    assert len(store.path.read_text().splitlines()) == 2


def test_snapshot_rejects_execution_authority():
    try:
        MarketSnapshotV2(
            snapshot_id="snap-1",
            event_id="event-1",
            market_type="MONEYLINE",
            quotes=(_quote(),),
            execution_authority=True,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("market snapshot accepted execution authority")
