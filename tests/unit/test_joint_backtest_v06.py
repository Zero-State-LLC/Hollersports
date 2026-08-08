from datetime import datetime, timezone

import pytest

from hollersports.dependency import JointBacktestRow, backtest_joint_probabilities


def row(row_id, outcome, *, available_at="2026-01-02T00:00:00Z", method="EMPIRICAL_CONDITIONAL"):
    return JointBacktestRow(
        row_id=row_id, event_id=f"event-{row_id}", market_class="NBA/SAME_GAME_PARLAY",
        leg_marginals=(0.5, 0.5), independent_probability=0.25,
        modeled_joint_probability=0.4, modeled_method=method, outcome=outcome,
        model_id="joint-model-v1", prediction_evidence_at="2026-01-01T19:59:00Z",
        predicted_at="2026-01-01T20:00:00Z", available_at=available_at,
        prediction_source="model-registry", prediction_source_hash=f"model-hash-{row_id}",
        source="settlement", source_hash=f"hash-{row_id}",
    )


def backtest(rows, minimum_sample=5):
    return backtest_joint_probabilities(
        rows, market_class="NBA/SAME_GAME_PARLAY", modeled_method="EMPIRICAL_CONDITIONAL",
        model_id="joint-model-v1",
        as_of=datetime(2026, 1, 2, 1, tzinfo=timezone.utc), minimum_sample=minimum_sample,
    )


def test_modeled_joint_is_scored_against_explicit_independence():
    result = backtest([row("1", 1), row("2", 1), row("3", 0), row("4", 0), row("5", 0)])
    assert result.status == "COMPUTED"
    assert result.modeled_beats_independence is True
    assert result.log_loss_improvement > 0
    assert result.modeled_log_loss.value < result.independent_log_loss.value
    assert result.advisory_mode == "ADVISORY_ONLY"
    assert result.execution_authority is False


def test_joint_backtest_excludes_future_and_other_method_rows():
    result = backtest([
        row("usable", 1),
        row("future", 1, available_at="2026-01-03T00:00:00Z"),
        row("other", 1, method="DRIVER"),
    ], minimum_sample=2)
    assert result.status == "NOT_COMPUTABLE"
    assert result.evidence_row_ids == ("usable",)
    assert result.independent_log_loss.sample_size == 1


def test_joint_backtest_rejects_duplicate_evidence_identity():
    result = backtest([row("same", 1), row("same", 0)], minimum_sample=2)
    assert result.status == "NOT_COMPUTABLE"
    assert result.reasons == ("duplicate joint backtest row_id",)


def test_joint_backtest_rejects_mixed_leg_counts():
    three_leg = row("three", 0).model_copy(update={
        "leg_marginals": (0.5, 0.5, 0.5), "independent_probability": 0.125,
    })
    result = backtest([row("two", 1), three_leg], minimum_sample=2)
    assert result.status == "NOT_COMPUTABLE"
    assert result.reasons == ("joint backtest cannot mix leg counts",)


def test_joint_backtest_row_enforces_probability_invariants():
    with pytest.raises(ValueError, match="product"):
        JointBacktestRow(
            row_id="bad", event_id="event", market_class="NBA/SGP", leg_marginals=(0.5, 0.5),
            independent_probability=0.3, modeled_joint_probability=0.4, modeled_method="MODEL", outcome=1,
            model_id="model", prediction_evidence_at="2026-01-01T19:59:00Z",
            predicted_at="2026-01-01T20:00:00Z", available_at="2026-01-02T00:00:00Z",
            prediction_source="model-registry", prediction_source_hash="model-hash",
            source="settlement", source_hash="hash",
        )
    with pytest.raises(ValueError, match="cannot exceed a marginal"):
        JointBacktestRow(
            row_id="bad-2", event_id="event", market_class="NBA/SGP", leg_marginals=(0.5, 0.5),
            independent_probability=0.25, modeled_joint_probability=0.6, modeled_method="MODEL", outcome=1,
            model_id="model", prediction_evidence_at="2026-01-01T19:59:00Z",
            predicted_at="2026-01-01T20:00:00Z", available_at="2026-01-02T00:00:00Z",
            prediction_source="model-registry", prediction_source_hash="model-hash",
            source="settlement", source_hash="hash",
        )


def test_joint_backtest_rejects_post_prediction_model_evidence():
    with pytest.raises(ValueError, match="cannot postdate prediction"):
        JointBacktestRow.model_validate(row("late-model", 1).model_dump() | {
            "prediction_evidence_at": "2026-01-01T20:01:00Z",
        })
