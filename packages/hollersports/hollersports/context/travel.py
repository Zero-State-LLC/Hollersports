from __future__ import annotations

from .models import ContextResult, TravelState, bounded_confidence, has_enough_samples, not_computable


def compute_travel_load(state: TravelState) -> ContextResult:
    """Compute a bounded travel-load index. Higher means more travel context load, not a verdict."""
    if not has_enough_samples(state.controlled_sample_size, state.history_sample_size):
        return not_computable("travel_load", ["inadequate controlled/history samples"], state.provenance)
    if state.miles_last_72h is None or state.timezone_delta_hours is None or state.rest_hours is None:
        return not_computable("travel_load", ["missing miles/timezone/rest evidence"], state.provenance)

    miles_component = min(state.miles_last_72h / 2500.0, 1.0) * 45.0
    timezone_component = min(abs(state.timezone_delta_hours) / 4.0, 1.0) * 25.0
    rest_component = max(0.0, (36.0 - state.rest_hours) / 36.0) * 20.0
    b2b_component = 10.0 if state.back_to_back else 0.0
    value = round(miles_component + timezone_component + rest_component + b2b_component, 4)
    sample_size = min(state.controlled_sample_size, state.history_sample_size)
    return ContextResult(status="COMPUTED", signal="travel_load", value=value, units="index_0_100", confidence=bounded_confidence(sample_size, len(state.provenance), "deterministic_context_v0_6"), provenance=state.provenance, reasons=[])
