"""Parlay dependency analysis and marginal leg values."""
from __future__ import annotations
from pydantic import Field
from .joint import joint_probability
from .models import AdvisoryModel, Computability, DependencyEdge, DependencyMethod, JointProbabilityResult, LegProbability

class MarginalLegValue(AdvisoryModel):
    leg_id: str
    with_leg_probability: float | None = None
    without_leg_probability: float | None = None
    delta_probability: float | None = None
    status: Computability = Computability.NOT_COMPUTABLE
    reason: str | None = None

class ParlayAnalysis(AdvisoryModel):
    status: Computability
    joint: JointProbabilityResult
    correlation_tax: float | None = None
    correlation_tax_decomposition: dict[str, float] = Field(default_factory=dict)
    marginal_leg_values: list[MarginalLegValue] = Field(default_factory=list)
    reason: str | None = None

def analyze_parlay(legs: list[LegProbability], edges: list[DependencyEdge] | None = None, *, method: DependencyMethod | None = None, explicitly_allow_independence: bool = False, empirical_evidence=None, driver_scenarios=None) -> ParlayAnalysis:
    joint = joint_probability(legs, edges, method=method, explicitly_allow_independence=explicitly_allow_independence, empirical_evidence=empirical_evidence, driver_scenarios=driver_scenarios)
    if joint.status is Computability.NOT_COMPUTABLE or joint.joint_probability is None:
        return ParlayAnalysis(status=Computability.NOT_COMPUTABLE, joint=joint, reason=joint.reason)
    marginals: list[MarginalLegValue] = []
    if method == DependencyMethod.INDEPENDENT and explicitly_allow_independence:
        for leg in legs:
            others = [other for other in legs if other.leg_id != leg.leg_id]
            without = joint_probability(others, [], method=method, explicitly_allow_independence=True).joint_probability if others else 1.0
            marginals.append(MarginalLegValue(leg_id=leg.leg_id, with_leg_probability=joint.joint_probability, without_leg_probability=without, delta_probability=(joint.joint_probability - (without or 0.0)), status=Computability.COMPUTABLE))
    else:
        marginals = [MarginalLegValue(leg_id=leg.leg_id, reason="marginal leg value requires recomputable evidence for subset; independent-only subset supported") for leg in legs]
    return ParlayAnalysis(status=Computability.COMPUTABLE, joint=joint, correlation_tax=joint.correlation_tax, correlation_tax_decomposition=joint.decomposition, marginal_leg_values=marginals)
