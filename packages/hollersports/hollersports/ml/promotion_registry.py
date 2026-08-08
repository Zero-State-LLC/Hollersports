"""Append-only shadow-only model promotion registry.

Local advisory registry for model promotion evidence. It never grants capital or
execution authority and persists records as JSONL with hash-chain integrity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4


class ModelFamily(str, Enum):
    PLAYER_OUTCOME = "PLAYER_OUTCOME"
    CONTEXT = "CONTEXT"
    DEPENDENCY = "DEPENDENCY"
    JOINT = "JOINT"


class RegistryHealthStatus(str, Enum):
    OK = "OK"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True)
class PromotionRecord:
    """Evidence-bound shadow-only promotion record."""

    model_family: ModelFamily | str
    sport: str
    market_class: str
    trained_at: datetime
    evaluated_at: datetime
    promoted_at: datetime
    artifact_hash: str
    evidence_hash: str
    sample_size: int
    sample_minimum: int
    metrics: Mapping[str, float]
    model_id: str
    record_id: str = field(default_factory=lambda: str(uuid4()))
    market_subclass: str | None = None
    notes: str | None = None
    capital_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        _validate_record(self)

    def key(self) -> tuple[str, str, str, str | None, str, str]:
        return (
            _family_value(self.model_family),
            self.sport,
            self.market_class,
            self.market_subclass,
            self.artifact_hash,
            self.evidence_hash,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "model_id": self.model_id,
            "model_family": _family_value(self.model_family),
            "sport": self.sport,
            "market_class": self.market_class,
            "market_subclass": self.market_subclass,
            "trained_at": self.trained_at.isoformat(),
            "evaluated_at": self.evaluated_at.isoformat(),
            "promoted_at": self.promoted_at.isoformat(),
            "artifact_hash": self.artifact_hash,
            "evidence_hash": self.evidence_hash,
            "sample_size": self.sample_size,
            "sample_minimum": self.sample_minimum,
            "metrics": dict(sorted(self.metrics.items())),
            "notes": self.notes,
            "capital_authority": False,
            "execution_authority": False,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PromotionRecord":
        return cls(
            record_id=str(payload["record_id"]),
            model_id=str(payload["model_id"]),
            model_family=ModelFamily(str(payload["model_family"])),
            sport=str(payload["sport"]),
            market_class=str(payload["market_class"]),
            market_subclass=payload.get("market_subclass"),
            trained_at=_parse_dt(str(payload["trained_at"])),
            evaluated_at=_parse_dt(str(payload["evaluated_at"])),
            promoted_at=_parse_dt(str(payload["promoted_at"])),
            artifact_hash=str(payload["artifact_hash"]),
            evidence_hash=str(payload["evidence_hash"]),
            sample_size=int(payload["sample_size"]),
            sample_minimum=int(payload["sample_minimum"]),
            metrics={str(k): float(v) for k, v in dict(payload["metrics"]).items()},
            notes=payload.get("notes"),
            capital_authority=bool(payload.get("capital_authority", False)),
            execution_authority=bool(payload.get("execution_authority", False)),
        )


@dataclass(frozen=True)
class RegistryHealth:
    status: RegistryHealthStatus
    checked_records: int
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.status is RegistryHealthStatus.OK


def stable_hash(value: Mapping[str, Any] | Iterable[Any]) -> str:
    """Return a stable sha256 hash for JSON-serializable evidence/artifacts."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


