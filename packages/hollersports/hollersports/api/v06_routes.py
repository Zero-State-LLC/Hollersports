"""Independent V0.6 bookmaker-intelligence API surface.

V0.5 routes remain untouched and act as the control group. Every response is
advisory-only and incapable of authorizing capital or execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from hollersports.bookmaker import BacktestRow, BookmakerQuote, MarketSnapshotStore, MarketSnapshotV2
from hollersports.bookmaker.backtest import compute_backtest_metrics
from hollersports.bookmaker.consensus import consensus_summary, weighted_consensus
from hollersports.bookmaker.devig import devig
from hollersports.bookmaker.fingerprint import bookmaker_fingerprint
from hollersports.bookmaker.pricing_residual import pricing_residuals
from hollersports.context import (
    ContextDerivation,
    ContextObservation,
    ContextResult,
    Confidence,
    ContextStorageError,
    ContextStore,
    DuplicateContextObservationError,
    PlayerState,
    compute_coach_response,
    compute_opportunity_shift,
    compute_relative_recovery_advantage,
    compute_travel_load,
    compute_venue_residual,
)
from hollersports.dependency import (
    DependencyEdge,
    DependencyMethod,
    DriverScenario,
    EmpiricalConditionalEvidence,
    LegProbability,
    analyze_parlay,
)
from hollersports.props import (
    DerivedPropSurfaceObservation,
    DuplicateObservationError,
    DuplicateSurfaceError,
    PropLadder,
    PropLadderObservation,
    PropPersistenceStore,
    PropStorageError,
    compute_curvature,
    compute_tail_tax,
    reconstruct_survival,
)
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


def _prop_store(request: Request) -> PropPersistenceStore:
    return PropPersistenceStore(request.app.state.data_root)


def _context_store(request: Request) -> ContextStore:
    return ContextStore(request.app.state.data_root)


class SingleAnalysisRequest(BaseModel):
    quote: BookmakerQuote
    consensus_quotes: tuple[BookmakerQuote, ...] = ()
    baseline_probabilities: dict[str, float] | None = None
    devig_method: str = "MULTIPLICATIVE"
    devig_parameters: dict[str, Any] = Field(default_factory=dict)
    consensus_factors: dict[str, dict[str, float]] = Field(default_factory=dict)


class FingerprintRequest(BaseModel):
    rows: list[dict[str, Any]]
    minimum_sample: int = Field(default=20, ge=1)
    ece_bins: int = Field(default=10, ge=1, le=100)


class BacktestRequest(BaseModel):
    rows: list[BacktestRow]
    minimum_sample: int = Field(default=20, ge=1)
    ece_bins: int = Field(default=10, ge=1, le=100)


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


class PropObservationRequest(BaseModel):
    observation: PropLadderObservation
    surface_id: str = Field(min_length=1)
    derived_at: datetime


class ContextObservationRequest(BaseModel):
    observation: ContextObservation
    derivation_id: str = Field(min_length=1)
    derived_at: datetime


class RecoveryAnalysisRequest(BaseModel):
    player: PlayerState
    peer: PlayerState


@router.post("/markets/snapshots")
def record_market_snapshot(body: MarketSnapshotV2, request: Request) -> dict[str, Any]:
    """Append one immutable observation. Existing observations are never updated."""
    try:
        return _snapshot_store(request).append(body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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


@router.post("/books/{book_id}/fingerprint/compute")
def compute_book_fingerprint(book_id: str, body: FingerprintRequest) -> dict[str, Any]:
    """Compute a fingerprint from caller-supplied settled historical evidence."""
    return bookmaker_fingerprint(
        book_id,
        body.rows,
        minimum_sample=body.minimum_sample,
        ece_bins=body.ece_bins,
    ).model_dump(mode="json")


@router.get("/markets/{market_id}/timeline")
def market_timeline(market_id: str, request: Request, at_or_before: datetime | None = None) -> dict[str, Any]:
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
def market_book_analysis(market_id: str, request: Request, at_or_before: datetime | None = None) -> dict[str, Any]:
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
    reconstruction = devig(
        body.quote.outcomes,
        method=body.devig_method,
        **body.devig_parameters,
    )
    if reconstruction.status != "COMPUTED":
        return _envelope(
            schema_version="SingleAnalysisPacket.v1",
            status="NOT_COMPUTABLE",
            reason=reconstruction.reason,
            fair_probability=reconstruction.model_dump(mode="json"),
        )
    fair = reconstruction.fair_probabilities
    quotes = body.consensus_quotes or (body.quote,)
    consensus = weighted_consensus(
        quotes,
        factors=body.consensus_factors or None,
        method=body.devig_method,
        method_parameters=body.devig_parameters,
    ).model_dump(mode="json")
    residual = pricing_residuals(fair, body.baseline_probabilities) if body.baseline_probabilities else None
    return _envelope(
        schema_version="SingleAnalysisPacket.v1",
        status="COMPUTED",
        observation=body.quote.model_dump(mode="json"),
        fair_probability={**reconstruction.model_dump(mode="json"), "values": fair},
        consensus=consensus,
        pricing={"bookmaker_residual": residual, "status": "COMPUTED" if residual is not None else "NOT_COMPUTABLE"},
        evidence={"bookmaker": fair, "market": consensus, "context": None, "player": None, "dependency": None},
    )


@router.post("/backtest/bookmaker")
def backtest_bookmaker(body: BacktestRequest) -> dict[str, Any]:
    metrics = compute_backtest_metrics(
        body.rows,
        min_samples=body.minimum_sample,
        ece_bins=body.ece_bins,
    )
    computable = sum(metric.status == "COMPUTABLE" for metric in metrics)
    return _envelope(
        schema_version="BookmakerBacktestPacket.v1",
        status="COMPUTED" if computable else "NOT_COMPUTABLE",
        row_count=len(body.rows),
        minimum_sample=body.minimum_sample,
        computable_metric_count=computable,
        metrics=[metric.model_dump(mode="json") for metric in metrics],
        provenance={"closing_prices_required_where_applicable": True, "settled_outcomes_required_where_applicable": True},
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


@router.post("/props/observations")
def record_prop_observation(body: PropObservationRequest, request: Request) -> dict[str, Any]:
    """Append an immutable ladder observation and its separately derived surface."""
    store = _prop_store(request)
    try:
        if store.get_ladder_observation(body.observation.observation_id) is not None:
            raise DuplicateObservationError(f"duplicate observation_id: {body.observation.observation_id}")
        if any(item.surface_id == body.surface_id for item in store.iter_surface_observations()):
            raise DuplicateSurfaceError(f"duplicate surface_id: {body.surface_id}")
        ladder_fingerprint = body.observation.fingerprint
        derived = DerivedPropSurfaceObservation(
            surface_id=body.surface_id,
            observation_id=body.observation.observation_id,
            ladder_fingerprint=ladder_fingerprint,
            market_id=body.observation.market_id,
            book_id=body.observation.book_id,
            event_id=body.observation.event_id,
            player_id=body.observation.player_id,
            player_name=body.observation.player_name,
            stat_type=body.observation.stat_type,
            observed_at=body.observation.observed_at,
            derived_at=body.derived_at,
            surface=reconstruct_survival(body.observation.ladder),
        )
        store.append_ladder_observation(body.observation)
        surface_fingerprint = store.append_surface_observation(derived)
    except (DuplicateObservationError, DuplicateSurfaceError, PropStorageError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _envelope(
        schema_version="PropPersistenceReceipt.v1",
        status="COMPUTED",
        observation_id=body.observation.observation_id,
        surface_id=body.surface_id,
        ladder_fingerprint=ladder_fingerprint,
        surface_fingerprint=surface_fingerprint,
    )


@router.get("/props/{market_id}")
@router.get("/props/{market_id}/surface")
@router.get("/props/{market_id}/ladder")
def get_prop_analysis(market_id: str, request: Request, at_or_before: datetime | None = None) -> dict[str, Any]:
    store = _prop_store(request)
    cutoff = at_or_before or datetime.now(timezone.utc)
    candidates = [item for item in store.iter_ladder_observations() if item.market_id == market_id and item.observed_at <= cutoff]
    if not candidates:
        return _envelope(schema_version="prop_ladder.v1", status="NOT_COMPUTABLE", market_id=market_id, reason="no persisted prop ladder at or before cutoff")
    ladder = max(candidates, key=lambda item: item.observed_at)
    surface = store.latest_surface_at_or_before(ladder.observation_id, cutoff)
    return _envelope(
        schema_version="prop_analysis.v1",
        status="COMPUTED" if surface is not None else "NOT_COMPUTABLE",
        market_id=market_id,
        ladder=ladder.model_dump(mode="json"),
        ladder_fingerprint=ladder.fingerprint,
        surface=surface.model_dump(mode="json") if surface is not None else None,
        reason=None if surface is not None else "no derived surface available at or before cutoff",
    )


def _derive_context(observation: ContextObservation):
    if observation.context_type == "TRAVEL":
        return compute_travel_load(observation.payload)
    if observation.context_type == "OPPORTUNITY":
        return compute_opportunity_shift(observation.payload)
    if observation.context_type == "COACHING":
        return compute_coach_response(observation.payload)
    if observation.context_type == "VENUE":
        return compute_venue_residual(observation.payload)
    return ContextResult(
        status="NOT_COMPUTABLE",
        signal="player_state_transform",
        confidence=Confidence(value=0.0, sample_size=0, method="observation_only"),
        provenance=observation.payload.provenance,
        reasons=["player state is evidence only; no calibrated distribution transform is promoted"],
    )


@router.post("/context/observations")
def record_context_observation(body: ContextObservationRequest, request: Request) -> dict[str, Any]:
    store = _context_store(request)
    result = _derive_context(body.observation)
    try:
        if any(item.observation_id == body.observation.observation_id for item in store.observations()):
            raise DuplicateContextObservationError(f"duplicate observation_id: {body.observation.observation_id}")
        if any(item.derivation_id == body.derivation_id for item in store.derivations()):
            raise ContextStorageError(f"duplicate derivation_id: {body.derivation_id}")
        derivation = ContextDerivation(
            derivation_id=body.derivation_id,
            observation_id=body.observation.observation_id,
            observation_fingerprint=body.observation.fingerprint,
            event_id=body.observation.event_id,
            entity_id=body.observation.entity_id,
            context_type=body.observation.context_type,
            observed_at=body.observation.observed_at,
            recorded_at=body.observation.recorded_at,
            derived_at=body.derived_at,
            result=result,
        )
        fingerprint, _ = store.append_bundle(body.observation, derivation)
    except (ContextStorageError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _envelope(schema_version="ContextPersistenceReceipt.v1", status=result.status, observation_fingerprint=fingerprint, derivation=derivation.model_dump(mode="json"))


@router.get("/context/{event_id}/{entity_id}/{context_type}")
def get_context_analysis(event_id: str, entity_id: str, context_type: str, request: Request, at_or_before: datetime | None = None) -> dict[str, Any]:
    if context_type not in {"PLAYER", "TRAVEL", "OPPORTUNITY", "COACHING", "VENUE"}:
        raise HTTPException(status_code=422, detail="unsupported context_type")
    found = _context_store(request).latest_at_or_before(event_id=event_id, entity_id=entity_id, context_type=context_type, as_of=at_or_before or datetime.now(timezone.utc))
    if found is None:
        return _envelope(schema_version="ContextAnalysisPacket.v1", status="NOT_COMPUTABLE", reason="no context observation at or before cutoff")
    observation, derivation = found
    return _envelope(
        schema_version="ContextAnalysisPacket.v1",
        status=derivation.result.status if derivation is not None else "NOT_COMPUTABLE",
        evidence={"context": observation.model_dump(mode="json"), "bookmaker": None, "market": None, "player": {"observation_id": observation.observation_id, "fingerprint": observation.fingerprint} if context_type == "PLAYER" else None, "dependency": None},
        derivation=derivation.model_dump(mode="json") if derivation is not None else None,
        reason=None if derivation is not None else "no derivation available at or before cutoff",
    )


@router.post("/context/recovery")
def analyze_recovery(body: RecoveryAnalysisRequest) -> dict[str, Any]:
    return _envelope(schema_version="RecoveryContextPacket.v1", **compute_relative_recovery_advantage(body.player, body.peer).model_dump(mode="json"))


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


@router.get("/health/context")
def context_health(request: Request) -> dict[str, Any]:
    store = _context_store(request)
    try:
        observations = store.observations()
        derivations = store.derivations()
        issues = store.integrity_issues()
    except (ValueError, OSError) as exc:
        return _envelope(
            schema_version="ContextHealthPacket.v1", status="NOT_COMPUTABLE",
            observation_count=None, derivation_count=None, integrity_issues=[f"unreadable context ledger: {exc}"],
            recorded_at_gate=True, api_bundled_write_lock=True, unknown_payload_fields_rejected=True,
        )
    return _envelope(
        schema_version="ContextHealthPacket.v1",
        status="PASS" if not issues else "NOT_COMPUTABLE",
        observation_count=len(observations), derivation_count=len(derivations), integrity_issues=issues,
        recorded_at_gate=True, api_bundled_write_lock=True, unknown_payload_fields_rejected=True,
    )
