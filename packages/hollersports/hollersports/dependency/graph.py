"""Inspectable dependency graph utilities."""
from __future__ import annotations
from pydantic import Field
from .models import AdvisoryModel, Computability, DependencyEdge, LegProbability

class DependencyGraphSnapshot(AdvisoryModel):
    status: Computability = Computability.COMPUTABLE
    legs: list[LegProbability] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)
    missing_required_dependencies: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    adjacency: dict[str, list[dict[str, object]]] = Field(default_factory=dict)

def inspect_dependency_graph(legs: list[LegProbability], edges: list[DependencyEdge]) -> DependencyGraphSnapshot:
    ordered_leg_ids = [leg.leg_id for leg in legs]
    leg_ids = set(ordered_leg_ids)
    missing: list[str] = []
    errors: list[str] = []
    if len(ordered_leg_ids) != len(leg_ids):
        errors.append("duplicate leg_id")
    adjacency: dict[str, list[dict[str, object]]] = {leg_id: [] for leg_id in leg_ids}
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        absent = [node for node in (edge.source_leg_id, edge.target_leg_id) if node not in leg_ids]
        if absent:
            label = f"{edge.source_leg_id}->{edge.target_leg_id}"
            errors.append(f"edge endpoint missing: {label}")
            if edge.required or edge.dependency_type == "required":
                missing.append(label)
        if edge.source_leg_id == edge.target_leg_id:
            errors.append(f"self dependency: {edge.source_leg_id}")
        identity = (edge.source_leg_id, edge.target_leg_id, edge.dependency_type)
        if identity in seen_edges:
            errors.append(f"duplicate dependency edge: {edge.source_leg_id}->{edge.target_leg_id}")
        seen_edges.add(identity)
        adjacency.setdefault(edge.source_leg_id, []).append(edge.model_dump())
    status = Computability.NOT_COMPUTABLE if missing or errors else Computability.COMPUTABLE
    return DependencyGraphSnapshot(status=status, legs=legs, edges=edges, missing_required_dependencies=missing, validation_errors=errors, adjacency=adjacency)
