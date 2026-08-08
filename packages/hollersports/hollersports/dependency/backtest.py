from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class JointBacktestRow(BaseModel):
    """One settled parlay forecast with both independence and modeled baselines."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    row_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    market_class: str = Field(min_length=1)
    leg_marginals: tuple[float, ...] = Field(min_length=2)
    independent_probability: float = Field(ge=0, le=1)
    modeled_joint_probability: float = Field(ge=0, le=1)
    modeled_method: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    outcome: int = Field(ge=0, le=1)
    prediction_evidence_at: datetime
    predicted_at: datetime
    available_at: datetime
    prediction_source: str = Field(min_length=1)
    prediction_source_hash: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("leg_marginals")
    @classmethod
    def probabilities(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if any(not 0 <= value <= 1 for value in values):
            raise ValueError("leg marginals must be in [0, 1]")
        return values

    @field_validator("prediction_evidence_at", "predicted_at", "available_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent(self) -> "JointBacktestRow":
        if self.prediction_evidence_at > self.predicted_at:
            raise ValueError("prediction evidence cannot postdate prediction")
        if self.available_at <= self.predicted_at:
            raise ValueError("settled outcome must become available after prediction")
        independent = math.prod(self.leg_marginals)
        if abs(independent - self.independent_probability) > 1e-9:
            raise ValueError("independent_probability must equal the product of leg marginals")
        if self.modeled_joint_probability > min(self.leg_marginals) + 1e-12:
            raise ValueError("modeled joint probability cannot exceed a marginal")
        if self.capital_authority or self.execution_authority:
            raise ValueError("joint backtesting cannot authorize capital or execution")
        return self


class JointBacktestMetric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    sample_size: int = Field(ge=0)
    value: float | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> "JointBacktestMetric":
        if self.status == "COMPUTED" and self.value is None:
            raise ValueError("computed metric requires value")
        if self.status == "NOT_COMPUTABLE" and not self.reason:
            raise ValueError("not-computable metric requires reason")
        return self


class JointBacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["JointProbabilityBacktest.v1"] = "JointProbabilityBacktest.v1"
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    market_class: str
    modeled_method: str
    model_id: str
    as_of: datetime
    minimum_sample: int = Field(ge=1)
    leg_count: int | None = Field(default=None, ge=2)
    independent_brier: JointBacktestMetric
    modeled_brier: JointBacktestMetric
    independent_log_loss: JointBacktestMetric
    modeled_log_loss: JointBacktestMetric
    log_loss_improvement: float | None = None
    modeled_beats_independence: bool | None = None
    evidence_row_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False


def _loss(probability: float, outcome: int) -> tuple[float, float]:
    bounded = min(max(probability, 1e-15), 1 - 1e-15)
    return (probability - outcome) ** 2, -(outcome * math.log(bounded) + (1 - outcome) * math.log(1 - bounded))


def backtest_joint_probabilities(
    rows: list[JointBacktestRow],
    *,
    market_class: str,
    modeled_method: str,
    model_id: str,
    as_of: datetime,
    minimum_sample: int = 20,
) -> JointBacktestResult:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if minimum_sample < 1:
        raise ValueError("minimum_sample must be positive")
    cutoff = as_of.astimezone(timezone.utc)
    scoped = sorted(
        (row for row in rows if row.market_class == market_class and row.modeled_method == modeled_method and row.model_id == model_id and row.available_at <= cutoff),
        key=lambda row: (row.available_at, row.row_id),
    )
    duplicate_ids = len({row.row_id for row in scoped}) != len(scoped)
    duplicate_sources = len({(row.source, row.source_hash) for row in scoped}) != len(scoped)
    mixed_leg_counts = len({len(row.leg_marginals) for row in scoped}) > 1
    if duplicate_ids or duplicate_sources or mixed_leg_counts:
        reason = "duplicate joint backtest row_id" if duplicate_ids else "duplicate joint source evidence" if duplicate_sources else "joint backtest cannot mix leg counts"
        empty = JointBacktestMetric(name="independent_brier", status="NOT_COMPUTABLE", sample_size=0, reason=reason)
        return JointBacktestResult(status="NOT_COMPUTABLE", market_class=market_class, modeled_method=modeled_method, model_id=model_id, as_of=cutoff, minimum_sample=minimum_sample, independent_brier=empty, modeled_brier=empty.model_copy(update={"name": "modeled_brier"}), independent_log_loss=empty.model_copy(update={"name": "independent_log_loss"}), modeled_log_loss=empty.model_copy(update={"name": "modeled_log_loss"}), reasons=(reason,))
    if len(scoped) < minimum_sample:
        reason = "minimum settled joint sample not met"
        def unavailable(name: str) -> JointBacktestMetric:
            return JointBacktestMetric(name=name, status="NOT_COMPUTABLE", sample_size=len(scoped), reason=reason)
        return JointBacktestResult(status="NOT_COMPUTABLE", market_class=market_class, modeled_method=modeled_method, model_id=model_id, as_of=cutoff, minimum_sample=minimum_sample, leg_count=len(scoped[0].leg_marginals) if scoped else None, independent_brier=unavailable("independent_brier"), modeled_brier=unavailable("modeled_brier"), independent_log_loss=unavailable("independent_log_loss"), modeled_log_loss=unavailable("modeled_log_loss"), evidence_row_ids=tuple(row.row_id for row in scoped), reasons=(reason,))
    independent = [_loss(row.independent_probability, row.outcome) for row in scoped]
    modeled = [_loss(row.modeled_joint_probability, row.outcome) for row in scoped]
    def metric(name: str, values: list[float]) -> JointBacktestMetric:
        return JointBacktestMetric(name=name, status="COMPUTED", sample_size=len(values), value=sum(values) / len(values))
    independent_log = sum(value[1] for value in independent) / len(independent)
    modeled_log = sum(value[1] for value in modeled) / len(modeled)
    improvement = independent_log - modeled_log
    return JointBacktestResult(
        status="COMPUTED", market_class=market_class, modeled_method=modeled_method, model_id=model_id, as_of=cutoff,
        minimum_sample=minimum_sample, leg_count=len(scoped[0].leg_marginals),
        independent_brier=metric("independent_brier", [value[0] for value in independent]),
        modeled_brier=metric("modeled_brier", [value[0] for value in modeled]),
        independent_log_loss=metric("independent_log_loss", [value[1] for value in independent]),
        modeled_log_loss=metric("modeled_log_loss", [value[1] for value in modeled]),
        log_loss_improvement=improvement,
        modeled_beats_independence=improvement > 0,
        evidence_row_ids=tuple(row.row_id for row in scoped),
        reasons=() if improvement > 0 else ("modeled joint probability did not beat explicit independence",),
    )
