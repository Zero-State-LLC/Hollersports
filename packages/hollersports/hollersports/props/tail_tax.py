from __future__ import annotations

from .models import ComputationStatus, PropLadder, PropsResult, not_computable
from .surface import reconstruct_survival


def compute_curvature(ladder: PropLadder) -> PropsResult:
    surface = reconstruct_survival(ladder)
    if surface.status != ComputationStatus.COMPUTABLE or len(surface.points) < 3:
        return not_computable("INSUFFICIENT_EVIDENCE", "curvature requires at least three coherent thresholds")
    slopes = []
    pts = surface.points
    for a, b in zip(pts, pts[1:]):
        dx = b.threshold - a.threshold
        if dx <= 0:
            return not_computable("INCOHERENT_LADDER", "thresholds must be strictly increasing")
        slopes.append((b.survival_probability - a.survival_probability) / dx)
    curvature = sum(abs(slopes[i + 1] - slopes[i]) for i in range(len(slopes) - 1)) / (len(slopes) - 1)
    return PropsResult(status=ComputationStatus.COMPUTABLE, value=curvature, metrics={"curvature": curvature}, weak_fit=surface.weak_fit, diagnostics=surface.diagnostics)


def compute_tail_tax(ladder: PropLadder) -> PropsResult:
    curvature = compute_curvature(ladder)
    if curvature.status != ComputationStatus.COMPUTABLE or curvature.value is None:
        return curvature
    surface = reconstruct_survival(ladder)
    tail_drop = surface.points[-2].survival_probability - surface.points[-1].survival_probability
    tax = max(0.0, tail_drop) * (1.0 + curvature.value)
    return PropsResult(status=ComputationStatus.COMPUTABLE, value=tax, metrics={"tail_tax": tax, "curvature": curvature.value}, weak_fit=curvature.weak_fit, diagnostics=curvature.diagnostics)
