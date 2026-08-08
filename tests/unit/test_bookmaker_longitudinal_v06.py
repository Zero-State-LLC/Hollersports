from datetime import datetime, timezone

from hollersports.bookmaker import BookmakerQuote, LongitudinalStore, LongitudinalThresholds, MarketSnapshotV2, OutcomePrice, analyze_longitudinal_market


T = LongitudinalThresholds(minimum_probability_move=0.01, follow_window_seconds=600, minimum_pressure_imbalance=0.1, maximum_resistant_move=0.005)


def quote(book, minute, probability, *, tickets=None, handle=None, event_id="event-1", point=None):
    metadata = {}
    if tickets is not None: metadata["ticket_pct"] = tickets
    if handle is not None: metadata["handle_pct"] = handle
    return BookmakerQuote(bookmaker=book, event_id=event_id, market_id="market-1", market_type="MONEYLINE", fetched_at=datetime(2026, 1, 1, 10, minute, tzinfo=timezone.utc), source="fixture", source_hash=f"{event_id}-{book}-{minute}", outcomes=(OutcomePrice(selection="HOME", observed_probability=probability, point=point),), metadata=metadata)


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
    assert result.event_id == "event-1"
    assert result.market_type == "MONEYLINE"
    assert result.movement_status == "COMPUTED"
    assert result.lead_lag_status == "COMPUTED"
    assert result.pressure_status == "COMPUTED"
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
    assert result.movement_status == "NOT_COMPUTABLE"
    assert result.lead_lag_status == "NOT_COMPUTABLE"
    assert result.pressure_status == "NOT_COMPUTABLE"


def test_longitudinal_scopes_reused_market_id_to_one_event():
    rows = snapshots() + [
        MarketSnapshotV2(snapshot_id="other-1", captured_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc), event_id="event-2", market_type="MONEYLINE", quotes=(quote("c", 0, 0.20, event_id="event-2"),)),
        MarketSnapshotV2(snapshot_id="other-2", captured_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc), event_id="event-2", market_type="MONEYLINE", quotes=(quote("c", 5, 0.80, event_id="event-2"),)),
    ]
    ambiguous = analyze_longitudinal_market(rows, "market-1", "HOME", datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc), T)
    assert ambiguous.status == "NOT_COMPUTABLE"
    result = analyze_longitudinal_market(rows, "market-1", "HOME", datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc), T, event_id="event-1")
    assert result.status == "COMPUTED"
    assert {move.bookmaker for move in result.moves} == {"a", "b"}


def test_longitudinal_uses_nearest_predecessor_and_reports_threshold_velocity():
    rows = [
        MarketSnapshotV2(snapshot_id="c1", captured_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc), event_id="event-1", market_type="MONEYLINE", quotes=(quote("a", 0, 0.50, point=20), quote("b", 0, 0.50, point=20), quote("c", 0, 0.50, point=20))),
        MarketSnapshotV2(snapshot_id="c2", captured_at=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc), event_id="event-1", market_type="MONEYLINE", quotes=(quote("a", 2, 0.52, point=21), quote("b", 2, 0.50, point=20), quote("c", 2, 0.50, point=20))),
        MarketSnapshotV2(snapshot_id="c3", captured_at=datetime(2026, 1, 1, 10, 4, tzinfo=timezone.utc), event_id="event-1", market_type="MONEYLINE", quotes=(quote("a", 4, 0.52, point=21), quote("b", 4, 0.52, point=20), quote("c", 4, 0.50, point=20))),
        MarketSnapshotV2(snapshot_id="c4", captured_at=datetime(2026, 1, 1, 10, 6, tzinfo=timezone.utc), event_id="event-1", market_type="MONEYLINE", quotes=(quote("a", 6, 0.52, point=21), quote("b", 6, 0.52, point=20), quote("c", 6, 0.52, point=20))),
    ]
    result = analyze_longitudinal_market(rows, "market-1", "HOME", datetime(2026, 1, 1, 10, 7, tzinfo=timezone.utc), T, event_id="event-1")
    assert [(event.leader_book, event.follower_book) for event in result.lead_lag_events] == [("a", "b"), ("b", "c")]
    a_move = next(move for move in result.moves if move.bookmaker == "a" and move.threshold_delta == 1)
    assert a_move.threshold_velocity_per_hour == 30


def test_lead_lag_has_an_independent_minimum_sample_gate():
    gated = T.model_copy(update={"minimum_lead_events": 2})
    result = analyze_longitudinal_market(snapshots(), "market-1", "HOME", datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc), gated)
    assert result.status == "COMPUTED"
    assert result.lead_lag_status == "NOT_COMPUTABLE"
    assert "lead_lag" in result.metric_reasons


def test_longitudinal_persistence_detects_tamper(tmp_path):
    analysis = analyze_longitudinal_market(snapshots(), "market-1", "HOME", datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc), T)
    store = LongitudinalStore(tmp_path)
    record = store.append("analysis-1", datetime(2026, 1, 1, 10, 11, tzinfo=timezone.utc), analysis)
    assert store.integrity_issues() == []
    raw = store.path.read_text(encoding="utf-8").replace(record.analysis_fingerprint, "0" * 64)
    store.path.write_text(raw, encoding="utf-8")
    assert store.integrity_issues() == ["analysis fingerprint mismatch: analysis-1"]
