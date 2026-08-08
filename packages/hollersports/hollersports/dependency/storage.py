from __future__ import annotations

import fcntl
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .graph import DependencyGraphSnapshot, inspect_dependency_graph
from .models import DependencyEdge, DependencyMethod, DriverScenario, EmpiricalConditionalEvidence, LegProbability
from .parlay import ParlayAnalysis, analyze_parlay


def stable_fingerprint(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DependencyStorageError(ValueError):
    pass


class DuplicateDependencyObservationError(DependencyStorageError):
    pass


class DependencyObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    parlay_id: str = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    source: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    legs: tuple[LegProbability, ...] = Field(min_length=2)
    edges: tuple[DependencyEdge, ...] = ()
    method: DependencyMethod | None = None
    explicitly_allow_independence: bool = False
    empirical_evidence: EmpiricalConditionalEvidence | None = None
    driver_scenarios: tuple[DriverScenario, ...] | None = None
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("observed_at", "recorded_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent(self) -> "DependencyObservation":
        if self.recorded_at < self.observed_at:
            raise ValueError("recorded_at cannot precede observed_at")
        if self.capital_authority or self.execution_authority:
            raise ValueError("dependency observations cannot authorize capital or execution")
        leg_ids = [leg.leg_id for leg in self.legs]
        if len(leg_ids) != len(set(leg_ids)):
            raise ValueError("leg_id values must be unique")
        known = set(leg_ids)
        if any(edge.source_leg_id not in known or edge.target_leg_id not in known for edge in self.edges):
            raise ValueError("every dependency edge endpoint must identify an observed leg")
        if self.method == DependencyMethod.INDEPENDENT and not self.explicitly_allow_independence:
            raise ValueError("independence requires explicit allow flag")
        return self

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self)


class DependencyAnalysisRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    observation_fingerprint: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    parlay_id: str = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    analyzed_at: datetime
    graph: DependencyGraphSnapshot
    analysis: ParlayAnalysis
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("observed_at", "recorded_at", "analyzed_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent(self) -> "DependencyAnalysisRecord":
        if self.recorded_at < self.observed_at or self.analyzed_at < self.recorded_at:
            raise ValueError("analysis timestamps are not temporally ordered")
        if self.capital_authority or self.execution_authority:
            raise ValueError("dependency analyses cannot authorize capital or execution")
        return self


class DependencyStore:
    def __init__(self, data_root: str | Path):
        root = Path(data_root) / "dependency"
        self.observations_path = root / "graphs" / "observations.jsonl"
        self.analyses_path = root / "analyses" / "parlays.jsonl"
        self.lock_path = root / ".dependency.lock"

    def observations(self) -> list[DependencyObservation]:
        return [DependencyObservation.model_validate(row) for row in self._read(self.observations_path)]

    def analyses(self) -> list[DependencyAnalysisRecord]:
        return [DependencyAnalysisRecord.model_validate(row) for row in self._read(self.analyses_path)]

    @staticmethod
    def derive(observation: DependencyObservation, analysis_id: str, analyzed_at: datetime) -> DependencyAnalysisRecord:
        graph = inspect_dependency_graph(list(observation.legs), list(observation.edges))
        result = analyze_parlay(
            list(observation.legs), list(observation.edges), method=observation.method,
            explicitly_allow_independence=observation.explicitly_allow_independence,
            empirical_evidence=observation.empirical_evidence,
            driver_scenarios=list(observation.driver_scenarios) if observation.driver_scenarios is not None else None,
        )
        return DependencyAnalysisRecord(
            analysis_id=analysis_id, observation_id=observation.observation_id,
            observation_fingerprint=observation.fingerprint, event_id=observation.event_id,
            parlay_id=observation.parlay_id, observed_at=observation.observed_at,
            recorded_at=observation.recorded_at, analyzed_at=analyzed_at, graph=graph, analysis=result,
        )

    def append_bundle(self, observation: DependencyObservation, analysis: DependencyAnalysisRecord) -> tuple[str, str]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if any(item.observation_id == observation.observation_id for item in self.observations()):
                raise DuplicateDependencyObservationError(f"duplicate observation_id: {observation.observation_id}")
            if any(item.analysis_id == analysis.analysis_id for item in self.analyses()):
                raise DependencyStorageError(f"duplicate analysis_id: {analysis.analysis_id}")
            self._validate_link(observation, analysis)
            old_observation_size = self.observations_path.stat().st_size if self.observations_path.exists() else 0
            old_analysis_size = self.analyses_path.stat().st_size if self.analyses_path.exists() else 0
            try:
                self._append(self.observations_path, observation)
                self._append(self.analyses_path, analysis)
            except Exception:
                self._truncate(self.observations_path, old_observation_size)
                self._truncate(self.analyses_path, old_analysis_size)
                raise
            return observation.fingerprint, stable_fingerprint(analysis)

    @staticmethod
    def _validate_link(observation: DependencyObservation, analysis: DependencyAnalysisRecord) -> None:
        if analysis.observation_id != observation.observation_id or analysis.observation_fingerprint != observation.fingerprint:
            raise DependencyStorageError("analysis source observation link is invalid")
        for field in ("event_id", "parlay_id", "observed_at", "recorded_at"):
            if getattr(analysis, field) != getattr(observation, field):
                raise DependencyStorageError(f"analysis {field} must match observation")
        expected = DependencyStore.derive(observation, analysis.analysis_id, analysis.analyzed_at)
        if analysis.graph != expected.graph or analysis.analysis != expected.analysis:
            raise DependencyStorageError("persisted dependency analysis does not match deterministic derivation")

    def latest_at_or_before(self, event_id: str, parlay_id: str, as_of: datetime) -> tuple[DependencyObservation, DependencyAnalysisRecord | None] | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(timezone.utc)
        candidates = [item for item in self.observations() if item.event_id == event_id and item.parlay_id == parlay_id and item.observed_at <= cutoff and item.recorded_at <= cutoff]
        if not candidates:
            return None
        observation = max(candidates, key=lambda item: (item.observed_at, item.recorded_at))
        analyses = [item for item in self.analyses() if item.observation_id == observation.observation_id and item.analyzed_at <= cutoff]
        return observation, max(analyses, key=lambda item: item.analyzed_at, default=None)

    def integrity_issues(self) -> list[str]:
        observations = self.observations()
        analyses = self.analyses()
        issues: list[str] = []
        if len({item.observation_id for item in observations}) != len(observations):
            issues.append("duplicate observation_id")
        if len({item.analysis_id for item in analyses}) != len(analyses):
            issues.append("duplicate analysis_id")
        by_id = {item.observation_id: item for item in observations}
        for analysis in analyses:
            observation = by_id.get(analysis.observation_id)
            if observation is None:
                issues.append(f"orphan analysis: {analysis.analysis_id}")
                continue
            try:
                self._validate_link(observation, analysis)
            except DependencyStorageError as exc:
                issues.append(f"invalid analysis {analysis.analysis_id}: {exc}")
        return issues

    @staticmethod
    def _append(path: Path, value: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(value.model_dump_json() + "\n")

    @staticmethod
    def _truncate(path: Path, size: int) -> None:
        if path.exists():
            with path.open("r+b") as handle:
                handle.truncate(size)

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