class ShadowPromotionRegistry:
    """Append-only JSONL registry with hash-chain integrity checks."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def append(self, record: PromotionRecord) -> PromotionRecord:
        records = self.list_records()
        if any(existing.record_id == record.record_id for existing in records):
            raise ValueError(f"duplicate record_id: {record.record_id}")
        if any(existing.key() == record.key() for existing in records):
            raise ValueError("duplicate artifact/evidence promotion for family/sport/market")
        previous_hash = self._last_entry_hash()
        entry = {"payload": record.payload(), "previous_hash": previous_hash}
        entry["entry_hash"] = stable_hash(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
        return record

    def list_records(self) -> list[PromotionRecord]:
        return [PromotionRecord.from_payload(entry["payload"]) for entry in self._read_entries()]

    def query(
        self,
        *,
        sport: str | None = None,
        model_family: ModelFamily | str | None = None,
        market_class: str | None = None,
        market_subclass: str | None = None,
        promoted_from: datetime | None = None,
        promoted_to: datetime | None = None,
    ) -> list[PromotionRecord]:
        if promoted_from is not None and promoted_from.tzinfo is None:
            raise ValueError("promoted_from must be timezone-aware")
        if promoted_to is not None and promoted_to.tzinfo is None:
            raise ValueError("promoted_to must be timezone-aware")
        family = _family_value(model_family) if model_family is not None else None
        out: list[PromotionRecord] = []
        for record in self.list_records():
            if sport is not None and record.sport != sport:
                continue
            if family is not None and _family_value(record.model_family) != family:
                continue
            if market_class is not None and record.market_class != market_class:
                continue
            if market_subclass is not None and record.market_subclass != market_subclass:
                continue
            if promoted_from is not None and record.promoted_at < promoted_from:
                continue
            if promoted_to is not None and record.promoted_at > promoted_to:
                continue
            out.append(record)
        return sorted(out, key=lambda r: r.promoted_at)

    def health(self) -> RegistryHealth:
        errors: list[str] = []
        seen_ids: set[str] = set()
        seen_keys: set[tuple[str, str, str, str | None, str, str]] = set()
        previous_hash: str | None = None
        entries = self._read_entries(raw=True)
        for idx, entry in enumerate(entries, start=1):
            actual = entry.get("entry_hash")
            unsigned = {"payload": entry.get("payload"), "previous_hash": entry.get("previous_hash")}
            if actual != stable_hash(unsigned):
                errors.append(f"line {idx}: entry_hash mismatch")
            if entry.get("previous_hash") != previous_hash:
                errors.append(f"line {idx}: previous_hash mismatch")
            previous_hash = actual
            try:
                record = PromotionRecord.from_payload(entry["payload"])
            except Exception as exc:  # noqa: BLE001
                errors.append(f"line {idx}: invalid payload: {exc}")
                continue
            if record.record_id in seen_ids:
                errors.append(f"line {idx}: duplicate record_id {record.record_id}")
            if record.key() in seen_keys:
                errors.append(f"line {idx}: duplicate promotion key")
            seen_ids.add(record.record_id)
            seen_keys.add(record.key())
        status = RegistryHealthStatus.OK if not errors else RegistryHealthStatus.CORRUPT
        return RegistryHealth(status=status, checked_records=len(entries), errors=tuple(errors))

    def _last_entry_hash(self) -> str | None:
        entries = self._read_entries(raw=True)
        return None if not entries else str(entries[-1]["entry_hash"])

    def _read_entries(self, raw: bool = False) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    entries.append(json.loads(line))
        return entries


def _validate_record(record: PromotionRecord) -> None:
    if _family_value(record.model_family) not in {item.value for item in ModelFamily}:
        raise ValueError("unsupported model_family")
    for field_name in ("sport", "market_class", "model_id"):
        if not str(getattr(record, field_name)).strip():
            raise ValueError(f"{field_name} is required")
    if record.capital_authority or record.execution_authority:
        raise ValueError("capital_authority and execution_authority must be false")
    if not _is_sha256(record.artifact_hash):
        raise ValueError("artifact_hash must be a stable sha256 hex digest")
    if not _is_sha256(record.evidence_hash):
        raise ValueError("evidence_hash must be a stable sha256 hex digest")
    for name in ("trained_at", "evaluated_at", "promoted_at"):
        if getattr(record, name).tzinfo is None:
            raise ValueError(f"{name} must be timezone-aware")
    if not record.trained_at <= record.evaluated_at <= record.promoted_at:
        raise ValueError("trained_at <= evaluated_at <= promoted_at is required")
    if record.sample_minimum < 1:
        raise ValueError("sample_minimum must be positive")
    if record.sample_size < record.sample_minimum:
        raise ValueError("sample_size must meet sample_minimum")
    if not record.metrics:
        raise ValueError("metrics are required")
    for key, value in record.metrics.items():
        if not str(key).strip():
            raise ValueError("metric names are required")
        if not isinstance(value, int | float):
            raise ValueError("metric values must be numeric")


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return parsed


def _family_value(model_family: ModelFamily | str) -> str:
    return model_family.value if isinstance(model_family, ModelFamily) else str(model_family)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)
