from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .models import ComputationStatus, Diagnostic, PropLadder, PropsResult, not_computable
from .surface import reconstruct_survival


class PairwiseDistributionConflict(BaseModel):
    model_config = ConfigDict(frozen=True)

    left_source: str
    right_source: str
    status: ComputationStatus
    mean_abs_conflict: float | None = None
    max_abs_conflict: float | None = None
    shared_thresholds: int = 0
    diagnostics: tuple[Diagnostic, ...] = ()
    weak_fit: bool = False


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


def pairwise_distribution_conflicts(ladders: dict[str, PropLadder]) -> tuple[PairwiseDistributionConflict, ...]:
    """Compare named source ladders pairwise without merging or collapsing sources."""
    names = sorted(ladders)
    conflicts: list[PairwiseDistributionConflict] = []
    for i, left_name in enumerate(names):
        for right_name in names[i + 1 :]:
            left = reconstruct_survival(ladders[left_name])
            right = reconstruct_survival(ladders[right_name])
            if left.status != ComputationStatus.COMPUTABLE or right.status != ComputationStatus.COMPUTABLE:
                conflicts.append(
                    PairwiseDistributionConflict(
                        left_source=left_name,
                        right_source=right_name,
                        status=ComputationStatus.NOT_COMPUTABLE,
                        diagnostics=(Diagnostic(code="INSUFFICIENT_EVIDENCE", message="both named source ladders must be coherent"),),
                        weak_fit=True,
                    )
                )
                continue
            right_map = {p.threshold: p.survival_probability for p in right.points}
            shared = [(p.survival_probability, right_map[p.threshold]) for p in left.points if p.threshold in right_map]
            if len(shared) < 2:
                conflicts.append(
                    PairwiseDistributionConflict(
                        left_source=left_name,
                        right_source=right_name,
                        status=ComputationStatus.NOT_COMPUTABLE,
                        shared_thresholds=len(shared),
                        diagnostics=(Diagnostic(code="INSUFFICIENT_OVERLAP", message="pairwise conflict requires at least two shared thresholds"),),
                        weak_fit=left.weak_fit or right.weak_fit,
                    )
                )
                continue
            diffs = [abs(a - b) for a, b in shared]
            conflicts.append(
                PairwiseDistributionConflict(
                    left_source=left_name,
                    right_source=right_name,
                    status=ComputationStatus.COMPUTABLE,
                    mean_abs_conflict=sum(diffs) / len(diffs),
                    max_abs_conflict=max(diffs),
                    shared_thresholds=len(shared),
                    diagnostics=left.diagnostics + right.diagnostics,
                    weak_fit=left.weak_fit or right.weak_fit,
                )
            )
    return tuple(conflicts)
