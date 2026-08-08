"""Stable fingerprints for immutable bookmaker market snapshots."""
from __future__ import annotations
import hashlib, json
from typing import Any, Mapping

def stable_fingerprint(payload: Mapping[str, Any]) -> str:
    """Hash a JSON-compatible payload with sorted keys for deterministic identity."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
