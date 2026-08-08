from __future__ import annotations

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .devig_calibration import DevigCalibrationResult
from .fingerprint import stable_fingerprint


class DevigCalibrationPromotionRecord(BaseModel):
    """Immutable append-only promotion of an evidence-bound de-vig calibration result."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["DevigCalibrationPromotion.v1"] = "DevigCalibrationPromotion.v1"
    promotion_id: str = Field(min_length=1)
    bookmaker: str = Field(min_length=1)
    sport: str = Field(min_length=1)
    market_class: str = Field(min_length=1)
    odds_bucket: str = Field(min_length=1)
    preferred_method: str = Field(min_length=1)
    as_of: datetime
    promoted_at: datetime
    minimum_sample: int = Field(ge=1)
    improvement_over_raw_brier: float = Field(gt=0)
    source_result_fingerprint: str = Field(min_length=1)
    result: DevigCalibrationResult
    packet_fingerprint: str = Field(min_length=1)
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    advisory_mode: Literal["ADVISORY_ONLY"] = "ADVISORY_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False

    @field_validator("as_of", "promoted_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def coherent(self) -> "DevigCalibrationPromotionRecord":
        if self.promoted_at < self.as_of:
            raise ValueError("promoted_at cannot precede as_of")
        if self.capital_authority or self.execution_authority:
            raise ValueError("de-vig calibration promotion cannot authorize capital or execution")
        if self.result.capital_authority or self.result.execution_authority:
            raise ValueError("source de-vig calibration cannot authorize capital or execution")
        if self.result.authority != "SHADOW_ONLY" or self.authority != "SHADOW_ONLY":
            raise ValueError("de-vig calibration promotion must remain SHADOW_ONLY")
        if self.result.status != "COMPUTED":
            raise ValueError("only COMPUTED de-vig calibration results can be promoted")
        if self.result.bookmaker != self.bookmaker or self.result.sport != self.sport or self.result.market_class != self.market_class or self.result.odds_bucket != self.odds_bucket:
            raise ValueError("source result scope must match promotion scope")
        if self.result.as_of != self.as_of:
            raise ValueError("source result as_of must match promotion as_of")
        if self.result.minimum_sample != self.minimum_sample:
            raise ValueError("source result minimum_sample must match promotion minimum_sample")
        if self.result.preferred_method != self.preferred_method:
            raise ValueError("source result preferred_method must match promotion preferred_method")
        if self.result.improvement_over_raw_brier != self.improvement_over_raw_brier:
            raise ValueError("source result Brier improvement must match promotion")
        if self.result.preferred_method is None:
            raise ValueError("source result requires a preferred method")
        if self.result.improvement_over_raw_brier is None or self.result.improvement_over_raw_brier <= 0:
            raise ValueError("source result must improve Brier over raw implied")
        if self.result.raw_implied.status != "COMPUTED" or self.result.raw_implied.sample_size < self.minimum_sample:
            raise ValueError("raw implied metric requires the minimum sample")
        preferred = next((item for item in self.result.methods if item.method == self.preferred_method), None)
        if preferred is None or preferred.status != "COMPUTED" or preferred.sample_size < self.minimum_sample:
            raise ValueError("preferred de-vig method requires the minimum sample")
        expected_source = stable_fingerprint(self.result.model_dump(mode="json"))
        if self.source_result_fingerprint != expected_source:
            raise ValueError("source result fingerprint mismatch")
        return self

    def fingerprint_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"packet_fingerprint"})


class DevigCalibrationPromotionStore:
    def __init__(self, data_root: str | Path):
        self.path = Path(data_root) / "bookmaker" / "devig_calibration" / "promotions.jsonl"
        self.lock_path = self.path.parent / ".devig_calibration_promotions.lock"

    def records(self) -> list[DevigCalibrationPromotionRecord]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return [DevigCalibrationPromotionRecord.model_validate(json.loads(line)) for line in handle if line.strip()]

    def append(
        self,
        *,
        promotion_id: str,
        result: DevigCalibrationResult,
        promoted_at: datetime,
    ) -> DevigCalibrationPromotionRecord:
        if promoted_at.tzinfo is None or promoted_at.utcoffset() is None:
            raise ValueError("promoted_at must be timezone-aware")
        if result.status != "COMPUTED":
            raise ValueError("only COMPUTED de-vig calibration results can be promoted")
        if result.preferred_method is None:
            raise ValueError("de-vig calibration promotion requires a preferred method")
        if result.improvement_over_raw_brier is None or result.improvement_over_raw_brier <= 0:
            raise ValueError("de-vig calibration promotion requires positive Brier improvement over raw")
        source_result_fingerprint = stable_fingerprint(result.model_dump(mode="json"))
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            existing = self.records()
            if any(item.promotion_id == promotion_id for item in existing):
                raise ValueError(f"duplicate promotion_id: {promotion_id}")
            if any(item.source_result_fingerprint == source_result_fingerprint for item in existing):
                raise ValueError(f"duplicate source_result_fingerprint: {source_result_fingerprint}")
            seed = DevigCalibrationPromotionRecord(
                promotion_id=promotion_id,
                bookmaker=result.bookmaker,
                sport=result.sport,
                market_class=result.market_class,
                odds_bucket=result.odds_bucket,
                preferred_method=result.preferred_method,
                as_of=result.as_of,
                promoted_at=promoted_at,
                minimum_sample=result.minimum_sample,
                improvement_over_raw_brier=float(result.improvement_over_raw_brier),
                source_result_fingerprint=source_result_fingerprint,
                result=result,
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
        sport: str | None = None,
        market_class: str | None = None,
        odds_bucket: str | None = None,
        at_or_before: datetime | None = None,
    ) -> list[DevigCalibrationPromotionRecord]:
        if at_or_before is not None:
            if at_or_before.tzinfo is None or at_or_before.utcoffset() is None:
                raise ValueError("at_or_before must be timezone-aware")
            at_or_before = at_or_before.astimezone(timezone.utc)
        rows = [
            item for item in self.records()
            if (bookmaker is None or item.bookmaker == bookmaker)
            and (sport is None or item.sport == sport)
            and (market_class is None or item.market_class == market_class)
            and (odds_bucket is None or item.odds_bucket == odds_bucket)
            and (at_or_before is None or (item.as_of <= at_or_before and item.promoted_at <= at_or_before))
        ]
        return sorted(rows, key=lambda item: (item.as_of, item.promoted_at, item.promotion_id))

    def integrity_issues(self) -> list[str]:
        try:
            rows = self.records()
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            return [str(exc)]
        issues: list[str] = []
        if len({row.promotion_id for row in rows}) != len(rows):
            issues.append("duplicate promotion_id")
        if len({row.source_result_fingerprint for row in rows}) != len(rows):
            issues.append("duplicate source_result_fingerprint")
        for row in rows:
            if stable_fingerprint(row.result.model_dump(mode="json")) != row.source_result_fingerprint:
                issues.append(f"source result fingerprint mismatch: {row.promotion_id}")
            if stable_fingerprint(row.fingerprint_payload()) != row.packet_fingerprint:
                issues.append(f"packet fingerprint mismatch: {row.promotion_id}")
        return issues
