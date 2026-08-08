"""Bounded dependency-domain models for advisory-only parlay analysis."""
from __future__ import annotations
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from hollersports.governance.authority import Authority

class Computability(str, Enum):
    COMPUTABLE = "COMPUTABLE"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"

class DependencyMethod(str, Enum):
    INDEPENDENT = "INDEPENDENT_EXPLICITLY_ALLOWED"
    EMPIRICAL_CONDITIONAL = "EMPIRICAL_CONDITIONAL"
    DETERMINISTIC_MONTE_CARLO = "DETERMINISTIC_MONTE_CARLO_SHARED_DRIVER"

def bound_probability(value: float) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    return float(value)

class AdvisoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capital_authority: bool = False
    execution_authority: bool = False
    authority: str = Authority.SHADOW_ONLY.value
    advisory_mode: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    @model_validator(mode="after")
    def _enforce_shadow_only(self):
        if self.capital_authority or self.execution_authority:
            raise ValueError("dependency domain is advisory SHADOW_ONLY with no execution authority")
        if self.authority != Authority.SHADOW_ONLY.value:
            raise ValueError("authority must be SHADOW_ONLY")
        return self

class LegProbability(AdvisoryModel):
    leg_id: str
    marginal_probability: float
    evidence: dict[str, Any] = Field(default_factory=dict)
    @field_validator("marginal_probability")
    @classmethod
    def _p(cls, value: float) -> float:
        return bound_probability(value)

class DependencyEdge(AdvisoryModel):
    source_leg_id: str
    target_leg_id: str
    dependency_type: Literal["required", "informative", "shared_driver"] = "informative"
    weight: float = 0.0
    evidence: dict[str, Any] = Field(default_factory=dict)
    required: bool = False
    @field_validator("weight")
    @classmethod
    def _weight(cls, value: float) -> float:
        if not -1.0 <= value <= 1.0:
            raise ValueError("dependency weight must be in [-1, 1]")
        return float(value)

class EmpiricalConditionalEvidence(AdvisoryModel):
    ordered_leg_ids: list[str]
    conditional_probabilities: dict[str, float]
    sample_size: int | None = None
    @field_validator("conditional_probabilities")
    @classmethod
    def _conditional_probabilities(cls, value: dict[str, float]) -> dict[str, float]:
        return {key: bound_probability(prob) for key, prob in value.items()}

class DriverScenario(AdvisoryModel):
    scenario_id: str
    probability: float
    leg_probabilities: dict[str, float]
    @field_validator("probability")
    @classmethod
    def _scenario_probability(cls, value: float) -> float:
        return bound_probability(value)
    @field_validator("leg_probabilities")
    @classmethod
    def _leg_probabilities(cls, value: dict[str, float]) -> dict[str, float]:
        return {key: bound_probability(prob) for key, prob in value.items()}

class JointProbabilityResult(AdvisoryModel):
    status: Computability
    method: DependencyMethod | None = None
    joint_probability: float | None = None
    reason: str | None = None
    marginal_cap: float | None = None
    correlation_tax: float | None = None
    decomposition: dict[str, float] = Field(default_factory=dict)
    @model_validator(mode="after")
    def _bounded_joint(self):
        if self.joint_probability is not None:
            bound_probability(self.joint_probability)
            if self.marginal_cap is not None and self.joint_probability > self.marginal_cap + 1e-12:
                raise ValueError("joint probability cannot exceed any marginal probability")
        if self.correlation_tax is not None and self.correlation_tax < -1e-12:
            raise ValueError("correlation tax cannot be negative")
        return self
