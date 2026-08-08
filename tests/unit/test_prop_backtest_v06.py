from datetime import datetime, timezone

import pytest

from hollersports.props import PropSurfaceBacktestRow, backtest_prop_surfaces


def row(row_id, actual, *, points=None, available_at="2026-01-02T00:00:00Z", model_id="prop-model-v1"):
    return PropSurfaceBacktestRow(
        row_id=row_id, event_id=f"event-{row_id}", player_id=f"player-{row_id}", stat_type="POINTS",
        market_class="NBA/PLAYER_PROP/POINTS", model_id=model_id,
        points=points or (
            {"threshold": 10, "survival_probability": 0.75},
            {"threshold": 20, "survival_probability": 0.50},
            {"threshold": 30, "survival_probability": 0.25},
        ),
        actual_value=actual, prediction_evidence_at="2026-01-01T19:59:00Z",
        predicted_at="2026-01-01T20:00:00Z", available_at=available_at,
        prediction_source="surface-model", prediction_source_hash=f"model-{row_id}",
        settlement_source="settlement", settlement_source_hash=f"settled-{row_id}",
    )


def backtest(rows, minimum_sample=4):
    return backtest_prop_surfaces(
        rows, market_class="NBA/PLAYER_PROP/POINTS", model_id="prop-model-v1",
        as_of=datetime(2026, 1, 2, 1, tzinfo=timezone.utc), minimum_sample=minimum_sample,
        calibration_bins=4,
    )


def test_prop_surface_backtest_scores_calibration_monotonicity_and_crps():
    result = backtest([row("1", 35), row("2", 25), row("3", 15), row("4", 5)])
    assert result.status == "COMPUTED"
    assert result.monotonic_violation_rate.value == 0
    assert result.calibration_error.value == 0
    assert result.threshold_forecast_count == 12
    assert result.brier.value >= 0
    assert 0 <= result.discrete_crps.value <= 1
    assert result.advisory_mode == "ADVISORY_ONLY"


def test_prop_surface_backtest_reports_probability_inversions():
    inverted = (
        {"threshold": 10, "survival_probability": 0.4},
        {"threshold": 20, "survival_probability": 0.6},
    )
    result = backtest([row("bad", 25, points=inverted)], minimum_sample=1)
    assert result.status == "COMPUTED"
    assert result.monotonic_violation_rate.value == 1


def test_prop_surface_backtest_excludes_future_and_other_model_rows():
    result = backtest([
        row("usable", 25),
        row("future", 25, available_at="2026-01-03T00:00:00Z"),
        row("other", 25, model_id="other-model"),
    ], minimum_sample=2)
    assert result.status == "NOT_COMPUTABLE"
    assert result.row_count == 1
    assert result.evidence_row_ids == ("usable",)


def test_prop_surface_backtest_rejects_post_prediction_evidence_and_duplicate_thresholds():
    payload = row("late", 25).model_dump()
    payload["prediction_evidence_at"] = "2026-01-01T20:01:00Z"
    with pytest.raises(ValueError, match="cannot postdate prediction"):
        PropSurfaceBacktestRow.model_validate(payload)
    payload = row("duplicate", 25).model_dump()
    payload["points"] = [
        {"threshold": 10, "survival_probability": 0.5},
        {"threshold": 10, "survival_probability": 0.4},
    ]
    with pytest.raises(ValueError, match="thresholds must be unique"):
        PropSurfaceBacktestRow.model_validate(payload)
