from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .models import ComputationStatus, Diagnostic, PropLadder, coherent_points, not_computable, sorted_over_points


class SurvivalPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    threshold: float
    survival_probability: float
    original_probability: float
    adjusted: bool = False
    residual: float = 0.0
    abs_residual: float = 0.0


class QuantileEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)

    quantile: str
    probability: float
    threshold: float | None = None
    status: ComputationStatus = ComputationStatus.NOT_COMPUTABLE
    diagnostic: Diagnostic | None = None


class BoundedMomentEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ComputationStatus
    mean: float | None = None
    variance: float | None = None
    skew: float | None = None
    quantile_count: int = 0
    lower_bound: float | None = None
    upper_bound: float | None = None
    diagnostic: Diagnostic | None = None


class SurvivalSurface(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ComputationStatus
    points: tuple[SurvivalPoint, ...] = ()
    weak_fit: bool = False
    diagnostics: tuple[Diagnostic, ...] = ()
    fit_error: float | None = None
    max_fit_error: float | None = None
    quantiles: dict[str, QuantileEstimate] = Field(default_factory=dict)
    median: float | None = None
    moments: BoundedMomentEstimate | None = None


def _not_computable_quantile(name: str, probability: float, code: str, message: str) -> QuantileEstimate:
    return QuantileEstimate(
        quantile=name,
        probability=probability,
        threshold=None,
        status=ComputationStatus.NOT_COMPUTABLE,
        diagnostic=Diagnostic(code=code, message=message),
    )


def _interpolate_quantile(points: tuple[SurvivalPoint, ...], probability: float, name: str) -> QuantileEstimate:
    target_survival = 1.0 - probability
    highest = points[0].survival_probability
    lowest = points[-1].survival_probability
    eps = 1e-12
    if target_survival > highest + eps or target_survival < lowest - eps:
        return _not_computable_quantile(
            name,
            probability,
            "OUTSIDE_OBSERVED_RANGE",
            "quantile target is outside observed threshold survival range; extrapolation is disabled",
        )
    for point in points:
        if abs(point.survival_probability - target_survival) <= 1e-12:
            return QuantileEstimate(quantile=name, probability=probability, threshold=point.threshold, status=ComputationStatus.COMPUTABLE)
    for left, right in zip(points, points[1:]):
        ls = left.survival_probability
        rs = right.survival_probability
        if ls >= target_survival >= rs and abs(ls - rs) > 1e-12:
            weight = (ls - target_survival) / (ls - rs)
            threshold = left.threshold + weight * (right.threshold - left.threshold)
            return QuantileEstimate(quantile=name, probability=probability, threshold=threshold, status=ComputationStatus.COMPUTABLE)
    return _not_computable_quantile(name, probability, "FLAT_SURFACE", "quantile falls on an unresolvable flat fitted segment")


def _quantiles(points: tuple[SurvivalPoint, ...]) -> dict[str, QuantileEstimate]:
    return {name: _interpolate_quantile(points, prob, name) for name, prob in (("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90))}


def _moments(points: tuple[SurvivalPoint, ...], quantiles: dict[str, QuantileEstimate]) -> BoundedMomentEstimate:
    computable = [q for q in quantiles.values() if q.status == ComputationStatus.COMPUTABLE and q.threshold is not None]
    if len(computable) < 3:
        return BoundedMomentEstimate(
            status=ComputationStatus.NOT_COMPUTABLE,
            diagnostic=Diagnostic(code="INSUFFICIENT_EVIDENCE", message="bounded moment estimates require at least three in-range quantiles"),
        )
    lower = points[0].threshold
    upper = points[-1].threshold
    values = [q.threshold for q in computable]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    skew = 0.0 if variance <= 1e-15 else sum(((value - mean) / variance**0.5) ** 3 for value in values) / len(values)
    return BoundedMomentEstimate(
        status=ComputationStatus.COMPUTABLE,
        mean=min(upper, max(lower, mean)),
        variance=variance,
        skew=skew,
        quantile_count=len(values),
        lower_bound=lower,
        upper_bound=upper,
    )


def reconstruct_survival(ladder: PropLadder) -> SurvivalSurface:
    points = sorted_over_points(ladder)
    ok, reason = coherent_points(points, min_points=2)
    if not ok:
        result = not_computable("INCOHERENT_LADDER", reason or "incoherent ladder")
        return SurvivalSurface(status=result.status, weak_fit=True, diagnostics=result.diagnostics)
    reconstructed: list[SurvivalPoint] = []
    running = 1.0
    weak_fit = False
    residuals: list[float] = []
    for threshold, probability in points:
        bounded = min(1.0, max(0.0, probability))
        fitted = min(running, bounded)
        residual = fitted - probability
        adjusted = abs(residual) > 1e-12
        weak_fit = weak_fit or adjusted
        residuals.append(residual)
        reconstructed.append(
            SurvivalPoint(
                threshold=threshold,
                survival_probability=fitted,
                original_probability=probability,
                adjusted=adjusted,
                residual=residual,
                abs_residual=abs(residual),
            )
        )
        running = fitted
    fit_error = sum(abs(value) for value in residuals) / len(residuals)
    max_fit_error = max(abs(value) for value in residuals)
    diagnostics = []
    if weak_fit:
        diagnostics.append(Diagnostic(code="WEAK_FIT_MONOTONIC_REPAIR", message="input probabilities were repaired to bounded non-increasing survival"))
    if fit_error > 0.025 or max_fit_error > 0.05:
        weak_fit = True
        diagnostics.append(Diagnostic(code="WEAK_FIT_RESIDUAL", message="surface residuals exceed weak-fit diagnostic tolerance"))
    final_points = tuple(reconstructed)
    quantiles = _quantiles(final_points)
    median = quantiles["p50"].threshold if quantiles["p50"].status == ComputationStatus.COMPUTABLE else None
    moments = _moments(final_points, quantiles)
    return SurvivalSurface(
        status=ComputationStatus.COMPUTABLE,
        points=final_points,
        weak_fit=weak_fit,
        diagnostics=tuple(diagnostics),
        fit_error=fit_error,
        max_fit_error=max_fit_error,
        quantiles=quantiles,
        median=median,
        moments=moments,
    )
