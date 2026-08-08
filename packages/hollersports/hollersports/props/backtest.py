from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PropSurfaceForecastPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    threshold: float
    survival_probability: float = Field(ge=0, le=1)


class PropSurfaceBacktestRow(BaseModel):
    """One pre-event survival surface paired with a subsequently settled result."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    row_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    player_id: str = Field(min_length=1)
    stat_type: str = Field(min_length=1)
    market_class: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    points: tuple[PropSurfaceForecastPoint, ...] = Field(min_length=2)
    actual_value: float
    prediction_evidence_at: datetime
    predicted_at: datetime
    available_at: datetime
    prediction_source: str = Field(min_length=1)
    prediction_source_hash: str = Field(min_length=1)
    settlement_source: str = Field(min_length=1)
    settlement_source_hash: str = Field(min_length=1)
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("prediction_evidence_at", "predicted_at", "available_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent(self) -> "PropSurfaceBacktestRow":
        thresholds = [point.threshold for point in self.points]
        if len(set(thresholds)) != len(thresholds):
            raise ValueError("surface thresholds must be unique")
        if self.prediction_evidence_at > self.predicted_at:
            raise ValueError("prediction evidence cannot postdate prediction")
        if self.available_at <= self.predicted_at:
            raise ValueError("settlement must become available after prediction")
        if self.capital_authority or self.execution_authority:
            raise ValueError("prop backtesting cannot authorize capital or execution")
        return self


class PropBacktestMetric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    sample_size: int = Field(ge=0)
    value: float | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> "PropBacktestMetric":
        if self.status == "COMPUTED" and self.value is None:
            raise ValueError("computed metric requires value")
        if self.status == "NOT_COMPUTABLE" and not self.reason:
            raise ValueError("not-computable metric requires reason")
        return self


class PropSurfaceBacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["PropSurfaceBacktest.v1"] = "PropSurfaceBacktest.v1"
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    market_class: str
    model_id: str
    as_of: datetime
    minimum_sample: int = Field(ge=1)
    row_count: int = Field(ge=0)
    threshold_forecast_count: int = Field(ge=0)
    monotonic_violation_rate: PropBacktestMetric
    calibration_error: PropBacktestMetric
    brier: PropBacktestMetric
    discrete_crps: PropBacktestMetric
    evidence_row_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False


def backtest_prop_surfaces(
    rows: list[PropSurfaceBacktestRow],
    *,
    market_class: str,
    model_id: str,
    as_of: datetime,
    minimum_sample: int = 20,
    calibration_bins: int = 10,
) -> PropSurfaceBacktestResult:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if minimum_sample < 1 or calibration_bins < 1:
        raise ValueError("minimum_sample and calibration_bins must be positive")
    cutoff = as_of.astimezone(timezone.utc)
    scoped = sorted(
        (row for row in rows if row.market_class == market_class and row.model_id == model_id and row.available_at <= cutoff),
        key=lambda row: (row.available_at, row.row_id),
    )
    duplicate = len({row.row_id for row in scoped}) != len(scoped) or len({(row.settlement_source, row.settlement_source_hash) for row in scoped}) != len(scoped)
    reason = "duplicate prop backtest evidence" if duplicate else "minimum settled prop-surface sample not met"

    def unavailable(name: str, sample: int) -> PropBacktestMetric:
        return PropBacktestMetric(name=name, status="NOT_COMPUTABLE", sample_size=sample, reason=reason)

    if duplicate or len(scoped) < minimum_sample:
        return PropSurfaceBacktestResult(
            status="NOT_COMPUTABLE", market_class=market_class, model_id=model_id, as_of=cutoff,
            minimum_sample=minimum_sample, row_count=len(scoped), threshold_forecast_count=sum(len(row.points) for row in scoped),
            monotonic_violation_rate=unavailable("monotonic_violation_rate", len(scoped)),
            calibration_error=unavailable("calibration_error", 0), brier=unavailable("brier", 0),
            discrete_crps=unavailable("discrete_crps", len(scoped)), evidence_row_ids=tuple(row.row_id for row in scoped), reasons=(reason,),
        )

    forecasts: list[tuple[float, int]] = []
    violations = 0
    row_crps: list[float] = []
    for row in scoped:
        points = sorted(row.points, key=lambda point: point.threshold)
        if any(right.survival_probability > left.survival_probability + 1e-12 for left, right in zip(points, points[1:])):
            violations += 1
        squared: list[float] = []
        for point in points:
            outcome = 1 if row.actual_value >= point.threshold else 0
            forecasts.append((point.survival_probability, outcome))
            squared.append((point.survival_probability - outcome) ** 2)
        span = points[-1].threshold - points[0].threshold
        if span <= 0:
            raise ValueError("surface threshold span must be positive")
        integral = sum(
            0.5 * (left_error + right_error) * (right.threshold - left.threshold)
            for left, right, left_error, right_error in zip(points, points[1:], squared, squared[1:])
        )
        row_crps.append(integral / span)

    brier_value = sum((probability - outcome) ** 2 for probability, outcome in forecasts) / len(forecasts)
    ece = 0.0
    for index in range(calibration_bins):
        low, high = index / calibration_bins, (index + 1) / calibration_bins
        bucket = [(probability, outcome) for probability, outcome in forecasts if low <= probability < high or (index == calibration_bins - 1 and probability == 1)]
        if bucket:
            predicted = sum(item[0] for item in bucket) / len(bucket)
            observed = sum(item[1] for item in bucket) / len(bucket)
            ece += len(bucket) / len(forecasts) * abs(predicted - observed)

    def metric(name: str, value: float, sample: int) -> PropBacktestMetric:
        return PropBacktestMetric(name=name, status="COMPUTED", sample_size=sample, value=value)

    return PropSurfaceBacktestResult(
        status="COMPUTED", market_class=market_class, model_id=model_id, as_of=cutoff,
        minimum_sample=minimum_sample, row_count=len(scoped), threshold_forecast_count=len(forecasts),
        monotonic_violation_rate=metric("monotonic_violation_rate", violations / len(scoped), len(scoped)),
        calibration_error=metric("calibration_error", ece, len(forecasts)),
        brier=metric("brier", brier_value, len(forecasts)),
        discrete_crps=metric("discrete_crps", sum(row_crps) / len(row_crps), len(scoped)),
        evidence_row_ids=tuple(row.row_id for row in scoped),
    )
