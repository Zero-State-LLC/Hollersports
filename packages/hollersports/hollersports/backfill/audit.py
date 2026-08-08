from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hollersports.bookmaker.models import MarketSnapshotV2


class EvidenceInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str
    exists: bool
    rows: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    invalid_rows: int = Field(ge=0)
    event_count: int = Field(ge=0)
    earliest_at: datetime | None = None
    latest_at: datetime | None = None
    issues: tuple[str, ...] = ()


class FixtureInventory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    fixture_id: str
    path: str
    complete: bool
    odds_records: int = Field(ge=0)
    result_records: int = Field(ge=0)
    issues: tuple[str, ...] = ()


class BackfillAuditReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["HistoricalBackfillAudit.v1"] = "HistoricalBackfillAudit.v1"
    generated_at: datetime
    data_root: str
    fixtures_root: str
    read_only: Literal[True] = True
    inventories: dict[str, EvidenceInventory]
    fixtures: tuple[FixtureInventory, ...]
    overlapping_market_settlement_events: int = Field(ge=0)
    temporally_ordered_market_settlement_events: int = Field(ge=0)
    v05_fixture_backfill_possible: bool
    v06_temporal_backfill_possible: bool
    blockers: tuple[str, ...]
    next_steps: tuple[str, ...]
    mode: Literal["PAPER_ONLY"] = "PAPER_ONLY"
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    capital_authority: bool = False
    execution_authority: bool = False


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.is_file():
        return [], []
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"unreadable: {exc}"]
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(f"line {number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            issues.append(f"line {number}: object required")
            continue
        rows.append(value)
    return rows, issues


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _inventory(
    path: Path,
    *,
    timestamp_keys: tuple[str, ...],
    event_key: str = "event_id",
    validator: type[BaseModel] | None = None,
    required_keys: tuple[str, ...] = (),
) -> tuple[EvidenceInventory, set[str]]:
    rows, issues = _read_jsonl(path)
    valid = 0
    events: set[str] = set()
    times: list[datetime] = []
    missing_required = 0
    for row in rows:
        try:
            if validator is not None:
                validator.model_validate(row)
            elif any(row.get(key) in (None, "") for key in required_keys):
                raise ValueError("required evidence fields missing")
        except ValueError:
            missing_required += 1
            continue
        valid += 1
        event = str(row.get(event_key) or "").strip()
        if event:
            events.add(event)
        for key in timestamp_keys:
            parsed = _timestamp(row.get(key))
            if parsed is not None:
                times.append(parsed)
                break
    if missing_required:
        issues.append(f"{missing_required} rows failed schema or required-evidence validation")
    return EvidenceInventory(
        path=str(path), exists=path.is_file(), rows=len(rows), valid_rows=valid,
        invalid_rows=len(rows) - valid + len([issue for issue in issues if issue.startswith("line ")]),
        event_count=len(events), earliest_at=min(times) if times else None,
        latest_at=max(times) if times else None, issues=tuple(issues),
    ), events


def _event_times(path: Path, timestamp_keys: tuple[str, ...]) -> dict[str, datetime]:
    rows, _ = _read_jsonl(path)
    times: dict[str, datetime] = {}
    for row in rows:
        event_id = str(row.get("event_id") or "").strip()
        if not event_id:
            continue
        parsed = next((_timestamp(row.get(key)) for key in timestamp_keys if _timestamp(row.get(key)) is not None), None)
        if parsed is not None and (event_id not in times or parsed < times[event_id]):
            times[event_id] = parsed
    return times


def _json_count(path: Path) -> tuple[int, str | None]:
    if not path.is_file():
        return 0, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return 0, f"invalid JSON: {exc}"
    if isinstance(value, list):
        return len(value), None
    if isinstance(value, dict):
        for key in ("records", "events", "markets", "results", "items", "data"):
            if isinstance(value.get(key), list):
                return len(value[key]), None
        return len(value), None
    return 0, "JSON object or array required"


def _fixtures(root: Path) -> tuple[FixtureInventory, ...]:
    if not root.is_dir():
        return ()
    found: list[FixtureInventory] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        required = [child / "meta.json", child / "odds_records.json", child / "results.json"]
        odds_count, odds_issue = _json_count(required[1])
        result_count, result_issue = _json_count(required[2])
        issues = [f"{path.name}: missing" for path in required if not path.is_file()]
        if odds_issue and odds_issue != "missing":
            issues.append(f"odds_records.json: {odds_issue}")
        if result_issue and result_issue != "missing":
            issues.append(f"results.json: {result_issue}")
        found.append(FixtureInventory(
            fixture_id=child.name, path=str(child), complete=not issues,
            odds_records=odds_count, result_records=result_count, issues=tuple(issues),
        ))
    return tuple(found)


def audit_backfill_readiness(
    data_root: str | Path,
    fixtures_root: str | Path,
    *,
    generated_at: datetime | None = None,
) -> BackfillAuditReport:
    """Inspect historical evidence without creating, changing, or deleting files."""
    root = Path(data_root)
    fixture_root = Path(fixtures_root)
    specs = {
        "market_snapshots": (root / "bookmaker" / "market_snapshot.v2.jsonl", ("captured_at",), MarketSnapshotV2, ()),
        "settlements": (root / "ledgers" / "settlements_history.jsonl", ("recorded_at", "settled_at"), None, ("event_id", "market_id", "status", "recorded_at", "source_hash")),
        "prop_ladders": (root / "props" / "ladders" / "observations.jsonl", ("observed_at",), None, ("event_id", "observed_at", "source", "source_hash")),
        "prop_surfaces": (root / "props" / "surfaces" / "surfaces.jsonl", ("derived_at", "observed_at"), None, ("event_id", "observed_at", "derived_at", "ladder_fingerprint")),
        "context_observations": (root / "context" / "observations" / "observations.jsonl", ("recorded_at", "observed_at"), None, ("event_id", "observed_at", "recorded_at", "source_hash")),
        "dependency_observations": (root / "dependency" / "observations" / "observations.jsonl", ("recorded_at", "observed_at"), None, ("event_id", "observed_at", "recorded_at", "source_hash")),
    }
    inventories: dict[str, EvidenceInventory] = {}
    event_sets: dict[str, set[str]] = {}
    for name, (path, timestamp_keys, validator, required) in specs.items():
        inventories[name], event_sets[name] = _inventory(path, timestamp_keys=timestamp_keys, validator=validator, required_keys=required)

    fixtures = _fixtures(fixture_root)
    overlap = len(event_sets["market_snapshots"] & event_sets["settlements"])
    market_times = _event_times(specs["market_snapshots"][0], ("captured_at",))
    settlement_times = _event_times(specs["settlements"][0], ("recorded_at", "settled_at"))
    ordered_overlap = sum(
        settlement_times[event_id] >= market_times[event_id]
        for event_id in market_times.keys() & settlement_times.keys()
    )
    blockers: list[str] = []
    if inventories["market_snapshots"].valid_rows == 0:
        blockers.append("no provenance-valid market_snapshot.v2 history")
    if inventories["settlements"].valid_rows == 0:
        blockers.append("no provenance-complete settled outcomes with recorded timestamps")
    if overlap == 0:
        blockers.append("no event IDs overlap between market memory and settlements")
    elif ordered_overlap == 0:
        blockers.append("overlapping settlements are timestamped before their market observations")
    v05_possible = any(item.complete and item.odds_records > 0 and item.result_records > 0 for item in fixtures)
    v06_possible = not blockers
    next_steps = (
        "run the existing fixture backfill for V0.5 control evidence" if v05_possible else "supply complete fixture odds and result packets",
        "ingest immutable historical market snapshots with original observation timestamps" if inventories["market_snapshots"].valid_rows == 0 else "retain existing market memory unchanged",
        "ingest closing and settlement packets with source hashes and availability timestamps" if inventories["settlements"].valid_rows == 0 else "join market and settlement evidence by event and market IDs",
        "rerun this auditor before enabling any write-capable V0.6 backfill",
    )
    now = generated_at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return BackfillAuditReport(
        generated_at=now.astimezone(timezone.utc), data_root=str(root), fixtures_root=str(fixture_root),
        inventories=inventories, fixtures=fixtures, overlapping_market_settlement_events=overlap,
        temporally_ordered_market_settlement_events=ordered_overlap,
        v05_fixture_backfill_possible=v05_possible, v06_temporal_backfill_possible=v06_possible,
        blockers=tuple(blockers), next_steps=next_steps,
    )
