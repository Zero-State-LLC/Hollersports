"""Inspectable dependency graph utilities."""
from __future__ import annotations
from pydantic import Field
from .models import AdvisoryModel, Computability, DependencyEdge, LegProbability

class DependencyGraphSnapshot(AdvisoryModel):
    status: Computability = Computability.COMPUTABLE
    legs: list[LegProbability] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)
    missing_required_dependencies: list[str] = Field(default_factory=list)
    adjacency: dict[str, list[dict[str, object]]] = Field(default_factory=dict)

def inspect_dependency_graph(legs: list[LegProbability], edges: list[DependencyEdge]) -> DependencyGraphSnapshot:
    leg_ids = {leg.leg_id for leg in legs}
    missing: list[str] = []
    adjacency: dict[str, list[dict[str, object]]] = {leg_id: [] for leg_id in leg_ids}
    for edge in edges:
        absent = [node for node in (edge.source_leg_id, edge.target_leg_id) if node not in leg_ids]
        if absent and (edge.required or edge.dependency_type == "required"):
            missing.append(f"{edge.source_leg_id}->{edge.target_leg_id}")
        adjacency.setdefault(edge.source_leg_id, []).append(edge.model_dump())
    status = Computability.NOT_COMPUTABLE if missing else Computability.COMPUTABLE
    return DependencyGraphSnapshot(status=status, legs=legs, edges=edges, missing_required_dependencies=missing, adjacency=adjacency)
