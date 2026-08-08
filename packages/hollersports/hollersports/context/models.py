from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


ContextMode = Literal["SHADOW_ONLY"]
Status = Literal["COMPUTED", "NOT_COMPUTABLE"]


class EvidenceQuality(str, Enum):
    DIRECT = "DIRECT"
    DERIVED = "DERIVED"
    ESTIMATED = "ESTIMATED"


class Provenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str = Field(..., min_length=1)
    observed_at: datetime | None = None
    quality: EvidenceQuality = EvidenceQuality.DIRECT
    notes: str | None = None

    @field_validator("observed_at")
    @classmethod
    def timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("provenance observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class Confidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float = Field(..., ge=0.0, le=1.0)
    sample_size: int = Field(..., ge=0)
    method: str = Field(..., min_length=1)


class ContextResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Status
    mode: ContextMode = "SHADOW_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False
    signal: str
    value: float | None = None
    units: str | None = None
    confidence: Confidence
    provenance: list[Provenance] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def advisory_only(self) -> "ContextResult":
        if self.mode != "SHADOW_ONLY" or self.capital_authority or self.execution_authority:
            raise ValueError("context results are SHADOW_ONLY without capital or execution authority")
        return self


class PlayerState(BaseModel):
    model_config = ConfigDict(frozen=True)

    player_id: str = Field(..., min_length=1)
    team_id: str | None = None
    minutes_last_7d: float | None = Field(default=None, ge=0)
    games_last_7d: int | None = Field(default=None, ge=0)
    rest_hours: float | None = Field(default=None, ge=0)
    injury_status: str | None = None
    controlled_sample_size: int = Field(default=0, ge=0)
    history_sample_size: int = Field(default=0, ge=0)
    provenance: list[Provenance] = Field(default_factory=list)
    confidence: Confidence = Field(default_factory=lambda: Confidence(value=0.0, sample_size=0, method="unscored"))


class TravelState(BaseModel):
    model_config = ConfigDict(frozen=True)

    team_id: str = Field(..., min_length=1)
    miles_last_72h: float | None = Field(default=None, ge=0)
    timezone_delta_hours: float | None = None
    rest_hours: float | None = Field(default=None, ge=0)
    back_to_back: bool = False
    controlled_sample_size: int = Field(default=0, ge=0)
    history_sample_size: int = Field(default=0, ge=0)
    provenance: list[Provenance] = Field(default_factory=list)
    confidence: Confidence = Field(default_factory=lambda: Confidence(value=0.0, sample_size=0, method="unscored"))


MIN_CONTROLLED_SAMPLE = 3
MIN_HISTORY_SAMPLE = 5


def has_enough_samples(controlled_sample_size: int, history_sample_size: int) -> bool:
    return controlled_sample_size >= MIN_CONTROLLED_SAMPLE and history_sample_size >= MIN_HISTORY_SAMPLE


def bounded_confidence(sample_size: int, provenance_count: int, method: str) -> Confidence:
    sample_component = min(sample_size / 25.0, 0.8)
    provenance_component = min(provenance_count / 5.0, 0.2)
    return Confidence(value=round(sample_component + provenance_component, 4), sample_size=sample_size, method=method)


def not_computable(signal: str, reasons: list[str], provenance: list[Provenance] | None = None) -> ContextResult:
    return ContextResult(
        status="NOT_COMPUTABLE",
        signal=signal,
        confidence=Confidence(value=0.0, sample_size=0, method="fail_closed"),
        provenance=provenance or [],
        reasons=reasons,
    )
