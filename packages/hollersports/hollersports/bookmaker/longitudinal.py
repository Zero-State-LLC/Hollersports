from __future__ import annotations

import json
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .fingerprint import stable_fingerprint
from .models import BookmakerQuote, MarketSnapshotV2, OutcomePrice


class LongitudinalThresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    minimum_probability_move: float = Field(gt=0, le=1)
    follow_window_seconds: int = Field(gt=0)
    minimum_pressure_imbalance: float = Field(gt=0, le=1)
    maximum_resistant_move: float = Field(ge=0, le=1)
    minimum_lead_events: int = Field(default=1, ge=1)


class BookMove(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    bookmaker: str
    from_time: datetime
    to_time: datetime
    probability_delta: float
    threshold_delta: float | None = None
    velocity_per_hour: float
    threshold_velocity_per_hour: float | None = None


class LeadLagEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    leader_book: str
    follower_book: str
    leader_time: datetime
    follower_time: datetime
    lag_seconds: float
    direction: Literal[-1, 1]


class PressureObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    bookmaker: str
    ticket_pct: float
    handle_pct: float
    imbalance: float
    probability_move: float
    elasticity: float | None = None
    resistance_observed: bool
    causal_attribution: Literal["UNKNOWN"] = "UNKNOWN"


class LongitudinalAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["BookmakerLongitudinalAnalysis.v1"] = "BookmakerLongitudinalAnalysis.v1"
    status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    event_id: str
    market_id: str
    market_type: str
    selection: str
    probability_basis: Literal["RAW_IMPLIED_OBSERVATION"] = "RAW_IMPLIED_OBSERVATION"
    as_of: datetime
    snapshot_fingerprints: tuple[str, ...] = ()
    moves: tuple[BookMove, ...] = ()
    lead_lag_events: tuple[LeadLagEvent, ...] = ()
    leader_counts: dict[str, int] = Field(default_factory=dict)
    follow_counts: dict[str, int] = Field(default_factory=dict)
    pressure: tuple[PressureObservation, ...] = ()
    movement_status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    lead_lag_status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    pressure_status: Literal["COMPUTED", "NOT_COMPUTABLE"]
    metric_reasons: dict[str, str] = Field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False


class LongitudinalRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    analysis_id: str = Field(min_length=1)
    analyzed_at: datetime
    analysis: LongitudinalAnalysis
    analysis_fingerprint: str = Field(min_length=1)

    @field_validator("analyzed_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("analyzed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def temporal(self) -> "LongitudinalRecord":
        if self.analyzed_at < self.analysis.as_of:
            raise ValueError("analyzed_at cannot precede analysis as_of")
        return self


def _probability(outcome: OutcomePrice) -> float | None:
    if outcome.observed_probability is not None:
        return outcome.observed_probability
    if outcome.decimal_odds is not None:
        return 1.0 / outcome.decimal_odds
    if outcome.american_odds is None:
        return None
    odds = outcome.american_odds
    return 100.0 / (odds + 100.0) if odds > 0 else (-odds) / ((-odds) + 100.0)


def _find(quote: BookmakerQuote, selection: str) -> tuple[float, float | None] | None:
    for outcome in quote.outcomes:
        if outcome.selection == selection:
            probability = _probability(outcome)
            return None if probability is None else (probability, outcome.point)
    return None


def analyze_longitudinal_market(
    snapshots: list[MarketSnapshotV2],
    market_id: str,
    selection: str,
    as_of: datetime,
    thresholds: LongitudinalThresholds,
    *,
    event_id: str | None = None,
) -> LongitudinalAnalysis:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    cutoff = as_of.astimezone(timezone.utc)
    candidates = [
        snapshot
        for snapshot in snapshots
        if snapshot.captured_at <= cutoff
        and any(quote.market_id == market_id for quote in snapshot.quotes)
    ]
    event_ids = {
        quote.event_id
        for snapshot in candidates
        for quote in snapshot.quotes
        if quote.market_id == market_id
    }
    selected_event = event_id or (next(iter(event_ids)) if len(event_ids) == 1 else None)
    if selected_event is None:
        reason = "event_id is required when a market_id appears in zero or multiple events"
        return LongitudinalAnalysis(
            status="NOT_COMPUTABLE",
            event_id=event_id or "UNKNOWN",
            market_id=market_id,
            market_type="UNKNOWN",
            selection=selection,
            as_of=cutoff,
            movement_status="NOT_COMPUTABLE",
            lead_lag_status="NOT_COMPUTABLE",
            pressure_status="NOT_COMPUTABLE",
            metric_reasons={"movement": reason, "lead_lag": reason, "pressure": reason},
            reasons=(reason,),
        )
    scoped = [
        snapshot
        for snapshot in candidates
        if any(
            quote.market_id == market_id and quote.event_id == selected_event
            for quote in snapshot.quotes
        )
    ]
    scoped.sort(key=lambda item: (item.captured_at, item.snapshot_id))
    fingerprints = tuple(snapshot.fingerprint or stable_fingerprint(snapshot.model_dump(mode="json")) for snapshot in scoped)
    series: dict[str, list[tuple[datetime, float, float | None, dict]]] = {}
    for snapshot in scoped:
        for quote in snapshot.quotes:
            if quote.market_id != market_id or quote.event_id != selected_event:
                continue
            found = _find(quote, selection)
            if found is None:
                continue
            probability, point = found
            series.setdefault(quote.bookmaker, []).append((quote.fetched_at, probability, point, quote.metadata))
    moves: list[BookMove] = []
    qualifying: list[tuple[datetime, str, int]] = []
    pressure: list[PressureObservation] = []
    for bookmaker, points in series.items():
        points.sort(key=lambda row: row[0])
        for previous, current in zip(points, points[1:]):
            seconds = (current[0] - previous[0]).total_seconds()
            if seconds <= 0:
                continue
            delta = current[1] - previous[1]
            threshold_delta = None if previous[2] is None or current[2] is None else current[2] - previous[2]
            moves.append(BookMove(
                bookmaker=bookmaker,
                from_time=previous[0],
                to_time=current[0],
                probability_delta=delta,
                threshold_delta=threshold_delta,
                velocity_per_hour=delta / (seconds / 3600.0),
                threshold_velocity_per_hour=None if threshold_delta is None else threshold_delta / (seconds / 3600.0),
            ))
            if abs(delta) >= thresholds.minimum_probability_move:
                qualifying.append((current[0], bookmaker, 1 if delta > 0 else -1))
            tickets, handle = current[3].get("ticket_pct"), current[3].get("handle_pct")
            if tickets is not None and handle is not None:
                try:
                    ticket_value, handle_value = float(tickets), float(handle)
                except (TypeError, ValueError):
                    continue
                if 0 <= ticket_value <= 1 and 0 <= handle_value <= 1:
                    imbalance = handle_value - ticket_value
                    elasticity = abs(delta) / abs(imbalance) if abs(imbalance) > 1e-12 else None
                    pressure.append(PressureObservation(bookmaker=bookmaker, ticket_pct=ticket_value, handle_pct=handle_value, imbalance=imbalance, probability_move=delta, elasticity=elasticity, resistance_observed=abs(imbalance) >= thresholds.minimum_pressure_imbalance and abs(delta) <= thresholds.maximum_resistant_move))
    qualifying.sort()
    events: list[LeadLagEvent] = []
    # Assign at most one leader to each follower move. The nearest preceding
    # same-direction move avoids triangular over-counting of one information chain.
    for index, (follower_time, follower, follower_direction) in enumerate(qualifying):
        for leader_time, leader, direction in reversed(qualifying[:index]):
            lag = (follower_time - leader_time).total_seconds()
            if lag > thresholds.follow_window_seconds:
                break
            if follower != leader and follower_direction == direction:
                events.append(LeadLagEvent(leader_book=leader, follower_book=follower, leader_time=leader_time, follower_time=follower_time, lag_seconds=lag, direction=direction))
                break
    leader_counts: dict[str, int] = {}
    follow_counts: dict[str, int] = {}
    for event in events:
        leader_counts[event.leader_book] = leader_counts.get(event.leader_book, 0) + 1
        follow_counts[event.follower_book] = follow_counts.get(event.follower_book, 0) + 1
    market_types = {
        quote.market_type
        for snapshot in scoped
        for quote in snapshot.quotes
        if quote.market_id == market_id and quote.event_id == selected_event
    }
    movement_computable = len(scoped) >= 2 and bool(moves)
    lead_lag_computable = len(events) >= thresholds.minimum_lead_events
    pressure_computable = bool(pressure)
    metric_reasons: dict[str, str] = {}
    if not movement_computable:
        metric_reasons["movement"] = "at least two temporally distinct price observations are required"
    if not lead_lag_computable:
        metric_reasons["lead_lag"] = f"at least {thresholds.minimum_lead_events} observed follower events are required"
    if not pressure_computable:
        metric_reasons["pressure"] = "ticket and handle observations are required"
    reasons = () if movement_computable else (metric_reasons["movement"],)
    return LongitudinalAnalysis(
        status="COMPUTED" if movement_computable else "NOT_COMPUTABLE",
        event_id=selected_event,
        market_id=market_id,
        market_type=next(iter(market_types)) if len(market_types) == 1 else "MIXED",
        selection=selection,
        as_of=cutoff,
        snapshot_fingerprints=fingerprints,
        moves=tuple(moves),
        lead_lag_events=tuple(events),
        leader_counts=leader_counts,
        follow_counts=follow_counts,
        pressure=tuple(pressure),
        movement_status="COMPUTED" if movement_computable else "NOT_COMPUTABLE",
        lead_lag_status="COMPUTED" if lead_lag_computable else "NOT_COMPUTABLE",
        pressure_status="COMPUTED" if pressure_computable else "NOT_COMPUTABLE",
        metric_reasons=metric_reasons,
        reasons=reasons,
    )


class LongitudinalStore:
    def __init__(self, data_root: str | Path):
        self.path = Path(data_root) / "bookmaker" / "longitudinal" / "analyses.jsonl"
        self.lock_path = self.path.parent / ".longitudinal.lock"

    def append(self, analysis_id: str, analyzed_at: datetime, analysis: LongitudinalAnalysis) -> LongitudinalRecord:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if any(item.analysis_id == analysis_id for item in self.records()):
                raise ValueError(f"duplicate analysis_id: {analysis_id}")
            fingerprint = stable_fingerprint(analysis.model_dump(mode="json"))
            record = LongitudinalRecord(analysis_id=analysis_id, analyzed_at=analyzed_at, analysis=analysis, analysis_fingerprint=fingerprint)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json() + "\n")
            return record

    def records(self) -> list[LongitudinalRecord]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return [LongitudinalRecord.model_validate(json.loads(line)) for line in handle if line.strip()]

    def integrity_issues(self) -> list[str]:
        records = self.records()
        issues = ["duplicate analysis_id"] if len({item.analysis_id for item in records}) != len(records) else []
        for record in records:
            if stable_fingerprint(record.analysis.model_dump(mode="json")) != record.analysis_fingerprint:
                issues.append(f"analysis fingerprint mismatch: {record.analysis_id}")
        return issues
