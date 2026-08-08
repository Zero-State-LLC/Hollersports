"""Shared-driver helpers for deterministic Monte Carlo inputs."""
from __future__ import annotations
from .models import DriverScenario

def normalize_driver_scenarios(scenarios: list[DriverScenario]) -> list[DriverScenario]:
    total = sum(s.probability for s in scenarios)
    if total <= 0:
        raise ValueError("scenario probabilities must have positive total")
    return [s.model_copy(update={"probability": s.probability / total}) for s in scenarios]
