from datetime import datetime, timezone

from hollersports.bookmaker import BookmakerQuote, LongitudinalStore, LongitudinalThresholds, MarketSnapshotV2, OutcomePrice, analyze_longitudinal_market


T = LongitudinalThresholds(minimum_probability_move=0.01, follow_window_seconds=600, minimum_pressure_imbalance=0.1, maximum_resistant_move=0.005)


def quote(book, minute, probability, *, tickets=None, handle=None):
    metadata = {}
    if tickets is not None: metadata["ticket_pct"] = tickets
    if handle is not None: metadata["handle_pct"] = handle
    return BookmakerQuote(bookmaker=book, event_id="event-1", market_id="market-1", market_type="MONEYLINE", fetched_at=datetime(2026, 1, 1, 10, minute, tzinfo=timezone.utc), source="fixture", source_hash=f"{book}-{minute}", outcomes=(OutcomePrice(selection="HOME", observed_probability=probability),), metadata=metadata)


def snapshots():
    return [
        MarketSnapshotV2(snapshot_id="s1", captured_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc), event_id="event-1", market_type="MONEYLINE", quotes=(quote("a", 0, 0.50), quote("b", 0, 0.50))),
        MarketSnapshotV2(snapshot_id="s2", captured_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc), event_id="event-1", market_type="MONEYLINE", quotes=(quote("a", 5, 0.53, tickets=0.4, handle=0.6), quote("b", 5, 0.50, tickets=0.3, handle=0.5))),
        MarketSnapshotV2(snapshot_id="s3", captured_at=datetime(2026, 1, 1, 10, 8, tzinfo=timezone.utc), event_id="event-1", market_type="MONEYLINE", quotes=(quote("a", 8, 0.53), quote("b", 8, 0.53))),
    ]


def test_longitudinal_analysis_identifies_leader_follow_and_observational_pressure():
    result = analyze_longitudinal_market(snapshots(), "market-1", "HOME", datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc), T)
    assert result.status == "COMPUTED"
    assert result.probability_basis == "RAW_IMPLIED_OBSERVATION"
    assert result.leader_counts == {"a": 1}
    assert result.follow_counts == {"b": 1}
    event = result.lead_lag_events[0]
    assert event.lag_seconds == 180
    assert all(item.causal_attribution == "UNKNOWN" for item in result.pressure)
    assert any(item.resistance_observed for item in result.pressure if item.bookmaker == "b")


def test_longitudinal_analysis_respects_as_of_and_fails_closed_without_moves():
    result = analyze_longitudinal_market(snapshots(), "market-1", "HOME", datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc), T)
    assert result.status == "NOT_COMPUTABLE"
    assert len(result.snapshot_fingerprints) == 1


def test_longitudinal_persistence_detects_tamper(tmp_path):
    analysis = analyze_longitudinal_market(snapshots(), "market-1", "HOME", datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc), T)
    store = LongitudinalStore(tmp_path)
    record = store.append("analysis-1", datetime(2026, 1, 1, 10, 11, tzinfo=timezone.utc), analysis)
    assert store.integrity_issues() == []
    raw = store.path.read_text(encoding="utf-8").replace(record.analysis_fingerprint, "0" * 64)
    store.path.write_text(raw, encoding="utf-8")
    assert store.integrity_issues() == ["analysis fingerprint mismatch: analysis-1"]
