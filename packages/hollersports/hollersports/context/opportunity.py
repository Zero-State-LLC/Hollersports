from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict

from .models import ContextResult, Provenance, bounded_confidence, has_enough_samples, not_computable


class OpportunityState(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: str = Field(..., min_length=1)
    current_usage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline_usage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    current_availability_share: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline_availability_share: float | None = Field(default=None, ge=0.0, le=1.0)
    controlled_sample_size: int = Field(default=0, ge=0)
    history_sample_size: int = Field(default=0, ge=0)
    provenance: list[Provenance] = Field(default_factory=list)


def compute_opportunity_shift(state: OpportunityState) -> ContextResult:
    if not has_enough_samples(state.controlled_sample_size, state.history_sample_size):
        return not_computable("opportunity_shift", ["inadequate controlled/history samples"], state.provenance)
    fields = [state.current_usage_rate, state.baseline_usage_rate, state.current_availability_share, state.baseline_availability_share]
    if any(value is None for value in fields):
        return not_computable("opportunity_shift", ["missing usage/availability evidence"], state.provenance)
    value = round(((state.current_usage_rate or 0.0) - (state.baseline_usage_rate or 0.0)) + ((state.current_availability_share or 0.0) - (state.baseline_availability_share or 0.0)), 4)
    sample_size = min(state.controlled_sample_size, state.history_sample_size)
    return ContextResult(status="COMPUTED", signal="opportunity_shift", value=value, units="share_delta", confidence=bounded_confidence(sample_size, len(state.provenance), "deterministic_context_v0_6"), provenance=state.provenance, reasons=[])
