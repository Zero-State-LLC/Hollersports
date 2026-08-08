"""Independent V0.6 bookmaker-intelligence API surface.

V0.5 routes remain untouched and act as the control group. Every response is
advisory-only and incapable of authorizing capital or execution.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from hollersports.bookmaker import BookmakerQuote, MarketSnapshotStore, MarketSnapshotV2
from hollersports.bookmaker.consensus import consensus_summary
from hollersports.bookmaker.devig import proportional_devig
from hollersports.bookmaker.pricing_residual import pricing_residuals
from hollersports.dependency import (
    DependencyEdge,
    DependencyMethod,
    DriverScenario,
    EmpiricalConditionalEvidence,
    LegProbability,
    analyze_parlay,
)
from hollersports.props import PropLadder, compute_curvature, compute_tail_tax, reconstruct_survival
from hollersports.runes.structural_verdict import StructuralThresholds, structural_verdict

router = APIRouter(prefix="/v1")


def _envelope(**values: Any) -> dict[str, Any]:
    return {
        **values,
        "authority": "SHADOW_ONLY",
        "mode": "ADVISORY_ONLY",
        "capital_authority": False,
        "execution_authority": False,
    }


def _snapshot_store(request: Request) -> MarketSnapshotStore:
    return MarketSnapshotStore(request.app.state.data_root)


class SingleAnalysisRequest(BaseModel):
    quote: BookmakerQuote
    consensus_quotes: tuple[BookmakerQuote, ...] = ()
    baseline_probabilities: dict[str, float] | None = None


class ParlayAnalysisRequest(BaseModel):
    legs: list[LegProbability] = Field(min_length=2)
    edges: list[DependencyEdge] = Field(default_factory=list)
    method: DependencyMethod | None = None
    explicitly_allow_independence: bool = False
    empirical_evidence: EmpiricalConditionalEvidence | None = None
    driver_scenarios: list[DriverScenario] | None = None


class StructuralAnalysisRequest(BaseModel):
    book_probability: float | None = None
    consensus_probability: float | None = None
    reality_probability: float | None = None
    data_quality: float = 0.0
    market_entropy: float = 1.0
    thresholds: StructuralThresholds | None = None
    dependency_required: bool = False
    dependency_confidence: float | None = None
    joint_probability: float | None = None
    book_joint_probability: float | None = None


@router.post("/markets/snapshots")
def record_market_snapshot(body: MarketSnapshotV2, request: Request) -> dict[str, Any]:
    """Append one immutable observation. Existing observations are never updated."""
    return _snapshot_store(request).append(body)


@router.get("/books")
def list_books(request: Request) -> dict[str, Any]:
    snapshots = _snapshot_store(request).query()
    books = sorted({quote.bookmaker for snapshot in snapshots for quote in snapshot.quotes})
    return _envelope(schema_version="BookmakerListPacket.v1", status="COMPUTED", books=books)


@router.get("/books/{book_id}/fingerprint")
def get_book_fingerprint(book_id: str, request: Request) -> dict[str, Any]:
    observations = [
        quote
        for snapshot in _snapshot_store(request).query()
        for quote in snapshot.quotes
        if quote.bookmaker == book_id
    ]
    return _envelope(
        schema_version="BookmakerFingerprintPacket.v1",
        status="NOT_COMPUTABLE",
        book_id=book_id,
        observed_quotes=len(observations),
        reason="settled and closing calibration samples are required for a bookmaker fingerprint",
    )


@router.get("/markets/{market_id}/timeline")
def market_timeline(market_id: str, request: Request, at_or_before: str | None = None) -> dict[str, Any]:
    snapshots = [
        item for item in _snapshot_store(request).query(end_at=at_or_before)
        if any(quote.market_id == market_id for quote in item.quotes)
    ]
    return _envelope(
        schema_version="MarketTimelinePacket.v1",
        status="COMPUTED" if snapshots else "NOT_COMPUTABLE",
        market_id=market_id,
        observations=[item.model_dump(mode="json") for item in snapshots],
        reason=None if snapshots else "no observations for market",
    )


@router.get("/markets/{market_id}/book-analysis")
def market_book_analysis(market_id: str, request: Request, at_or_before: str | None = None) -> dict[str, Any]:
    snapshots = [
        item for item in _snapshot_store(request).query(end_at=at_or_before)
        if any(quote.market_id == market_id for quote in item.quotes)
    ]
    if not snapshots:
        return _envelope(schema_version="BookPriceAnalysis.v1", status="NOT_COMPUTABLE", market_id=market_id, reason="no observations for market")
    latest = snapshots[-1]
    quotes = tuple(quote for quote in latest.quotes if quote.market_id == market_id)
    return _envelope(
        schema_version="BookPriceAnalysis.v1",
        status="COMPUTED",
        market_id=market_id,
        market_snapshot_id=latest.snapshot_id,
        consensus=consensus_summary(quotes),
        provenance={"snapshot_fingerprint": latest.fingerprint, "captured_at": latest.captured_at},
    )


@router.post("/analyze/single")
def analyze_single(body: SingleAnalysisRequest) -> dict[str, Any]:
    fair = proportional_devig(body.quote.outcomes)
    if fair is None:
        return _envelope(schema_version="SingleAnalysisPacket.v1", status="NOT_COMPUTABLE", reason="complete paired prices are required")
    quotes = body.consensus_quotes or (body.quote,)
    consensus = consensus_summary(quotes)
    residual = pricing_residuals(fair, body.baseline_probabilities) if body.baseline_probabilities else None
    return _envelope(
        schema_version="SingleAnalysisPacket.v1",
        status="COMPUTED",
        observation=body.quote.model_dump(mode="json"),
        fair_probability={"method": "MULTIPLICATIVE", "values": fair},
        consensus=consensus,
        pricing={"bookmaker_residual": residual, "status": "COMPUTED" if residual is not None else "NOT_COMPUTABLE"},
        evidence={"bookmaker": fair, "market": consensus, "context": None, "player": None, "dependency": None},
    )


@router.post("/analyze/parlay")
@router.post("/parlay/xray")
@router.post("/parlay/surgery")
def parlay_analysis(body: ParlayAnalysisRequest) -> dict[str, Any]:
    result = analyze_parlay(
        body.legs,
        body.edges,
        method=body.method,
        explicitly_allow_independence=body.explicitly_allow_independence,
        empirical_evidence=body.empirical_evidence,
        driver_scenarios=body.driver_scenarios,
    )
    return _envelope(schema_version="parlay_analysis.v1", **result.model_dump(mode="json"))


@router.post("/props/surface")
def prop_surface(body: PropLadder) -> dict[str, Any]:
    surface = reconstruct_survival(body)
    curvature = compute_curvature(body)
    tail_tax = compute_tail_tax(body)
    return _envelope(
        schema_version="prop_surface.v1",
        ladder=body.model_dump(mode="json"),
        surface=surface.model_dump(mode="json"),
        curvature=curvature.model_dump(mode="json"),
        tail_tax=tail_tax.model_dump(mode="json"),
        status=surface.status.value,
    )


@router.get("/props/{market_id}")
@router.get("/props/{market_id}/surface")
@router.get("/props/{market_id}/ladder")
def get_prop_analysis(market_id: str) -> dict[str, Any]:
    return _envelope(schema_version="prop_ladder.v1", status="NOT_COMPUTABLE", market_id=market_id, reason="no persisted prop ladder was supplied")


@router.post("/structural-verdict")
def analyze_structure(body: StructuralAnalysisRequest) -> dict[str, Any]:
    return structural_verdict(**body.model_dump())


@router.get("/health/bookmaker")
def bookmaker_health(request: Request) -> dict[str, Any]:
    count = len(_snapshot_store(request).query())
    return _envelope(schema_version="BookmakerHealthPacket.v1", status="PASS", snapshot_count=count, append_only=True)


@router.get("/health/dependency")
def dependency_health() -> dict[str, Any]:
    return _envelope(schema_version="DependencyHealthPacket.v1", status="PASS", unknown_dependency_policy="NOT_COMPUTABLE", naive_multiplication_default=False)
