from __future__ import annotations

import hashlib
import json
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
    model_config = ConfigDict(frozen=True)

    observation_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    context_type: ContextType
    observed_at: datetime
    source: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    payload: ContextPayload
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("observed_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def closed_and_coherent(self) -> "ContextObservation":
        if self.capital_authority or self.execution_authority:
            raise ValueError("context observations cannot authorize capital or execution")
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
    model_config = ConfigDict(frozen=True)

    derivation_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    observation_fingerprint: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    context_type: ContextType
    observed_at: datetime
    derived_at: datetime
    result: ContextResult
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("observed_at", "derived_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def closed_and_temporal(self) -> "ContextDerivation":
        if self.capital_authority or self.execution_authority:
            raise ValueError("context derivations cannot authorize capital or execution")
        if self.derived_at < self.observed_at:
            raise ValueError("derived_at cannot precede observed_at")
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
        if observation.fingerprint != derivation.observation_fingerprint:
            raise ContextStorageError("observation fingerprint mismatch")
        for field in ("event_id", "entity_id", "context_type", "observed_at"):
            if getattr(observation, field) != getattr(derivation, field):
                raise ContextStorageError(f"derivation {field} must match observation")
        if any(item.derivation_id == derivation.derivation_id for item in self.derivations()):
            raise ContextStorageError(f"duplicate derivation_id: {derivation.derivation_id}")
        self._append(self.derivations_path, derivation)

    def latest_at_or_before(self, *, event_id: str, entity_id: str, context_type: ContextType, as_of: datetime) -> tuple[ContextObservation, ContextDerivation | None] | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(timezone.utc)
        candidates = [item for item in self.observations() if item.event_id == event_id and item.entity_id == entity_id and item.context_type == context_type and item.observed_at <= cutoff]
        if not candidates:
            return None
        observation = max(candidates, key=lambda item: item.observed_at)
        derived = [item for item in self.derivations() if item.observation_id == observation.observation_id and item.derived_at <= cutoff]
        return observation, max(derived, key=lambda item: item.derived_at, default=None)

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
