from __future__ import annotations

from enum import Enum
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ComputationStatus(str, Enum):
    COMPUTABLE = "COMPUTABLE"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"


class GovernanceMode(str, Enum):
    SHADOW_ONLY = "SHADOW_ONLY"


class PropSide(str, Enum):
    OVER = "OVER"
    UNDER = "UNDER"


class PropThreshold(BaseModel):
    model_config = ConfigDict(frozen=True)

    threshold: float
    fair_probability: float = Field(ge=0.0, le=1.0)
    side: PropSide = PropSide.OVER
    source: str | None = None


class PropLadder(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    market: str
    player: str | None = None
    thresholds: tuple[PropThreshold, ...] = Field(min_length=1)
    governance: GovernanceMode = GovernanceMode.SHADOW_ONLY
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("event_id", "market")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def _governance_closed(self) -> "PropLadder":
        if self.governance != GovernanceMode.SHADOW_ONLY:
            raise ValueError("props domain is SHADOW_ONLY")
        if self.capital_authority or self.execution_authority:
            raise ValueError("capital_authority and execution_authority must be false")
        return self


class Diagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class PropsResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ComputationStatus
    governance: GovernanceMode = GovernanceMode.SHADOW_ONLY
    value: float | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    diagnostics: tuple[Diagnostic, ...] = ()
    weak_fit: bool = False


def not_computable(code: str, message: str) -> PropsResult:
    return PropsResult(status=ComputationStatus.NOT_COMPUTABLE, value=None, diagnostics=(Diagnostic(code=code, message=message),), weak_fit=True)


def sorted_over_points(ladder: PropLadder) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for item in ladder.thresholds:
        probability = item.fair_probability if item.side == PropSide.OVER else 1.0 - item.fair_probability
        points.append((item.threshold, probability))
    points.sort(key=lambda x: x[0])
    return points


def coherent_points(points: Sequence[tuple[float, float]], *, min_points: int = 2) -> tuple[bool, str | None]:
    if len(points) < min_points:
        return False, "insufficient distinct ladder points"
    thresholds = [p[0] for p in points]
    if len(set(thresholds)) != len(thresholds):
        return False, "duplicate thresholds are incoherent"
    if any(prob < 0.0 or prob > 1.0 for _, prob in points):
        return False, "probabilities must be bounded in [0, 1]"
    return True, None
