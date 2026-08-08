from __future__ import annotations

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .fingerprint import stable_fingerprint
from .models import BookmakerFingerprint


class FingerprintPromotionRecord(BaseModel):
    """Immutable promotion of one evidence-bound bookmaker fingerprint."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["BookmakerFingerprintPromotion.v1"] = "BookmakerFingerprintPromotion.v1"
    fingerprint_id: str = Field(min_length=1)
    bookmaker: str = Field(min_length=1)
    market_class: str = Field(min_length=1)
    as_of: datetime
    computed_at: datetime
    fingerprint: BookmakerFingerprint
    evidence_fingerprints: tuple[str, ...] = Field(min_length=1)
    packet_fingerprint: str = Field(min_length=1)
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("as_of", "computed_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent(self) -> "FingerprintPromotionRecord":
        if self.computed_at < self.as_of:
            raise ValueError("computed_at cannot precede as_of")
        if self.fingerprint.bookmaker != self.bookmaker:
            raise ValueError("fingerprint bookmaker must match promotion bookmaker")
        if self.fingerprint.status != "COMPUTED":
            raise ValueError("only COMPUTED fingerprints can be promoted")
        if self.capital_authority or self.execution_authority:
            raise ValueError("fingerprint promotion cannot authorize capital or execution")
        return self

    def fingerprint_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"packet_fingerprint"})


class FingerprintStore:
    def __init__(self, data_root: str | Path):
        self.path = Path(data_root) / "bookmaker" / "fingerprints" / "promotions.jsonl"
        self.lock_path = self.path.parent / ".fingerprints.lock"

    def records(self) -> list[FingerprintPromotionRecord]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return [FingerprintPromotionRecord.model_validate(json.loads(line)) for line in handle if line.strip()]

    def append(
        self,
        *,
        fingerprint_id: str,
        bookmaker: str,
        market_class: str,
        as_of: datetime,
        computed_at: datetime,
        fingerprint: BookmakerFingerprint,
        evidence_rows: list[dict[str, Any]],
    ) -> FingerprintPromotionRecord:
        cutoff = as_of.astimezone(timezone.utc) if as_of.tzinfo is not None and as_of.utcoffset() is not None else None
        if cutoff is None:
            raise ValueError("as_of must be timezone-aware")
        for row in evidence_rows:
            raw_available_at = row.get("available_at")
            if not isinstance(raw_available_at, str):
                raise ValueError("each promotion evidence row requires available_at")
            try:
                available_at = datetime.fromisoformat(raw_available_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("evidence available_at must be ISO-8601") from exc
            if available_at.tzinfo is None or available_at.utcoffset() is None:
                raise ValueError("evidence available_at must be timezone-aware")
            if available_at.astimezone(timezone.utc) > cutoff:
                raise ValueError("fingerprint evidence cannot postdate as_of")
        evidence_fingerprints = tuple(stable_fingerprint(row) for row in evidence_rows)
        if not evidence_fingerprints:
            raise ValueError("fingerprint promotion requires immutable evidence rows")
        if len(set(evidence_fingerprints)) != len(evidence_fingerprints):
            raise ValueError("duplicate fingerprint evidence row")
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if any(item.fingerprint_id == fingerprint_id for item in self.records()):
                raise ValueError(f"duplicate fingerprint_id: {fingerprint_id}")
            seed = FingerprintPromotionRecord(
                fingerprint_id=fingerprint_id,
                bookmaker=bookmaker,
                market_class=market_class,
                as_of=as_of,
                computed_at=computed_at,
                fingerprint=fingerprint,
                evidence_fingerprints=evidence_fingerprints,
                packet_fingerprint="pending",
            )
            record = seed.model_copy(update={"packet_fingerprint": stable_fingerprint(seed.fingerprint_payload())})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json() + "\n")
                handle.flush()
            return record

    def query(
        self,
        *,
        bookmaker: str | None = None,
        market_class: str | None = None,
        at_or_before: datetime | None = None,
    ) -> list[FingerprintPromotionRecord]:
        if at_or_before is not None:
            if at_or_before.tzinfo is None or at_or_before.utcoffset() is None:
                raise ValueError("at_or_before must be timezone-aware")
            at_or_before = at_or_before.astimezone(timezone.utc)
        rows = [
            item for item in self.records()
            if (bookmaker is None or item.bookmaker == bookmaker)
            and (market_class is None or item.market_class == market_class)
            and (at_or_before is None or (item.as_of <= at_or_before and item.computed_at <= at_or_before))
        ]
        return sorted(rows, key=lambda item: (item.as_of, item.computed_at, item.fingerprint_id))

    def integrity_issues(self) -> list[str]:
        try:
            rows = self.records()
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            return [str(exc)]
        issues = ["duplicate fingerprint_id"] if len({row.fingerprint_id for row in rows}) != len(rows) else []
        for row in rows:
            if stable_fingerprint(row.fingerprint_payload()) != row.packet_fingerprint:
                issues.append(f"packet fingerprint mismatch: {row.fingerprint_id}")
            if len(set(row.evidence_fingerprints)) != len(row.evidence_fingerprints):
                issues.append(f"duplicate evidence fingerprint: {row.fingerprint_id}")
        return issues
