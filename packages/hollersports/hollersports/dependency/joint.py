"""Joint probability methods with fail-closed dependency handling."""
from __future__ import annotations
from math import prod
from .graph import inspect_dependency_graph
from .models import Computability, DependencyEdge, DependencyMethod, DriverScenario, EmpiricalConditionalEvidence, JointProbabilityResult, LegProbability

def _cap(joint: float, legs: list[LegProbability]) -> tuple[float, float]:
    marginal_cap = min((leg.marginal_probability for leg in legs), default=0.0)
    return min(joint, marginal_cap), marginal_cap

def _tax(independent_joint: float, bounded_joint: float) -> float:
    return max(0.0, independent_joint - bounded_joint)

def _benefit(independent_joint: float, bounded_joint: float) -> float:
    return max(0.0, bounded_joint - independent_joint)

def independent_joint_probability(legs: list[LegProbability], *, explicitly_allowed: bool = False) -> JointProbabilityResult:
    if not explicitly_allowed:
        return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason="independence requires explicit allow flag")
    raw = prod(leg.marginal_probability for leg in legs)
    joint, marginal_cap = _cap(raw, legs)
    return JointProbabilityResult(status=Computability.COMPUTABLE, method=DependencyMethod.INDEPENDENT, joint_probability=joint, marginal_cap=marginal_cap, correlation_tax=0.0, dependency_benefit=0.0, decomposition={"independent_joint": raw, "marginal_cap_adjustment": raw - joint})

def empirical_conditional_joint_probability(legs: list[LegProbability], evidence: EmpiricalConditionalEvidence | None) -> JointProbabilityResult:
    if evidence is None:
        return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason="empirical conditional evidence is required")
    if evidence.sample_size is None or evidence.sample_size <= 0:
        return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason="empirical conditional evidence requires a positive sample size")
    by_id = {leg.leg_id: leg for leg in legs}
    if set(evidence.ordered_leg_ids) != set(by_id):
        return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason="conditional evidence must cover exactly all legs")
    joint = 1.0
    missing: list[str] = []
    for index, leg_id in enumerate(evidence.ordered_leg_ids):
        key = leg_id if index == 0 else f"{leg_id}|" + ",".join(evidence.ordered_leg_ids[:index])
        if key not in evidence.conditional_probabilities:
            missing.append(key)
        else:
            joint *= evidence.conditional_probabilities[key]
    if missing:
        return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason="missing conditional probabilities: " + ", ".join(missing))
    bounded, marginal_cap = _cap(joint, legs)
    independent = prod(leg.marginal_probability for leg in legs)
    return JointProbabilityResult(status=Computability.COMPUTABLE, method=DependencyMethod.EMPIRICAL_CONDITIONAL, joint_probability=bounded, marginal_cap=marginal_cap, correlation_tax=_tax(independent, bounded), dependency_benefit=_benefit(independent, bounded), decomposition={"raw_conditional_joint": joint, "independent_joint": independent, "marginal_cap_adjustment": joint - bounded, "sample_size": float(evidence.sample_size)})

def deterministic_driver_joint_probability(legs: list[LegProbability], scenarios: list[DriverScenario] | None) -> JointProbabilityResult:
    if not scenarios:
        return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason="shared-driver scenario evidence is required")
    leg_ids = {leg.leg_id for leg in legs}
    total_weight = sum(s.probability for s in scenarios)
    if abs(total_weight - 1.0) > 1e-9:
        return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason="driver scenario probabilities must sum to 1")
    joint = 0.0
    for scenario in scenarios:
        if set(scenario.leg_probabilities) != leg_ids:
            return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason=f"scenario {scenario.scenario_id} must cover exactly all legs")
        joint += scenario.probability * prod(scenario.leg_probabilities[leg_id] for leg_id in leg_ids)
    bounded, marginal_cap = _cap(joint, legs)
    independent = prod(leg.marginal_probability for leg in legs)
    return JointProbabilityResult(status=Computability.COMPUTABLE, method=DependencyMethod.DETERMINISTIC_MONTE_CARLO, joint_probability=bounded, marginal_cap=marginal_cap, correlation_tax=_tax(independent, bounded), dependency_benefit=_benefit(independent, bounded), decomposition={"raw_driver_joint": joint, "independent_joint": independent, "marginal_cap_adjustment": joint - bounded})

def joint_probability(legs: list[LegProbability], edges: list[DependencyEdge] | None = None, *, method: DependencyMethod | None = None, explicitly_allow_independence: bool = False, empirical_evidence: EmpiricalConditionalEvidence | None = None, driver_scenarios: list[DriverScenario] | None = None) -> JointProbabilityResult:
    graph = inspect_dependency_graph(legs, edges or [])
    if graph.status is Computability.NOT_COMPUTABLE:
        return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason="missing required dependency: " + ", ".join(graph.missing_required_dependencies))
    if method == DependencyMethod.INDEPENDENT:
        return independent_joint_probability(legs, explicitly_allowed=explicitly_allow_independence)
    if method == DependencyMethod.EMPIRICAL_CONDITIONAL:
        return empirical_conditional_joint_probability(legs, empirical_evidence)
    if method == DependencyMethod.DETERMINISTIC_MONTE_CARLO:
        return deterministic_driver_joint_probability(legs, driver_scenarios)
    return JointProbabilityResult(status=Computability.NOT_COMPUTABLE, reason="dependency method evidence is required; independence is not assumed")
