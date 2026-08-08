import json
from datetime import datetime, timezone

from hollersports.backfill import audit_backfill_readiness


def snapshot(event_id="event-1"):
    return {
        "schema_version": "market_snapshot.v2", "snapshot_id": "snapshot-1",
        "captured_at": "2026-01-01T20:00:00Z", "event_id": event_id,
        "market_type": "MONEYLINE", "quotes": [{
            "bookmaker": "book-a", "event_id": event_id, "market_id": "market-1",
            "market_type": "MONEYLINE", "outcomes": [
                {"selection": "HOME", "observed_probability": 0.55},
                {"selection": "AWAY", "observed_probability": 0.50},
            ], "fetched_at": "2026-01-01T19:59:00Z", "source": "archive",
            "source_hash": "market-source-hash",
        }],
    }


def settlement(recorded_at="2026-01-02T00:00:00Z", event_id="event-1"):
    return {
        "event_id": event_id, "market_id": "market-1", "status": "WIN",
        "recorded_at": recorded_at, "source_hash": "settlement-source-hash",
    }


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_empty_audit_is_read_only_and_reports_v06_blockers(tmp_path):
    data_root = tmp_path / "absent-data"
    fixtures_root = tmp_path / "absent-fixtures"
    report = audit_backfill_readiness(
        data_root, fixtures_root, generated_at=datetime(2026, 1, 3, tzinfo=timezone.utc)
    )
    assert report.read_only is True
    assert report.v06_temporal_backfill_possible is False
    assert report.v05_fixture_backfill_possible is False
    assert "no provenance-valid market_snapshot.v2 history" in report.blockers
    assert not data_root.exists()
    assert not fixtures_root.exists()


def test_audit_recognizes_temporally_joinable_v06_evidence_and_v05_fixtures(tmp_path):
    data_root = tmp_path / "data"
    fixtures_root = tmp_path / "fixtures"
    write_jsonl(data_root / "bookmaker" / "market_snapshot.v2.jsonl", [snapshot()])
    write_jsonl(data_root / "ledgers" / "settlements_history.jsonl", [settlement()])
    fixture = fixtures_root / "day001"
    fixture.mkdir(parents=True)
    (fixture / "meta.json").write_text('{"run_id":"day001"}', encoding="utf-8")
    (fixture / "odds_records.json").write_text('[{"event_id":"event-1"}]', encoding="utf-8")
    (fixture / "results.json").write_text('[{"event_id":"event-1"}]', encoding="utf-8")

    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file())
    report = audit_backfill_readiness(data_root, fixtures_root)
    after = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file())

    assert before == after
    assert report.v05_fixture_backfill_possible is True
    assert report.v06_temporal_backfill_possible is True
    assert report.overlapping_market_settlement_events == 1
    assert report.temporally_ordered_market_settlement_events == 1
    assert report.inventories["market_snapshots"].valid_rows == 1
    assert report.inventories["settlements"].valid_rows == 1


def test_audit_blocks_settlement_timestamped_before_market_observation(tmp_path):
    data_root = tmp_path / "data"
    write_jsonl(data_root / "bookmaker" / "market_snapshot.v2.jsonl", [snapshot()])
    write_jsonl(data_root / "ledgers" / "settlements_history.jsonl", [settlement("2026-01-01T19:00:00Z")])
    report = audit_backfill_readiness(data_root, tmp_path / "fixtures")
    assert report.overlapping_market_settlement_events == 1
    assert report.temporally_ordered_market_settlement_events == 0
    assert report.v06_temporal_backfill_possible is False
    assert "overlapping settlements are timestamped before their market observations" in report.blockers


def test_audit_rejects_legacy_settlements_without_provenance_hash(tmp_path):
    data_root = tmp_path / "data"
    write_jsonl(data_root / "bookmaker" / "market_snapshot.v2.jsonl", [snapshot()])
    legacy = settlement()
    legacy.pop("source_hash")
    write_jsonl(data_root / "ledgers" / "settlements_history.jsonl", [legacy])
    report = audit_backfill_readiness(data_root, tmp_path / "fixtures")
    assert report.inventories["settlements"].valid_rows == 0
    assert report.v06_temporal_backfill_possible is False
