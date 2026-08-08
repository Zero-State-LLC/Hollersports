from __future__ import annotations

import hashlib
import json
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .coaching import CoachHistory
from .models import ContextResult, PlayerState, TravelState
from .opportunity import OpportunityState
from .venue import VenueState

ContextType = Literal["PLAYER", "TRAVEL", "OPPORTUNITY", "COACHING", "VENUE"]
ContextPayload = PlayerState | TravelState | OpportunityState | CoachHistory | VenueState


class ContextStorageError(ValueError):
    pass


class DuplicateContextObservationError(ContextStorageError):
    pass


def stable_fingerprint(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_EXPECTED_TYPES: dict[str, type[BaseModel]] = {
    "PLAYER": PlayerState,
    "TRAVEL": TravelState,
    "OPPORTUNITY": OpportunityState,
    "COACHING": CoachHistory,
    "VENUE": VenueState,
}


class ContextObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    context_type: ContextType
    observed_at: datetime
    recorded_at: datetime
    source: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    payload: ContextPayload
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_payload_fields(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("payload"), dict):
            context_type = data.get("context_type")
            expected = _EXPECTED_TYPES.get(context_type)
            if expected is not None:
                unknown = set(data["payload"]) - set(expected.model_fields)
                if unknown:
                    raise ValueError(f"unknown {context_type} payload fields: {sorted(unknown)}")
        return data

    @field_validator("observed_at", "recorded_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def closed_and_coherent(self) -> "ContextObservation":
        if self.capital_authority or self.execution_authority:
            raise ValueError("context observations cannot authorize capital or execution")
        if self.recorded_at < self.observed_at:
            raise ValueError("recorded_at cannot precede observed_at")
        expected = _EXPECTED_TYPES[self.context_type]
        if not isinstance(self.payload, expected):
            raise ValueError(f"payload must be {expected.__name__} for {self.context_type}")
        payload_entity = (
            getattr(self.payload, "player_id", None)
            or getattr(self.payload, "team_id", None)
            or getattr(self.payload, "entity_id", None)
            or getattr(self.payload, "coach_id", None)
            or getattr(self.payload, "venue_id", None)
        )
        if payload_entity != self.entity_id:
            raise ValueError("entity_id must match payload identity")
        for provenance in getattr(self.payload, "provenance", []):
            if provenance.observed_at is not None and provenance.observed_at > self.observed_at:
                raise ValueError("payload provenance cannot postdate observation")
        return self

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self)


class ContextDerivation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    derivation_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    observation_fingerprint: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    context_type: ContextType
    observed_at: datetime
    recorded_at: datetime
    derived_at: datetime
    result: ContextResult
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("observed_at", "recorded_at", "derived_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def closed_and_temporal(self) -> "ContextDerivation":
        if self.capital_authority or self.execution_authority:
            raise ValueError("context derivations cannot authorize capital or execution")
        if self.recorded_at < self.observed_at:
            raise ValueError("recorded_at cannot precede observed_at")
        if self.derived_at < self.recorded_at:
            raise ValueError("derived_at cannot precede recorded_at")
        return self


class ContextStore:
    def __init__(self, data_root: str | Path):
        root = Path(data_root) / "context"
        self.observations_path = root / "observations" / "observations.jsonl"
        self.derivations_path = root / "derivations" / "derivations.jsonl"

    def observations(self) -> list[ContextObservation]:
        return [ContextObservation.model_validate(row) for row in self._read(self.observations_path)]

    def derivations(self) -> list[ContextDerivation]:
        return [ContextDerivation.model_validate(row) for row in self._read(self.derivations_path)]

    def append_observation(self, observation: ContextObservation) -> str:
        if any(item.observation_id == observation.observation_id for item in self.observations()):
            raise DuplicateContextObservationError(f"duplicate observation_id: {observation.observation_id}")
        self._append(self.observations_path, observation)
        return observation.fingerprint

    def append_derivation(self, derivation: ContextDerivation) -> None:
        observation = next((item for item in self.observations() if item.observation_id == derivation.observation_id), None)
        if observation is None:
            raise ContextStorageError("missing source context observation")
        self._validate_derivation(observation, derivation)
        if any(item.derivation_id == derivation.derivation_id for item in self.derivations()):
            raise ContextStorageError(f"duplicate derivation_id: {derivation.derivation_id}")
        self._append(self.derivations_path, derivation)

    @staticmethod
    def _validate_derivation(observation: ContextObservation, derivation: ContextDerivation) -> None:
        if observation.fingerprint != derivation.observation_fingerprint:
            raise ContextStorageError("observation fingerprint mismatch")
        for field in ("event_id", "entity_id", "context_type", "observed_at", "recorded_at"):
            if getattr(observation, field) != getattr(derivation, field):
                raise ContextStorageError(f"derivation {field} must match observation")
        if derivation.result.provenance != getattr(observation.payload, "provenance", []):
            raise ContextStorageError("derivation provenance must exactly match source observation evidence")
        expected_signal = {
            "PLAYER": "player_state_transform",
            "TRAVEL": "travel_load",
            "OPPORTUNITY": "opportunity_shift",
            "COACHING": "coach_response",
            "VENUE": "venue_residual",
        }[observation.context_type]
        if derivation.result.signal != expected_signal:
            raise ContextStorageError("derivation signal does not match context_type")

    def append_bundle(self, observation: ContextObservation, derivation: ContextDerivation) -> tuple[str, str]:
        """Append an observation and derivation under one process lock with rollback on failure."""
        lock_path = self.observations_path.parent.parent / ".context.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if any(item.observation_id == observation.observation_id for item in self.observations()):
                raise DuplicateContextObservationError(f"duplicate observation_id: {observation.observation_id}")
            if any(item.derivation_id == derivation.derivation_id for item in self.derivations()):
                raise ContextStorageError(f"duplicate derivation_id: {derivation.derivation_id}")
            if derivation.observation_id != observation.observation_id:
                raise ContextStorageError("derivation observation_id must match observation")
            self._validate_derivation(observation, derivation)
            observation_size = self.observations_path.stat().st_size if self.observations_path.exists() else 0
            derivation_size = self.derivations_path.stat().st_size if self.derivations_path.exists() else 0
            try:
                self._append(self.observations_path, observation)
                self._append(self.derivations_path, derivation)
            except Exception:
                self._truncate(self.observations_path, observation_size)
                self._truncate(self.derivations_path, derivation_size)
                raise
            return observation.fingerprint, stable_fingerprint(derivation)

    def latest_at_or_before(self, *, event_id: str, entity_id: str, context_type: ContextType, as_of: datetime) -> tuple[ContextObservation, ContextDerivation | None] | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(timezone.utc)
        candidates = [item for item in self.observations() if item.event_id == event_id and item.entity_id == entity_id and item.context_type == context_type and item.observed_at <= cutoff and item.recorded_at <= cutoff]
        if not candidates:
            return None
        observation = max(candidates, key=lambda item: item.observed_at)
        derived = [item for item in self.derivations() if item.observation_id == observation.observation_id and item.derived_at <= cutoff]
        return observation, max(derived, key=lambda item: item.derived_at, default=None)

    @staticmethod
    def _truncate(path: Path, size: int) -> None:
        if not path.exists():
            return
        with path.open("r+b") as handle:
            handle.truncate(size)

    @staticmethod
    def _append(path: Path, value: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(value.model_dump_json() + "\n")

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
