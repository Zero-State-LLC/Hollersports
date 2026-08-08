from __future__ import annotations

import fcntl
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import StructuralEvidenceObservation


def stable_fingerprint(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class SynthesisStorageError(ValueError):
    pass


class StructuralAnalysisRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    observation_fingerprint: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    subject_type: Literal["SINGLE", "PARLAY"]
    observed_at: datetime
    recorded_at: datetime
    analyzed_at: datetime
    verdict_packet: dict[str, Any]
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("observed_at", "recorded_at", "analyzed_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent(self) -> "StructuralAnalysisRecord":
        if self.recorded_at < self.observed_at or self.analyzed_at < self.recorded_at:
            raise ValueError("analysis timestamps are not temporally ordered")
        if self.capital_authority or self.execution_authority:
            raise ValueError("structural analysis cannot authorize capital or execution")
        return self


class SynthesisStore:
    def __init__(self, data_root: str | Path):
        root = Path(data_root) / "analyses" / "structural"
        self.observations_path = root / "observations.jsonl"
        self.analyses_path = root / "analyses.jsonl"
        self.lock_path = root / ".structural.lock"

    def observations(self) -> list[StructuralEvidenceObservation]:
        return [StructuralEvidenceObservation.model_validate(row) for row in self._read(self.observations_path)]

    def analyses(self) -> list[StructuralAnalysisRecord]:
        return [StructuralAnalysisRecord.model_validate(row) for row in self._read(self.analyses_path)]

    @staticmethod
    def derive(observation: StructuralEvidenceObservation, analysis_id: str, analyzed_at: datetime) -> StructuralAnalysisRecord:
        return StructuralAnalysisRecord(
            analysis_id=analysis_id, observation_id=observation.observation_id,
            observation_fingerprint=stable_fingerprint(observation), subject_id=observation.subject_id,
            subject_type=observation.subject_type, observed_at=observation.observed_at,
            recorded_at=observation.recorded_at, analyzed_at=analyzed_at,
            verdict_packet=observation.derive(),
        )

    @staticmethod
    def _validate(observation: StructuralEvidenceObservation, analysis: StructuralAnalysisRecord) -> None:
        if analysis.observation_id != observation.observation_id or analysis.observation_fingerprint != stable_fingerprint(observation):
            raise SynthesisStorageError("analysis source observation link is invalid")
        for field in ("subject_id", "subject_type", "observed_at", "recorded_at"):
            if getattr(analysis, field) != getattr(observation, field):
                raise SynthesisStorageError(f"analysis {field} must match observation")
        if analysis.verdict_packet != observation.derive():
            raise SynthesisStorageError("persisted verdict does not match deterministic synthesis")

    def append_bundle(self, observation: StructuralEvidenceObservation, analysis: StructuralAnalysisRecord) -> tuple[str, str]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if any(item.observation_id == observation.observation_id for item in self.observations()):
                raise SynthesisStorageError(f"duplicate observation_id: {observation.observation_id}")
            if any(item.analysis_id == analysis.analysis_id for item in self.analyses()):
                raise SynthesisStorageError(f"duplicate analysis_id: {analysis.analysis_id}")
            self._validate(observation, analysis)
            old_o = self.observations_path.stat().st_size if self.observations_path.exists() else 0
            old_a = self.analyses_path.stat().st_size if self.analyses_path.exists() else 0
            try:
                self._append(self.observations_path, observation)
                self._append(self.analyses_path, analysis)
            except Exception:
                self._truncate(self.observations_path, old_o)
                self._truncate(self.analyses_path, old_a)
                raise
            return stable_fingerprint(observation), stable_fingerprint(analysis)

    def latest_at_or_before(self, subject_id: str, as_of: datetime) -> tuple[StructuralEvidenceObservation, StructuralAnalysisRecord | None] | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(timezone.utc)
        candidates = [item for item in self.observations() if item.subject_id == subject_id and item.observed_at <= cutoff and item.recorded_at <= cutoff]
        if not candidates:
            return None
        observation = max(candidates, key=lambda item: (item.observed_at, item.recorded_at))
        analyses = [item for item in self.analyses() if item.observation_id == observation.observation_id and item.analyzed_at <= cutoff]
        return observation, max(analyses, key=lambda item: item.analyzed_at, default=None)

    def integrity_issues(self) -> list[str]:
        observations, analyses = self.observations(), self.analyses()
        issues: list[str] = []
        by_id = {item.observation_id: item for item in observations}
        if len(by_id) != len(observations): issues.append("duplicate observation_id")
        if len({item.analysis_id for item in analyses}) != len(analyses): issues.append("duplicate analysis_id")
        for analysis in analyses:
            source = by_id.get(analysis.observation_id)
            if source is None:
                issues.append(f"orphan analysis: {analysis.analysis_id}")
                continue
            try: self._validate(source, analysis)
            except SynthesisStorageError as exc: issues.append(f"invalid analysis {analysis.analysis_id}: {exc}")
        return issues

    @staticmethod
    def _append(path: Path, value: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle: handle.write(value.model_dump_json() + "\n")

    @staticmethod
    def _truncate(path: Path, size: int) -> None:
        if path.exists():
            with path.open("r+b") as handle: handle.truncate(size)

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists(): return []
        with path.open("r", encoding="utf-8") as handle: return [json.loads(line) for line in handle if line.strip()]
