from __future__ import annotations

from .models import ComputationStatus, Diagnostic, PropLadder, PropsResult, not_computable
from .surface import reconstruct_survival


def _classify_curvature(value: float) -> str:
    if value < 0.01:
        return "FLAT"
    if value < 0.05:
        return "GRADUAL"
    return "KINKED"


def _classify_tail_tax(value: float) -> str:
    if value < 0.03:
        return "LOW"
    if value < 0.08:
        return "MODERATE"
    return "HIGH"


def compute_curvature(ladder: PropLadder) -> PropsResult:
    surface = reconstruct_survival(ladder)
    if surface.status != ComputationStatus.COMPUTABLE or len(surface.points) < 3:
        return not_computable("INSUFFICIENT_EVIDENCE", "curvature requires at least three coherent thresholds")
    slopes = []
    pts = surface.points
    adjacent_curvatures: list[float] = []
    for a, b in zip(pts, pts[1:]):
        dx = b.threshold - a.threshold
        if dx <= 0:
            return not_computable("INCOHERENT_LADDER", "thresholds must be strictly increasing")
        slopes.append((b.survival_probability - a.survival_probability) / dx)
    for i in range(len(slopes) - 1):
        adjacent_curvatures.append(abs(slopes[i + 1] - slopes[i]))
    curvature = sum(adjacent_curvatures) / len(adjacent_curvatures)
    metrics = {
        "curvature": curvature,
        "adjacent_curvature_max": max(adjacent_curvatures),
        "adjacent_curvature_mean": curvature,
    }
    diagnostics = surface.diagnostics + (Diagnostic(code=f"CURVATURE_{_classify_curvature(curvature)}", message="adjacent threshold curvature classification"),)
    return PropsResult(status=ComputationStatus.COMPUTABLE, value=curvature, metrics=metrics, weak_fit=surface.weak_fit, diagnostics=diagnostics)


def compute_tail_tax(ladder: PropLadder) -> PropsResult:
    curvature = compute_curvature(ladder)
    if curvature.status != ComputationStatus.COMPUTABLE or curvature.value is None:
        return curvature
    surface = reconstruct_survival(ladder)
    tail_drop = surface.points[-2].survival_probability - surface.points[-1].survival_probability
    tax = max(0.0, tail_drop) * (1.0 + curvature.value)
    diagnostics = curvature.diagnostics + (Diagnostic(code=f"TAIL_TAX_{_classify_tail_tax(tax)}", message="adjacent threshold tail-tax classification"),)
    return PropsResult(
        status=ComputationStatus.COMPUTABLE,
        value=tax,
        metrics={"tail_tax": tax, "curvature": curvature.value, "tail_drop": tail_drop},
        weak_fit=curvature.weak_fit,
        diagnostics=diagnostics,
    )
