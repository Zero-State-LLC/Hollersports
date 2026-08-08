"""Deterministic V0.6 structural synthesis.

This rune combines already-derived evidence. It never invents probabilities and it
never grants execution authority. Thresholds must be supplied from calibration,
not embedded as product intuition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class StructuralVerdict(str, Enum):
    VALUE_ALIGNED = "VALUE_ALIGNED"
    HOUSE_ALIGNED = "HOUSE_ALIGNED"
    RETAIL_PRICED = "RETAIL_PRICED"
    CORRELATED_FAIRLY_PRICED = "CORRELATED_FAIRLY_PRICED"
    CORRELATED_OVERPRICED = "CORRELATED_OVERPRICED"
    CONFLICT = "CONFLICT"
    NO_EDGE = "NO_EDGE"
    PASS = "PASS"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"


@dataclass(frozen=True)
class StructuralThresholds:
    """Calibration-owned thresholds required by :func:`structural_verdict`."""

    minimum_data_quality: float
    maximum_market_entropy: float
    minimum_dependency_confidence: float
    edge_probability_points: float
    conflict_probability_points: float
    fair_pricing_tolerance: float

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


def _packet(verdict: StructuralVerdict, reasons: list[str], evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "StructuralVerdictPacket.v1",
        "status": verdict.value,
        "verdict": verdict.value,
        "reasons": reasons,
        "evidence": dict(evidence),
        "authority": "SHADOW_ONLY",
        "mode": "ADVISORY_ONLY",
        "capital_authority": False,
        "execution_authority": False,
        "provenance": {"derivation": "RUNE.STRUCTURAL_VERDICT", "threshold_source": "CALIBRATION_REQUIRED"},
    }


def structural_verdict(
    *,
    book_probability: float | None,
    consensus_probability: float | None,
    reality_probability: float | None,
    data_quality: float,
    market_entropy: float,
    thresholds: StructuralThresholds | None,
    dependency_required: bool = False,
    dependency_confidence: float | None = None,
    joint_probability: float | None = None,
    book_joint_probability: float | None = None,
    context_reference: str | None = None,
    context_confidence: float | None = None,
) -> dict[str, Any]:
    """Return a bounded verdict from separated evidence families.

    Missing calibrated thresholds is deliberately ``NOT_COMPUTABLE``. For parlays,
    a dependency estimate is mandatory unless dependency is explicitly not required.
    """

    evidence = {
        "bookmaker": {"probability": book_probability, "joint_probability": book_joint_probability},
        "market": {"consensus_probability": consensus_probability, "entropy": market_entropy},
        "player": {"reality_probability": reality_probability},
        "context": {"reference": context_reference, "confidence": context_confidence},
        "dependency": {"required": dependency_required, "confidence": dependency_confidence, "joint_probability": joint_probability},
        "data_quality": data_quality,
    }
    if thresholds is None:
        return _packet(StructuralVerdict.NOT_COMPUTABLE, ["calibrated thresholds are required"], evidence)
    supplied = [book_probability, consensus_probability, reality_probability]
    if any(value is None or not 0.0 <= value <= 1.0 for value in supplied):
        return _packet(StructuralVerdict.NOT_COMPUTABLE, ["book, consensus, and reality probabilities are required"], evidence)
    if not 0.0 <= data_quality <= 1.0 or not 0.0 <= market_entropy <= 1.0:
        return _packet(StructuralVerdict.NOT_COMPUTABLE, ["quality and entropy must be bounded"], evidence)
    if data_quality < thresholds.minimum_data_quality:
        return _packet(StructuralVerdict.NOT_COMPUTABLE, ["data quality below calibrated minimum"], evidence)
    if market_entropy > thresholds.maximum_market_entropy:
        return _packet(StructuralVerdict.PASS, ["market disagreement exceeds calibrated entropy limit"], evidence)
    if dependency_required:
        if dependency_confidence is None or dependency_confidence < thresholds.minimum_dependency_confidence:
            return _packet(StructuralVerdict.NOT_COMPUTABLE, ["dependency evidence is inadequate"], evidence)
        if joint_probability is None or book_joint_probability is None:
            return _packet(StructuralVerdict.NOT_COMPUTABLE, ["joint and book joint probabilities are required"], evidence)
        if not 0.0 <= joint_probability <= 1.0 or not 0.0 <= book_joint_probability <= 1.0:
            return _packet(StructuralVerdict.NOT_COMPUTABLE, ["joint probabilities must be bounded"], evidence)
        delta = book_joint_probability - joint_probability
        if delta > thresholds.fair_pricing_tolerance:
            return _packet(StructuralVerdict.CORRELATED_OVERPRICED, ["book joint price exceeds modeled joint probability"], evidence)
        return _packet(StructuralVerdict.CORRELATED_FAIRLY_PRICED, ["joint price is within calibrated tolerance"], evidence)

    book = float(book_probability)
    consensus = float(consensus_probability)
    reality = float(reality_probability)
    if abs(consensus - reality) > thresholds.conflict_probability_points:
        return _packet(StructuralVerdict.CONFLICT, ["market and player evidence conflict"], evidence)
    reference = (consensus + reality) / 2.0
    residual = book - reference
    if residual > thresholds.edge_probability_points:
        return _packet(StructuralVerdict.RETAIL_PRICED, ["offered implied probability materially exceeds reconstructed references"], evidence)
    if residual < -thresholds.edge_probability_points:
        return _packet(StructuralVerdict.VALUE_ALIGNED, ["offered implied probability is below aligned reconstructed references"], evidence)
    if abs(book - consensus) <= thresholds.fair_pricing_tolerance and abs(book - reality) <= thresholds.fair_pricing_tolerance:
        return _packet(StructuralVerdict.HOUSE_ALIGNED, ["book, market, and player evidence agree"], evidence)
    return _packet(StructuralVerdict.NO_EDGE, ["no calibrated structural separation"], evidence)
