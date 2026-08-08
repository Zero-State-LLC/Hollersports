"""Append-only JSONL storage for immutable market_snapshot.v2 records.

The store appends validated snapshots and provides temporal reads. It does not
update or delete records, preserving market memory as observed evidence.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .fingerprint import stable_fingerprint
from .models import MarketSnapshotV2

def market_snapshot_path(data_root: Path | str) -> Path:
    """Return the canonical append-only market snapshot path under a data root."""
    return Path(data_root) / "bookmaker" / "market_snapshot.v2.jsonl"

class MarketSnapshotStore:
    """Append-only market memory store for V0.6 bookmaker snapshots."""
    def __init__(self, data_root: Path | str) -> None:
        self.path = market_snapshot_path(data_root)
    def append(self, snapshot: MarketSnapshotV2) -> dict[str, Any]:
        """Append one immutable snapshot as JSONL and return governance metadata."""
        payload = snapshot.model_dump(mode="json")
        payload["fingerprint"] = payload.get("fingerprint") or stable_fingerprint({k: v for k, v in payload.items() if k != "fingerprint"})
        validated = MarketSnapshotV2.model_validate(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(validated.model_dump(mode="json"), sort_keys=True) + "\n")
        return {"schema_version":"market_snapshot.v2","status":"RECORDED","path":str(self.path),"snapshot_id":validated.snapshot_id,"fingerprint":validated.fingerprint,"mode":"SHADOW_ONLY","advisory_mode":"ADVISORY_ONLY","capital_authority":False,"execution_authority":False}
    def query(self, *, event_id: str | None = None, market_type: str | None = None, start_at: str | None = None, end_at: str | None = None) -> list[MarketSnapshotV2]:
        """Load snapshots filtered by event, market, and inclusive timestamp bounds."""
        if not self.path.is_file(): return []
        out: list[MarketSnapshotV2] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line: continue
                try: snapshot = MarketSnapshotV2.model_validate(json.loads(line))
                except (json.JSONDecodeError, ValueError): continue
                if event_id is not None and snapshot.event_id != event_id: continue
                if market_type is not None and snapshot.market_type != market_type: continue
                if start_at is not None and snapshot.captured_at < start_at: continue
                if end_at is not None and snapshot.captured_at > end_at: continue
                out.append(snapshot)
        return sorted(out, key=lambda item: (item.captured_at, item.snapshot_id))

def append_snapshot(data_root: Path | str, snapshot: MarketSnapshotV2) -> dict[str, Any]:
    """Convenience wrapper for appending one market snapshot."""
    return MarketSnapshotStore(data_root).append(snapshot)

def query_snapshots(data_root: Path | str, **query_filters: Any) -> list[MarketSnapshotV2]:
    """Convenience wrapper for temporal market snapshot queries."""
    return MarketSnapshotStore(data_root).query(**query_filters)
