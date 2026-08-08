import pytest

from hollersports.props import (
    ComputationStatus,
    PropLadder,
    PropThreshold,
    compute_curvature,
    compute_tail_tax,
    pairwise_distribution_conflicts,
    reconstruct_survival,
)


def ladder(name="book-a", probs=(0.90, 0.75, 0.50, 0.25, 0.10)):
    return PropLadder(
        event_id=f"event-{name}",
        market="POINTS",
        player="player-1",
        thresholds=tuple(
            PropThreshold(threshold=float(threshold), fair_probability=probability, source=name)
            for threshold, probability in zip((10, 20, 30, 40, 50), probs)
        ),
    )


def test_surface_adds_residuals_fit_error_quantiles_and_bounded_moments():
    surface = reconstruct_survival(ladder())

    assert surface.status == ComputationStatus.COMPUTABLE
    assert surface.weak_fit is False
    assert surface.fit_error == pytest.approx(0.0)
    assert surface.max_fit_error == pytest.approx(0.0)
    assert [point.residual for point in surface.points] == [0.0] * 5
    assert set(surface.quantiles) == {"p10", "p25", "p50", "p75", "p90"}
    assert surface.quantiles["p10"].threshold == pytest.approx(10.0)
    assert surface.quantiles["p25"].threshold == pytest.approx(20.0)
    assert surface.quantiles["p50"].threshold == pytest.approx(30.0)
    assert surface.quantiles["p75"].threshold == pytest.approx(40.0)
    assert surface.quantiles["p90"].threshold == pytest.approx(50.0)
    assert surface.median == pytest.approx(30.0)
    assert surface.moments is not None
    assert surface.moments.status == ComputationStatus.COMPUTABLE
    assert 10.0 <= surface.moments.mean <= 50.0
    assert surface.moments.variance == pytest.approx(200.0)
    assert surface.moments.skew == pytest.approx(0.0)
    assert surface.moments.quantile_count == 5


def test_quantiles_and_moments_do_not_extrapolate_beyond_observed_range():
    surface = reconstruct_survival(ladder(probs=(0.70, 0.60, 0.55, 0.45, 0.40)))

    assert surface.quantiles["p10"].status == ComputationStatus.NOT_COMPUTABLE
    assert surface.quantiles["p10"].threshold is None
    assert surface.quantiles["p90"].status == ComputationStatus.NOT_COMPUTABLE
    assert surface.quantiles["p90"].threshold is None
    assert surface.median is not None
    assert surface.moments is not None
    assert surface.moments.status == ComputationStatus.NOT_COMPUTABLE
    assert surface.moments.mean is None


def test_monotonic_repair_records_observation_residuals_and_weak_fit_diagnostics():
    surface = reconstruct_survival(ladder(probs=(0.60, 0.64, 0.30, 0.20, 0.10)))

    assert surface.weak_fit is True
    assert surface.fit_error == pytest.approx(0.008)
    assert surface.max_fit_error == pytest.approx(0.04)
    assert surface.points[1].adjusted is True
    assert surface.points[1].residual == pytest.approx(-0.04)
    assert any(diagnostic.code == "WEAK_FIT_MONOTONIC_REPAIR" for diagnostic in surface.diagnostics)


def test_adjacent_curvature_and_tail_tax_classifications_are_reported():
    curv = compute_curvature(ladder(probs=(0.90, 0.75, 0.50, 0.25, 0.10)))
    tax = compute_tail_tax(ladder(probs=(0.90, 0.75, 0.50, 0.25, 0.10)))

    assert curv.status == ComputationStatus.COMPUTABLE
    assert "adjacent_curvature_max" in curv.metrics
    assert any(diagnostic.code.startswith("CURVATURE_") for diagnostic in curv.diagnostics)
    assert tax.status == ComputationStatus.COMPUTABLE
    assert "tail_drop" in tax.metrics
    assert any(diagnostic.code.startswith("TAIL_TAX_") for diagnostic in tax.diagnostics)


def test_pairwise_named_distribution_conflicts_preserve_sources():
    conflicts = pairwise_distribution_conflicts(
        {
            "book-a": ladder("book-a", probs=(0.90, 0.75, 0.50, 0.25, 0.10)),
            "book-b": ladder("book-b", probs=(0.88, 0.70, 0.52, 0.22, 0.12)),
            "model": ladder("model", probs=(0.91, 0.73, 0.48, 0.28, 0.11)),
        }
    )

    names = {(conflict.left_source, conflict.right_source) for conflict in conflicts}
    assert names == {("book-a", "book-b"), ("book-a", "model"), ("book-b", "model")}
    assert all(conflict.status == ComputationStatus.COMPUTABLE for conflict in conflicts)
    assert all(conflict.shared_thresholds == 5 for conflict in conflicts)
    assert all(conflict.mean_abs_conflict is not None for conflict in conflicts)
