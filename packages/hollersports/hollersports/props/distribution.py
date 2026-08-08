from __future__ import annotations

from .models import ComputationStatus, PropLadder, PropsResult, not_computable
from .surface import reconstruct_survival


def distribution_conflict(reference: PropLadder, candidate: PropLadder) -> PropsResult:
    ref = reconstruct_survival(reference)
    cand = reconstruct_survival(candidate)
    if ref.status != ComputationStatus.COMPUTABLE or cand.status != ComputationStatus.COMPUTABLE:
        return not_computable("INSUFFICIENT_EVIDENCE", "both ladders must be coherent")
    c_map = {p.threshold: p.survival_probability for p in cand.points}
    shared = [(p.survival_probability, c_map[p.threshold]) for p in ref.points if p.threshold in c_map]
    if len(shared) < 2:
        return not_computable("INSUFFICIENT_OVERLAP", "distribution conflict requires at least two shared thresholds")
    mean_abs = sum(abs(a - b) for a, b in shared) / len(shared)
    max_abs = max(abs(a - b) for a, b in shared)
    return PropsResult(status=ComputationStatus.COMPUTABLE, value=mean_abs, metrics={"mean_abs_conflict": mean_abs, "max_abs_conflict": max_abs, "shared_thresholds": float(len(shared))}, weak_fit=ref.weak_fit or cand.weak_fit, diagnostics=ref.diagnostics + cand.diagnostics)
