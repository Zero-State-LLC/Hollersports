from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hollersports.runes.structural_verdict import StructuralThresholds, structural_verdict


class StructuralEvidenceObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    subject_type: Literal["SINGLE", "PARLAY"]
    observed_at: datetime
    recorded_at: datetime
    source: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    threshold_source_id: str = Field(min_length=1)
    threshold_source_hash: str = Field(min_length=1)
    book_probability: float | None = Field(default=None, ge=0, le=1)
    consensus_probability: float | None = Field(default=None, ge=0, le=1)
    reality_probability: float | None = Field(default=None, ge=0, le=1)
    data_quality: float = Field(ge=0, le=1)
    market_entropy: float = Field(ge=0, le=1)
    context_confidence: float | None = Field(default=None, ge=0, le=1)
    thresholds: StructuralThresholds
    dependency_required: bool = False
    dependency_confidence: float | None = Field(default=None, ge=0, le=1)
    joint_probability: float | None = Field(default=None, ge=0, le=1)
    book_joint_probability: float | None = Field(default=None, ge=0, le=1)
    evidence_references: dict[str, str] = Field(default_factory=dict)
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("observed_at", "recorded_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent(self) -> "StructuralEvidenceObservation":
        if self.recorded_at < self.observed_at:
            raise ValueError("recorded_at cannot precede observed_at")
        if self.capital_authority or self.execution_authority:
            raise ValueError("structural evidence cannot authorize capital or execution")
        if self.subject_type == "PARLAY" and not self.dependency_required:
            raise ValueError("PARLAY structural evidence must require dependency analysis")
        required_refs = {"bookmaker", "market", "context", "player"}
        if self.dependency_required:
            required_refs.add("dependency")
        if not required_refs.issubset(self.evidence_references):
            raise ValueError("evidence references must identify every required evidence family")
        if any(not key.strip() or not value.strip() for key, value in self.evidence_references.items()):
            raise ValueError("evidence reference keys and values must not be blank")
        return self

    def derive(self) -> dict[str, Any]:
        return structural_verdict(
            book_probability=self.book_probability,
            consensus_probability=self.consensus_probability,
            reality_probability=self.reality_probability,
            data_quality=self.data_quality,
            market_entropy=self.market_entropy,
            thresholds=self.thresholds,
            dependency_required=self.dependency_required,
            dependency_confidence=self.dependency_confidence,
            joint_probability=self.joint_probability,
            book_joint_probability=self.book_joint_probability,
            context_reference=self.evidence_references.get("context"),
            context_confidence=self.context_confidence,
        )


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"


class ReleaseGateThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum_backtest_sample: int = Field(ge=1)
    minimum_qualified_fingerprints: int = Field(ge=1)
    maximum_prop_monotonic_violation_rate: float = Field(ge=0, le=1)
    maximum_prop_calibration_error: float = Field(ge=0, le=1)
    minimum_verdict_discrimination: float = Field(ge=0)
    minimum_pass_retained_sample: int = Field(ge=1)


class ReleaseGateEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    temporal_replay_passed: bool | None = None
    devig_sample_size: int = Field(default=0, ge=0)
    raw_implied_brier: float | None = Field(default=None, ge=0)
    fair_probability_brier: float | None = Field(default=None, ge=0)
    qualified_fingerprint_count: int | None = Field(default=None, ge=0)
    prop_sample_size: int = Field(default=0, ge=0)
    prop_monotonic_violation_rate: float | None = Field(default=None, ge=0, le=1)
    prop_calibration_error: float | None = Field(default=None, ge=0, le=1)
    joint_sample_size: int = Field(default=0, ge=0)
    independent_joint_log_loss: float | None = Field(default=None, ge=0)
    modeled_joint_log_loss: float | None = Field(default=None, ge=0)
    verdict_sample_size: int = Field(default=0, ge=0)
    verdict_discrimination: float | None = Field(default=None, ge=0)
    pass_retained_sample: int = Field(default=0, ge=0)
    forced_pick_calibration_error: float | None = Field(default=None, ge=0)
    pass_filtered_calibration_error: float | None = Field(default=None, ge=0)
    v05_regression_passed: bool | None = None
    provenance: dict[str, str] = Field(default_factory=dict)


class ReleaseGateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    gate: Literal["A", "B", "C", "D", "E", "F", "G", "H"]
    status: GateStatus
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class ReleaseReadinessPacket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["V06ReleaseReadinessPacket.v1"] = "V06ReleaseReadinessPacket.v1"
    status: Literal["READY", "NOT_READY"]
    gates: tuple[ReleaseGateResult, ...]
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False
