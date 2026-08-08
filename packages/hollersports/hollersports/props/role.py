from __future__ import annotations

from .models import ComputationStatus, PropLadder, PropsResult, not_computable
from .surface import reconstruct_survival


def role_stability(ladders: list[PropLadder] | tuple[PropLadder, ...]) -> PropsResult:
    if len(ladders) < 2:
        return not_computable("INSUFFICIENT_EVIDENCE", "role stability requires at least two ladder snapshots")
    surfaces = [reconstruct_survival(l) for l in ladders]
    if any(s.status != ComputationStatus.COMPUTABLE for s in surfaces):
        return not_computable("INCOHERENT_LADDER", "all snapshots must be coherent")
    threshold_sets = [set(p.threshold for p in s.points) for s in surfaces]
    shared = threshold_sets[0].copy()
    for thresholds in threshold_sets[1:]:
        shared &= thresholds
    if len(shared) < 2:
        return not_computable("INSUFFICIENT_OVERLAP", "role stability requires at least two common thresholds")
    vectors = []
    for s in surfaces:
        m = {p.threshold: p.survival_probability for p in s.points}
        vectors.append([m[t] for t in sorted(shared)])
    drifts = []
    for prev, cur in zip(vectors, vectors[1:]):
        drifts.append(sum(abs(a - b) for a, b in zip(prev, cur)) / len(prev))
    instability = sum(drifts) / len(drifts)
    stability = max(0.0, 1.0 - instability)
    return PropsResult(status=ComputationStatus.COMPUTABLE, value=stability, metrics={"stability": stability, "instability": instability, "shared_thresholds": float(len(shared))}, weak_fit=any(s.weak_fit for s in surfaces), diagnostics=tuple(d for s in surfaces for d in s.diagnostics))
