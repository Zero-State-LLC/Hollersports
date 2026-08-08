from __future__ import annotations

from .models import ComputationStatus, PropLadder, PropsResult, coherent_points, not_computable, sorted_over_points


def validate_ladder(ladder: PropLadder, *, min_points: int = 2) -> PropsResult:
    points = sorted_over_points(ladder)
    ok, reason = coherent_points(points, min_points=min_points)
    if not ok:
        return not_computable("INCOHERENT_LADDER", reason or "incoherent ladder")
    monotonic = all(points[i][1] >= points[i + 1][1] for i in range(len(points) - 1))
    if not monotonic:
        return PropsResult(status=ComputationStatus.COMPUTABLE, value=0.0, metrics={"points": float(len(points))}, weak_fit=True)
    return PropsResult(status=ComputationStatus.COMPUTABLE, value=1.0, metrics={"points": float(len(points))})
