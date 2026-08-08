"""Pydantic models for the V0.6 bookmaker bounded domain.

Shadow-only, advisory-only observed market data. Missing prices fail closed.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

def utc_now_iso() -> str:
    """Return a UTC timestamp for locally captured records."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

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
        if value is not None and value in (-100, 0): raise ValueError("invalid american odds")
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
    event_start_time: str | None = None
    fetched_at: str = Field(default_factory=utc_now_iso)
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class MarketSnapshotV2(GovernanceFields):
    """Immutable append-only market_snapshot.v2 record."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["market_snapshot.v2"] = "market_snapshot.v2"
    snapshot_id: str = Field(min_length=1)
    captured_at: str = Field(default_factory=utc_now_iso)
    event_id: str = Field(min_length=1)
    market_type: str = Field(min_length=1)
    quotes: tuple[BookmakerQuote, ...] = Field(min_length=1)
    fingerprint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
