"""Evidence-bound V0.6 bookmaker backtesting metrics.

Independent SHADOW_ONLY/ADVISORY_ONLY helpers. This module does not place wagers,
recommend stakes, or require API route integration.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MetricStatus = Literal["COMPUTABLE", "NOT_COMPUTABLE"]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value


class BacktestMetric(BaseModel):
    """One evidence-bound metric result with explicit sample accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1)
    status: MetricStatus
    sample_size: int = Field(ge=0)
    value: float | None = None
    reason: str | None = None
    group: str | None = None

    @model_validator(mode="after")
    def _status_matches_value(self) -> "BacktestMetric":
        if self.status == "COMPUTABLE" and self.value is None:
            raise ValueError("computable metric requires value")
        if self.status == "NOT_COMPUTABLE" and not self.reason:
            raise ValueError("not-computable metric requires reason")
        return self


class BacktestRow(BaseModel):
    """One settled prediction row for advisory-only bookmaker backtesting."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    row_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    market_type: str = Field(min_length=1)
    selection: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    predicted_probability: float = Field(gt=0.0, lt=1.0)
    outcome: int | None = Field(default=None, ge=0, le=1)
    prediction_at: datetime
    closing_at: datetime | None = None
    settled_at: datetime | None = None
    fair_probability: float | None = Field(default=None, gt=0.0, lt=1.0)
    book_probability: float | None = Field(default=None, gt=0.0, lt=1.0)
    closing_probability: float | None = Field(default=None, gt=0.0, lt=1.0)
    verdict: str | None = None
    group: str | None = None
    mode: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("prediction_at", "closing_at", "settled_at")
    @classmethod
    def _aware_timestamps(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)

    @model_validator(mode="after")
    def _guardrails(self) -> "BacktestRow":
        if self.capital_authority or self.execution_authority:
            raise ValueError("backtest rows are advisory-only with no capital/execution authority")
        if self.closing_at is not None and self.settled_at is not None:
            if not (self.prediction_at < self.closing_at <= self.settled_at):
                raise ValueError("no-future-leakage requires prediction_at < closing_at <= settled_at")
        if self.outcome is not None and self.settled_at is None:
            raise ValueError("settled_at is required when outcome is present")
        return self


def _rows(rows: Iterable[BacktestRow]) -> list[BacktestRow]:
    return list(rows)


def _not(name: str, sample_size: int, reason: str, group: str | None = None) -> BacktestMetric:
    return BacktestMetric(name=name, status="NOT_COMPUTABLE", sample_size=sample_size, reason=reason, group=group)


def _metric(name: str, value: float, sample_size: int, group: str | None = None) -> BacktestMetric:
    return BacktestMetric(name=name, status="COMPUTABLE", sample_size=sample_size, value=value, group=group)


def brier_score(rows: Iterable[BacktestRow], *, min_samples: int = 1) -> BacktestMetric:
    usable = [r for r in _rows(rows) if r.outcome is not None]
    if len(usable) < min_samples:
        return _not("brier", len(usable), "outcomes or minimum samples absent")
    return _metric("brier", sum((r.predicted_probability - float(r.outcome)) ** 2 for r in usable) / len(usable), len(usable))


def log_loss(rows: Iterable[BacktestRow], *, min_samples: int = 1, eps: float = 1e-15) -> BacktestMetric:
    usable = [r for r in _rows(rows) if r.outcome is not None]
    if len(usable) < min_samples:
        return _not("log_loss", len(usable), "outcomes or minimum samples absent")
    total = 0.0
    for r in usable:
        p = min(max(r.predicted_probability, eps), 1.0 - eps)
        y = float(r.outcome)
        total += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
    return _metric("log_loss", total / len(usable), len(usable))


def expected_calibration_error(rows: Iterable[BacktestRow], *, bins: int = 10, min_samples: int = 1) -> BacktestMetric:
    usable = [r for r in _rows(rows) if r.outcome is not None]
    if bins <= 0:
        return _not("ece", len(usable), "bins must be positive")
    if len(usable) < min_samples:
        return _not("ece", len(usable), "outcomes or minimum samples absent")
    total = 0.0
    for idx in range(bins):
        lo, hi = idx / bins, (idx + 1) / bins
        bucket = [r for r in usable if (lo <= r.predicted_probability < hi) or (idx == bins - 1 and r.predicted_probability == 1.0)]
        if bucket:
            conf = sum(r.predicted_probability for r in bucket) / len(bucket)
            acc = sum(float(r.outcome) for r in bucket) / len(bucket)
            total += (len(bucket) / len(usable)) * abs(acc - conf)
    return _metric("ece", total, len(usable))


def fair_calibration_error(rows: Iterable[BacktestRow], *, min_samples: int = 1) -> BacktestMetric:
    """Absolute calibration gap between reconstructed fair belief and outcomes."""
    usable = [r for r in _rows(rows) if r.fair_probability is not None and r.outcome is not None]
    if len(usable) < min_samples:
        return _not("fair_calibration_error", len(usable), "fair probabilities, outcomes, or minimum samples absent")
    fair_rate = sum(float(r.fair_probability) for r in usable) / len(usable)
    outcome_rate = sum(float(r.outcome) for r in usable) / len(usable)
    return _metric("fair_calibration_error", abs(fair_rate - outcome_rate), len(usable))


def book_pricing_error(rows: Iterable[BacktestRow], *, min_samples: int = 1) -> BacktestMetric:
    """Absolute calibration gap between reconstructed book belief and outcomes."""
    usable = [r for r in _rows(rows) if r.book_probability is not None and r.outcome is not None]
    if len(usable) < min_samples:
        return _not("book_pricing_error", len(usable), "book probabilities, outcomes, or minimum samples absent")
    book_rate = sum(float(r.book_probability) for r in usable) / len(usable)
    outcome_rate = sum(float(r.outcome) for r in usable) / len(usable)
    return _metric("book_pricing_error", abs(book_rate - outcome_rate), len(usable))


def clv_information_capture_ratio(rows: Iterable[BacktestRow], *, min_samples: int = 1) -> BacktestMetric:
    usable = [r for r in _rows(rows) if r.fair_probability is not None and r.closing_probability is not None and r.closing_at is not None and r.settled_at is not None]
    if len(usable) < min_samples:
        return _not("clv_information_capture_ratio", len(usable), "fair/closing prices, temporal evidence, or minimum samples absent")
    denom = sum(abs(r.closing_probability - r.fair_probability) for r in usable)
    if denom == 0.0:
        return _not("clv_information_capture_ratio", len(usable), "closing-to-fair movement is zero")
    numerator = sum(abs(r.predicted_probability - r.fair_probability) for r in usable)
    return _metric("clv_information_capture_ratio", numerator / denom, len(usable))


def verdict_discrimination_by_group(rows: Iterable[BacktestRow], *, min_samples: int = 2) -> list[BacktestMetric]:
    grouped: dict[str, list[BacktestRow]] = defaultdict(list)
    for row in _rows(rows):
        grouped[row.group or "UNGROUPED"].append(row)
    metrics: list[BacktestMetric] = []
    for group, items in sorted(grouped.items()):
        usable = [r for r in items if r.outcome is not None and r.verdict]
        if len(usable) < min_samples or len({r.verdict for r in usable}) < 2:
            metrics.append(_not("verdict_discrimination", len(usable), "outcomes, verdict diversity, or minimum samples absent", group))
            continue
        rates = []
        for verdict in sorted({r.verdict for r in usable}):
            bucket = [r for r in usable if r.verdict == verdict]
            rates.append(sum(float(r.outcome) for r in bucket) / len(bucket))
        metrics.append(_metric("verdict_discrimination", max(rates) - min(rates), len(usable), group))
    return metrics


def compute_backtest_metrics(rows: Iterable[BacktestRow], *, min_samples: int = 1, ece_bins: int = 10) -> list[BacktestMetric]:
    materialized = _rows(rows)
    return [
        brier_score(materialized, min_samples=min_samples),
        log_loss(materialized, min_samples=min_samples),
        expected_calibration_error(materialized, bins=ece_bins, min_samples=min_samples),
        fair_calibration_error(materialized, min_samples=min_samples),
        book_pricing_error(materialized, min_samples=min_samples),
        clv_information_capture_ratio(materialized, min_samples=min_samples),
        *verdict_discrimination_by_group(materialized, min_samples=max(2, min_samples)),
    ]
