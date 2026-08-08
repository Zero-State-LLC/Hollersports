from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict

from .models import ContextResult, Provenance, bounded_confidence, has_enough_samples, not_computable


class VenueState(BaseModel):
    model_config = ConfigDict(frozen=True)

    venue_id: str = Field(..., min_length=1)
    observed_factor: float | None = None
    controlled_baseline: float | None = None
    league_baseline: float | None = None
    controlled_sample_size: int = Field(default=0, ge=0)
    history_sample_size: int = Field(default=0, ge=0)
    provenance: list[Provenance] = Field(default_factory=list)


def compute_venue_residual(state: VenueState) -> ContextResult:
    if not has_enough_samples(state.controlled_sample_size, state.history_sample_size):
        return not_computable("venue_residual", ["inadequate controlled/history samples"], state.provenance)
    if state.observed_factor is None or state.controlled_baseline is None or state.league_baseline is None:
        return not_computable("venue_residual", ["missing observed/baseline venue evidence"], state.provenance)
    value = round(state.observed_factor - ((state.controlled_baseline + state.league_baseline) / 2.0), 4)
    sample_size = min(state.controlled_sample_size, state.history_sample_size)
    return ContextResult(status="COMPUTED", signal="venue_residual", value=value, units="factor_delta", confidence=bounded_confidence(sample_size, len(state.provenance), "deterministic_context_v0_6"), provenance=state.provenance, reasons=[])
