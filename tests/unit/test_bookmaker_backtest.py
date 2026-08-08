import math

import pytest

from hollersports.bookmaker.backtest import (
    BacktestRow,
    brier_score,
    book_pricing_error,
    clv_information_capture_ratio,
    compute_backtest_metrics,
    expected_calibration_error,
    fair_calibration_error,
    log_loss,
    verdict_discrimination_by_group,
)


def _row(idx, p, outcome, *, fair=0.5, book=0.52, close=0.58, verdict="PASS", group="g1"):
    return BacktestRow(
        row_id=f"row-{idx}",
        event_id=f"event-{idx}",
        market_type="MONEYLINE",
        selection="HOME",
        predicted_probability=p,
        outcome=outcome,
        prediction_at="2026-01-01T10:00:00Z",
        closing_at="2026-01-01T12:00:00Z",
        settled_at="2026-01-01T18:00:00Z",
        fair_probability=fair,
        book_probability=book,
        closing_probability=close,
        verdict=verdict,
        group=group,
    )


def test_backtest_metrics_are_evidence_bound_and_computable():
    rows = [
        _row(1, 0.70, 1, fair=0.65, book=0.60, close=0.68, verdict="PASS"),
        _row(2, 0.20, 0, fair=0.25, book=0.30, close=0.28, verdict="FADE"),
    ]

    brier = brier_score(rows)
    assert brier.status == "COMPUTABLE"
    assert brier.sample_size == 2
    assert brier.value == pytest.approx(((0.7 - 1.0) ** 2 + (0.2 - 0.0) ** 2) / 2)

    ll = log_loss(rows)
    assert ll.sample_size == 2
    assert ll.value == pytest.approx((-(math.log(0.7) + math.log(0.8))) / 2)

    ece = expected_calibration_error(rows, bins=2)
    assert ece.status == "COMPUTABLE"
    assert ece.sample_size == 2

    assert fair_calibration_error(rows).value == pytest.approx((abs(0.70 - 0.65) + abs(0.20 - 0.25)) / 2)
    assert book_pricing_error(rows).value == pytest.approx((abs(0.70 - 0.60) + abs(0.20 - 0.30)) / 2)
    assert clv_information_capture_ratio(rows).value == pytest.approx((0.05 + 0.05) / (0.03 + 0.03))

    discrimination = verdict_discrimination_by_group(rows)
    assert discrimination[0].status == "COMPUTABLE"
    assert discrimination[0].group == "g1"
    assert discrimination[0].sample_size == 2
    assert discrimination[0].value == pytest.approx(1.0)


def test_metrics_fail_closed_when_required_evidence_is_absent():
    rows = [
        BacktestRow(
            row_id="pending-1",
            event_id="event-1",
            market_type="MONEYLINE",
            selection="HOME",
            predicted_probability=0.55,
            prediction_at="2026-01-01T10:00:00Z",
        )
    ]

    metrics = compute_backtest_metrics(rows, min_samples=2)
    assert metrics
    assert all(metric.status == "NOT_COMPUTABLE" for metric in metrics)
    assert all(metric.sample_size >= 0 for metric in metrics)
    assert {metric.name for metric in metrics} >= {
        "brier",
        "log_loss",
        "ece",
        "fair_calibration_error",
        "book_pricing_error",
        "clv_information_capture_ratio",
        "verdict_discrimination",
    }


def test_clv_requires_closing_prices_and_temporal_evidence():
    row = BacktestRow(
        row_id="settled-no-close",
        event_id="event-1",
        market_type="MONEYLINE",
        selection="HOME",
        predicted_probability=0.55,
        outcome=1,
        prediction_at="2026-01-01T10:00:00Z",
        settled_at="2026-01-01T18:00:00Z",
        fair_probability=0.50,
    )

    metric = clv_information_capture_ratio([row])
    assert metric.status == "NOT_COMPUTABLE"
    assert metric.sample_size == 0
    assert "closing" in metric.reason


def test_backtest_row_rejects_future_leakage_and_authority():
    with pytest.raises(ValueError, match="prediction_at < closing_at <= settled_at"):
        BacktestRow(
            row_id="leaky",
            event_id="event-1",
            market_type="MONEYLINE",
            selection="HOME",
            predicted_probability=0.55,
            outcome=1,
            prediction_at="2026-01-01T13:00:00Z",
            closing_at="2026-01-01T12:00:00Z",
            settled_at="2026-01-01T18:00:00Z",
        )

    with pytest.raises(ValueError, match="no capital/execution authority"):
        BacktestRow(
            row_id="authority",
            event_id="event-1",
            market_type="MONEYLINE",
            selection="HOME",
            predicted_probability=0.55,
            prediction_at="2026-01-01T10:00:00Z",
            execution_authority=True,
        )
