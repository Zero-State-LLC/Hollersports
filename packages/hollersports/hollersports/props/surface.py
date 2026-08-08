from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .models import ComputationStatus, Diagnostic, PropLadder, coherent_points, not_computable, sorted_over_points


class SurvivalPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    threshold: float
    survival_probability: float
    original_probability: float
    adjusted: bool = False


class SurvivalSurface(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ComputationStatus
    points: tuple[SurvivalPoint, ...] = ()
    weak_fit: bool = False
    diagnostics: tuple[Diagnostic, ...] = ()


def reconstruct_survival(ladder: PropLadder) -> SurvivalSurface:
    points = sorted_over_points(ladder)
    ok, reason = coherent_points(points, min_points=2)
    if not ok:
        result = not_computable("INCOHERENT_LADDER", reason or "incoherent ladder")
        return SurvivalSurface(status=result.status, weak_fit=True, diagnostics=result.diagnostics)
    reconstructed: list[SurvivalPoint] = []
    running = 1.0
    weak_fit = False
    for threshold, probability in points:
        bounded = min(1.0, max(0.0, probability))
        fitted = min(running, bounded)
        adjusted = abs(fitted - probability) > 1e-12
        weak_fit = weak_fit or adjusted
        reconstructed.append(SurvivalPoint(threshold=threshold, survival_probability=fitted, original_probability=probability, adjusted=adjusted))
        running = fitted
    diagnostics = (Diagnostic(code="WEAK_FIT_MONOTONIC_REPAIR", message="input probabilities were repaired to non-increasing survival"),) if weak_fit else ()
    return SurvivalSurface(status=ComputationStatus.COMPUTABLE, points=tuple(reconstructed), weak_fit=weak_fit, diagnostics=diagnostics)
