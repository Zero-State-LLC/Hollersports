from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict

from .models import ContextResult, Provenance, bounded_confidence, has_enough_samples, not_computable


class CoachHistory(BaseModel):
    model_config = ConfigDict(frozen=True)

    coach_id: str = Field(..., min_length=1)
    adjustment_events: int = Field(..., ge=0)
    comparable_events: int = Field(..., ge=0)
    controlled_sample_size: int = Field(default=0, ge=0)
    history_sample_size: int = Field(default=0, ge=0)
    provenance: list[Provenance] = Field(default_factory=list)


def compute_coach_response(history: CoachHistory) -> ContextResult:
    if not has_enough_samples(history.controlled_sample_size, history.history_sample_size) or history.comparable_events <= 0:
        return not_computable("coach_response", ["inadequate controlled/history samples"], history.provenance)
    value = round(min(history.adjustment_events / history.comparable_events, 1.0), 4)
    sample_size = min(history.controlled_sample_size, history.history_sample_size, history.comparable_events)
    return ContextResult(status="COMPUTED", signal="coach_response", value=value, units="rate_0_1", confidence=bounded_confidence(sample_size, len(history.provenance), "deterministic_context_v0_6"), provenance=history.provenance, reasons=[])
