from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .models import GovernanceMode, PropLadder
from .surface import SurvivalSurface


class PropStorageError(ValueError):
    """Base error for prop persistence failures."""


class DuplicateObservationError(PropStorageError):
    """Raised when an append would reuse an existing observation_id."""


class DuplicateSurfaceError(PropStorageError):
    """Raised when an append would reuse an existing surface_id."""


def _canonical_payload(value: BaseModel | dict[str, Any]) -> str:
    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json")
    else:
        data = value
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_fingerprint(value: BaseModel | dict[str, Any]) -> str:
    """Return a stable sha256 fingerprint for a Pydantic model or JSON payload."""

    return hashlib.sha256(_canonical_payload(value).encode("utf-8")).hexdigest()


class PropLadderObservation(BaseModel):
    """Provenance-complete immutable ladder observation for V0.6 SHADOW_ONLY persistence."""

    model_config = ConfigDict(frozen=True)

    observation_id: str
    market_id: str
    book_id: str
    event_id: str
    player_id: str | None = None
    player_name: str | None = None
    stat_type: str
    observed_at: datetime
    source: str
    source_hash: str
    ladder: PropLadder
    governance: GovernanceMode = GovernanceMode.SHADOW_ONLY
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("observation_id", "market_id", "book_id", "event_id", "stat_type", "source", "source_hash")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("observed_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _advisory_only(self) -> "PropLadderObservation":
        if self.governance != GovernanceMode.SHADOW_ONLY:
            raise ValueError("props persistence is SHADOW_ONLY")
        if self.capital_authority or self.execution_authority:
            raise ValueError("capital_authority and execution_authority must be false")
        if self.event_id != self.ladder.event_id:
            raise ValueError("event_id must match ladder.event_id")
        if self.stat_type.casefold() not in self.ladder.market.casefold():
            raise ValueError("stat_type must identify the ladder market")
        return self

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self)


class DerivedPropSurfaceObservation(BaseModel):
    """Persisted derived surface that references, but never mutates, its source ladder."""

    model_config = ConfigDict(frozen=True)

    surface_id: str
    observation_id: str
    ladder_fingerprint: str
    market_id: str
    book_id: str
    event_id: str
    player_id: str | None = None
    player_name: str | None = None
    stat_type: str
    observed_at: datetime
    derived_at: datetime
    derivation: Literal["survival_surface"] = "survival_surface"
    surface: SurvivalSurface
    governance: GovernanceMode = GovernanceMode.SHADOW_ONLY
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("surface_id", "observation_id", "ladder_fingerprint", "market_id", "book_id", "event_id", "stat_type")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("observed_at", "derived_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _closed_and_not_future(self) -> "DerivedPropSurfaceObservation":
        if self.governance != GovernanceMode.SHADOW_ONLY:
            raise ValueError("props persistence is SHADOW_ONLY")
        if self.capital_authority or self.execution_authority:
            raise ValueError("capital_authority and execution_authority must be false")
        if self.derived_at < self.observed_at:
            raise ValueError("derived_at cannot precede observed_at")
        return self

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self)


class PropPersistenceStore:
    """Append-only JSONL persistence for prop ladders and derived surfaces."""

    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root)
        self.props_root = self.data_root / "props"
        self.ladders_dir = self.props_root / "ladders"
        self.surfaces_dir = self.props_root / "surfaces"
        self.ladders_path = self.ladders_dir / "observations.jsonl"
        self.surfaces_path = self.surfaces_dir / "surfaces.jsonl"

    def append_ladder_observation(self, observation: PropLadderObservation) -> str:
        existing_ids = {item.observation_id for item in self.iter_ladder_observations()}
        if observation.observation_id in existing_ids:
            raise DuplicateObservationError(f"duplicate observation_id: {observation.observation_id}")
        self._append_jsonl(self.ladders_path, observation)
        return observation.fingerprint

    def append_surface_observation(self, surface: DerivedPropSurfaceObservation) -> str:
        ladder = self.get_ladder_observation(surface.observation_id)
        if ladder is None:
            raise PropStorageError(f"missing ladder observation: {surface.observation_id}")
        if ladder.fingerprint != surface.ladder_fingerprint:
            raise PropStorageError("surface ladder_fingerprint does not match stored ladder observation")
        if surface.observed_at != ladder.observed_at:
            raise PropStorageError("surface observed_at must match ladder observed_at to avoid future derivation")
        for field in ("market_id", "book_id", "event_id", "player_id", "player_name", "stat_type"):
            if getattr(surface, field) != getattr(ladder, field):
                raise PropStorageError(f"surface {field} must match stored ladder observation")
        existing_ids = {item.surface_id for item in self.iter_surface_observations()}
        if surface.surface_id in existing_ids:
            raise DuplicateSurfaceError(f"duplicate surface_id: {surface.surface_id}")
        self._append_jsonl(self.surfaces_path, surface)
        return surface.fingerprint

    def iter_ladder_observations(self) -> list[PropLadderObservation]:
        return [PropLadderObservation.model_validate(row) for row in self._read_jsonl(self.ladders_path)]

    def iter_surface_observations(self) -> list[DerivedPropSurfaceObservation]:
        return [DerivedPropSurfaceObservation.model_validate(row) for row in self._read_jsonl(self.surfaces_path)]

    def get_ladder_observation(self, observation_id: str) -> PropLadderObservation | None:
        for observation in self.iter_ladder_observations():
            if observation.observation_id == observation_id:
                return observation
        return None

    def latest_surface_at_or_before(self, observation_id: str, as_of: datetime) -> DerivedPropSurfaceObservation | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(timezone.utc)
        candidates = [
            item for item in self.iter_surface_observations()
            if item.observation_id == observation_id
            and item.observed_at <= cutoff
            and item.derived_at <= cutoff
        ]
        return max(candidates, key=lambda item: item.derived_at, default=None)

    def latest_ladder_at_or_before(
        self,
        *,
        market_id: str,
        book_id: str,
        event_id: str,
        stat_type: str,
        as_of: datetime,
        player_id: str | None = None,
    ) -> PropLadderObservation | None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(timezone.utc)
        candidates = [
            item
            for item in self.iter_ladder_observations()
            if item.market_id == market_id
            and item.book_id == book_id
            and item.event_id == event_id
            and item.stat_type == stat_type
            and item.player_id == player_id
            and item.observed_at <= cutoff
        ]
        return max(candidates, key=lambda item: item.observed_at, default=None)

    @staticmethod
    def _append_jsonl(path: Path, value: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(value.model_dump_json())
            fh.write("\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    rows.append(json.loads(stripped))
        return rows
