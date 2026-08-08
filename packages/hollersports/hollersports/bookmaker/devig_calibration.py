from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .devig import devig, outcome_implied_probability
from .models import OutcomePrice

DevigMethod = Literal["MULTIPLICATIVE", "ADDITIVE", "POWER", "SHIN"]


class DevigCalibrationRow(BaseModel):
    """One settled, provenance-complete market used only after it became available."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    row_id: str = Field(min_length=1)
    bookmaker: str = Field(min_length=1)
    sport: str = Field(min_length=1)
    market_class: str = Field(min_length=1)
    odds_bucket: str = Field(min_length=1)
    outcomes: tuple[OutcomePrice, ...] = Field(min_length=2)
    winning_selection: str = Field(min_length=1)
    observed_at: datetime
    available_at: datetime
    source: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("observed_at", "available_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent(self) -> "DevigCalibrationRow":
        selections = [outcome.selection for outcome in self.outcomes]
        if len(set(selections)) != len(selections):
            raise ValueError("calibration outcomes require unique selections")
        if self.winning_selection not in selections:
            raise ValueError("winning_selection must exist in outcomes")
        if self.available_at < self.observed_at:
            raise ValueError("available_at cannot precede observed_at")
        if self.capital_authority or self.execution_authority:
            raise ValueError("de-vig calibration cannot authorize capital or execution")
        return self


class MethodCalibrationMetric(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    method: str
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    sample_size: int = Field(ge=0)
    brier: float | None = Field(default=None, ge=0)
    log_loss: float | None = Field(default=None, ge=0)
    reason: str | None = None


class DevigCalibrationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["DevigCalibrationComparison.v1"] = "DevigCalibrationComparison.v1"
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    bookmaker: str
    sport: str
    market_class: str
    odds_bucket: str
    as_of: datetime
    minimum_sample: int = Field(ge=1)
    raw_implied: MethodCalibrationMetric
    methods: tuple[MethodCalibrationMetric, ...]
    preferred_method: str | None = None
    improvement_over_raw_brier: float | None = None
    reasons: tuple[str, ...] = ()
    evidence_row_ids: tuple[str, ...] = ()
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False



def _scores(probabilities: dict[str, float], winner: str) -> tuple[float, float]:
    brier = sum((probability - (1.0 if selection == winner else 0.0)) ** 2 for selection, probability in probabilities.items())
    winner_probability = min(max(probabilities[winner], 1e-15), 1.0)
    return brier, -math.log(winner_probability)


def compare_devig_methods(
    rows: list[DevigCalibrationRow],
    *,
    bookmaker: str,
    sport: str,
    market_class: str,
    odds_bucket: str,
    as_of: datetime,
    minimum_sample: int = 20,
    method_parameters: dict[str, dict[str, Any]] | None = None,
) -> DevigCalibrationResult:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if minimum_sample < 1:
        raise ValueError("minimum_sample must be positive")
    cutoff = as_of.astimezone(timezone.utc)
    scoped = [
        row for row in rows
        if row.bookmaker == bookmaker
        and row.sport == sport
        and row.market_class == market_class
        and row.odds_bucket == odds_bucket
        and row.available_at <= cutoff
    ]
    scoped.sort(key=lambda row: (row.available_at, row.row_id))
    duplicate_ids = len({row.row_id for row in scoped}) != len(scoped)
    if duplicate_ids:
        reason = "duplicate calibration row_id"
        empty = MethodCalibrationMetric(method="RAW_IMPLIED", status="NOT_COMPUTABLE", sample_size=0, reason=reason)
        return DevigCalibrationResult(status="NOT_COMPUTABLE", bookmaker=bookmaker, sport=sport, market_class=market_class, odds_bucket=odds_bucket, as_of=cutoff, minimum_sample=minimum_sample, raw_implied=empty, methods=(), reasons=(reason,))

    raw_scores: list[tuple[float, float]] = []
    method_scores: dict[str, list[tuple[float, float]]] = {name: [] for name in ("MULTIPLICATIVE", "ADDITIVE", "POWER", "SHIN")}
    parameters = method_parameters or {}
    for row in scoped:
        raw = {outcome.selection: outcome_implied_probability(outcome) for outcome in row.outcomes}
        if all(value is not None for value in raw.values()):
            raw_scores.append(_scores({key: float(value) for key, value in raw.items()}, row.winning_selection))
        for method in method_scores:
            try:
                result = devig(row.outcomes, method=method, **parameters.get(method, {}))
            except (TypeError, ValueError):
                continue
            if result.status == "COMPUTED":
                method_scores[method].append(_scores(result.fair_probabilities, row.winning_selection))

    def metric(name: str, values: list[tuple[float, float]]) -> MethodCalibrationMetric:
        if len(values) < minimum_sample:
            return MethodCalibrationMetric(method=name, status="NOT_COMPUTABLE", sample_size=len(values), reason="minimum held-out sample not met")
        return MethodCalibrationMetric(method=name, status="COMPUTED", sample_size=len(values), brier=sum(value[0] for value in values) / len(values), log_loss=sum(value[1] for value in values) / len(values))

    raw_metric = metric("RAW_IMPLIED", raw_scores)
    methods = tuple(metric(name, values) for name, values in method_scores.items())
    computable = [item for item in methods if item.status == "COMPUTED"]
    if raw_metric.status != "COMPUTED" or not computable:
        reason = "raw and at least one de-vig method require the minimum held-out sample"
        return DevigCalibrationResult(status="NOT_COMPUTABLE", bookmaker=bookmaker, sport=sport, market_class=market_class, odds_bucket=odds_bucket, as_of=cutoff, minimum_sample=minimum_sample, raw_implied=raw_metric, methods=methods, reasons=(reason,), evidence_row_ids=tuple(row.row_id for row in scoped))
    ranked = sorted(computable, key=lambda item: (float(item.brier), float(item.log_loss), item.method))
    best = ranked[0]
    improvement = float(raw_metric.brier) - float(best.brier)
    return DevigCalibrationResult(
        status="COMPUTED",
        bookmaker=bookmaker,
        sport=sport,
        market_class=market_class,
        odds_bucket=odds_bucket,
        as_of=cutoff,
        minimum_sample=minimum_sample,
        raw_implied=raw_metric,
        methods=methods,
        preferred_method=best.method if improvement > 0 else None,
        improvement_over_raw_brier=improvement,
        reasons=() if improvement > 0 else ("no de-vig method beat raw implied Brier",),
        evidence_row_ids=tuple(row.row_id for row in scoped),
    )
