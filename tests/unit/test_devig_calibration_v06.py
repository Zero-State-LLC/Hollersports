from datetime import datetime, timezone

import pytest

from hollersports.bookmaker import DevigCalibrationRow, compare_devig_methods


def row(row_id, winner, *, available_at="2026-01-02T00:00:00Z", bookmaker="book-a"):
    return DevigCalibrationRow(
        row_id=row_id,
        bookmaker=bookmaker,
        sport="NBA",
        market_class="NBA/MONEYLINE",
        odds_bucket="EVEN",
        outcomes=(
            {"selection": "HOME", "observed_probability": 0.60},
            {"selection": "AWAY", "observed_probability": 0.50},
        ),
        winning_selection=winner,
        observed_at="2026-01-01T20:00:00Z",
        available_at=available_at,
        source="settlement",
        source_hash=f"hash-{row_id}",
    )


def compare(rows, minimum_sample=2):
    return compare_devig_methods(
        rows,
        bookmaker="book-a",
        sport="NBA",
        market_class="NBA/MONEYLINE",
        odds_bucket="EVEN",
        as_of=datetime(2026, 1, 2, 1, tzinfo=timezone.utc),
        minimum_sample=minimum_sample,
        method_parameters={"SHIN": {"z": 0.02}},
    )


def test_devig_comparison_selects_only_a_method_that_beats_raw_brier():
    result = compare([row("one", "HOME"), row("two", "AWAY")])
    assert result.status == "COMPUTED"
    assert result.preferred_method in {"MULTIPLICATIVE", "ADDITIVE", "POWER", "SHIN"}
    assert result.improvement_over_raw_brier > 0
    assert all(item.sample_size == 2 for item in result.methods)
    assert result.capital_authority is False


def test_devig_comparison_excludes_future_and_wrong_market_evidence():
    future = row("future", "HOME", available_at="2026-01-03T00:00:00Z")
    other = row("other", "HOME", bookmaker="book-b")
    result = compare([row("one", "HOME"), future, other])
    assert result.status == "NOT_COMPUTABLE"
    assert result.raw_implied.sample_size == 1
    assert result.evidence_row_ids == ("one",)


def test_devig_comparison_rejects_duplicate_evidence_identity():
    result = compare([row("same", "HOME"), row("same", "AWAY")])
    assert result.status == "NOT_COMPUTABLE"
    assert result.reasons == ("duplicate calibration row_id",)


def test_calibration_row_rejects_settlement_available_before_observation():
    with pytest.raises(ValueError, match="available_at cannot precede"):
        row("bad", "HOME", available_at="2025-12-31T00:00:00Z")


def test_invalid_method_parameters_fail_that_method_closed():
    result = compare_devig_methods(
        [row("one", "HOME"), row("two", "AWAY")], bookmaker="book-a", sport="NBA",
        market_class="NBA/MONEYLINE", odds_bucket="EVEN",
        as_of=datetime(2026, 1, 2, 1, tzinfo=timezone.utc), minimum_sample=2,
        method_parameters={"SHIN": {"unknown": 1}},
    )
    shin = next(item for item in result.methods if item.method == "SHIN")
    assert shin.status == "NOT_COMPUTABLE"
    assert result.status == "COMPUTED"
