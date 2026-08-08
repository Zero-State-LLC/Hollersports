"""Pydantic models for the V0.6 bookmaker bounded domain.

Shadow-only, advisory-only observed market data. Missing prices fail closed.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    """Return an aware UTC timestamp for locally captured records."""
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value


class GovernanceFields(BaseModel):
    """Governance envelope enforcing SHADOW_ONLY, ADVISORY_ONLY, and no authority."""
    mode: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @model_validator(mode="after")
    def _guard(self) -> "GovernanceFields":
        if self.mode != "SHADOW_ONLY" or self.advisory_mode != "ADVISORY_ONLY" or self.capital_authority or self.execution_authority:
            raise ValueError("bookmaker domain must be SHADOW_ONLY/ADVISORY_ONLY with capital/execution false")
        return self


class OutcomePrice(BaseModel):
    """Observed price for one outcome selection."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    selection: str = Field(min_length=1)
    american_odds: int | None = None
    decimal_odds: float | None = Field(default=None, gt=1.0)
    point: float | None = None
    observed_probability: float | None = Field(default=None, gt=0.0, lt=1.0)

    @field_validator("american_odds")
    @classmethod
    def _valid_american(cls, value: int | None) -> int | None:
        if value is not None and value in (-100, 0):
            raise ValueError("invalid american odds")
        return value

    @model_validator(mode="after")
    def _has_price(self) -> "OutcomePrice":
        if self.american_odds is None and self.decimal_odds is None and self.observed_probability is None:
            raise ValueError("observed price required")
        return self


class BookmakerQuote(GovernanceFields):
    """Observed quote from one bookmaker for one market."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    bookmaker: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    market_type: str = Field(min_length=1)
    outcomes: tuple[OutcomePrice, ...] = Field(min_length=1)
    market_id: str | None = None
    event_start_time: datetime | None = None
    fetched_at: datetime = Field(default_factory=utc_now)
    source: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_start_time", "fetched_at")
    @classmethod
    def _aware_timestamps(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)


class DevigResult(GovernanceFields):
    """Fail-closed packet for one deterministic de-vig calculation."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    method: Literal["MULTIPLICATIVE", "ADDITIVE", "POWER", "SHIN"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    raw_probabilities: dict[str, float] = Field(default_factory=dict)
    overround: float | None = None
    fair_probabilities: dict[str, float] = Field(default_factory=dict)
    uncertainty: float | None = None
    reason: str | None = None
    source: str | None = None
    source_hash: str | None = None


class ConsensusResult(GovernanceFields):
    """Weighted consensus packet with provenance and concentration diagnostics."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    probabilities: dict[str, float] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    raw_weights: dict[str, float] = Field(default_factory=dict)
    entropy: float | None = None
    weight_entropy: float | None = None
    effective_book_count: float | None = None
    bookmakers_observed: list[str] = Field(default_factory=list)
    source_provenance: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None


class BookmakerFingerprint(GovernanceFields):
    """Historical bookmaker diagnostics calculated only from supplied evidence."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    bookmaker: str
    sample_size: int
    minimum_sample: int
    brier: float | None = None
    log_loss: float | None = None
    ece: float | None = None
    hold: float | None = None
    bias: float | None = None
    stale_rate: float | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    field_sample_sizes: dict[str, int] = Field(default_factory=dict)
    reason: str | None = None
    source_provenance: list[dict[str, Any]] = Field(default_factory=list)


class MarketSnapshotV2(GovernanceFields):
    """Immutable append-only market_snapshot.v2 record."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["market_snapshot.v2"] = "market_snapshot.v2"
    snapshot_id: str = Field(min_length=1)
    captured_at: datetime = Field(default_factory=utc_now)
    event_id: str = Field(min_length=1)
    market_type: str = Field(min_length=1)
    quotes: tuple[BookmakerQuote, ...] = Field(min_length=1)
    fingerprint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("captured_at")
    @classmethod
    def _aware_captured_at(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def _observation_precedes_capture(self) -> "MarketSnapshotV2":
        if any(quote.fetched_at > self.captured_at for quote in self.quotes):
            raise ValueError("quote fetched_at cannot be later than snapshot captured_at")
        return self
