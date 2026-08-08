"""Stable fingerprints and historical bookmaker diagnostics."""
from __future__ import annotations
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any
from .models import BookmakerFingerprint


def stable_fingerprint(payload: Mapping[str, Any]) -> str:
    """Hash a JSON-compatible payload with sorted keys for deterministic identity."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _num(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in row and row[key] is not None:
            try:
                value = float(row[key])
            except (TypeError, ValueError):
                return None
            return value if math.isfinite(value) else None
    return None


def _outcome(row: Mapping[str, Any]) -> int | None:
    for key in ("outcome", "actual", "settled", "winner", "won"):
        if key in row and row[key] is not None:
            value = row[key]
            if isinstance(value, bool):
                return 1 if value else 0
            if isinstance(value, str):
                lowered = value.lower()
                if lowered in {"1", "true", "win", "won", "yes"}:
                    return 1
                if lowered in {"0", "false", "loss", "lost", "no"}:
                    return 0
            if value in (0, 1):
                return int(value)
    return None


def _provenance(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ("source", "source_hash", "event_id", "market_id", "selection") if key in row and row[key] is not None}


def bookmaker_fingerprint(bookmaker: str, rows: Sequence[Mapping[str, Any]], *, minimum_sample: int = 20, ece_bins: int = 10) -> BookmakerFingerprint:
    """Calculate bookmaker diagnostics only from supplied historical rows.

    Expected optional row fields: probability/fair_probability/prediction,
    outcome/actual/won, raw_probability, overround/hold, bias, stale/stale_seconds,
    source, source_hash. Missing evidence yields NOT_COMPUTABLE fields.
    """
    if minimum_sample <= 0 or ece_bins <= 0:
        return BookmakerFingerprint(
            status="NOT_COMPUTABLE",
            bookmaker=bookmaker,
            sample_size=0,
            minimum_sample=max(0, minimum_sample),
            reason="minimum_sample and ece_bins must be positive",
        )
    scoped = [
        row
        for row in rows
        if str(row.get("bookmaker", bookmaker)) == bookmaker
        and str(row.get("source") or "").strip()
        and str(row.get("source_hash") or "").strip()
    ]
    sample_size = len(scoped)
    provenance = [_provenance(row) for row in scoped if _provenance(row)]
    if sample_size < minimum_sample:
        return BookmakerFingerprint(
            status="NOT_COMPUTABLE",
            bookmaker=bookmaker,
            sample_size=sample_size,
            minimum_sample=minimum_sample,
            fields={},
            reason="minimum provenance-complete sample not met",
            source_provenance=provenance,
        )

    scored: list[tuple[float, int]] = []
    holds: list[float] = []
    biases: list[float] = []
    stale_values: list[float] = []
    for row in scoped:
        p = _num(row, "probability", "fair_probability", "prediction", "predicted_probability")
        y = _outcome(row)
        if p is not None and 0.0 < p < 1.0 and y is not None:
            scored.append((p, y))
        hold = _num(row, "hold", "overround")
        if hold is None:
            raw = _num(row, "raw_probability")
            fair = _num(row, "fair_probability", "probability")
            if raw is not None and fair is not None:
                hold = raw - fair
        if hold is not None:
            holds.append(hold)
        bias = _num(row, "bias")
        if bias is not None:
            biases.append(bias)
        elif p is not None and y is not None:
            biases.append(p - y)
        stale = _num(row, "stale", "is_stale")
        if stale is None:
            stale_seconds = _num(row, "stale_seconds", "age_seconds")
            stale_threshold = _num(row, "stale_threshold_seconds") or 300.0
            if stale_seconds is not None:
                stale = 1.0 if stale_seconds > stale_threshold else 0.0
        if stale is not None:
            stale_values.append(1.0 if stale > 0.0 else 0.0)

    fields: dict[str, str] = {}
    field_sample_sizes = {
        "brier": len(scored),
        "log_loss": len(scored),
        "ece": len(scored),
        "hold": len(holds),
        "bias": len(biases),
        "stale_rate": len(stale_values),
    }
    brier = log_loss = ece = None
    if len(scored) >= minimum_sample:
        brier = sum((p - y) ** 2 for p, y in scored) / len(scored)
        log_loss = -sum(y * math.log(max(min(p, 1 - 1e-15), 1e-15)) + (1 - y) * math.log(max(min(1 - p, 1 - 1e-15), 1e-15)) for p, y in scored) / len(scored)
        bins: list[list[tuple[float, int]]] = [[] for _ in range(ece_bins)]
        for p, y in scored:
            bins[min(ece_bins - 1, int(p * ece_bins))].append((p, y))
        ece = sum((len(bucket) / len(scored)) * abs((sum(p for p, _ in bucket) / len(bucket)) - (sum(y for _, y in bucket) / len(bucket))) for bucket in bins if bucket)
        fields.update({"brier": "COMPUTED", "log_loss": "COMPUTED", "ece": "COMPUTED"})
    else:
        fields.update({"brier": "NOT_COMPUTABLE", "log_loss": "NOT_COMPUTABLE", "ece": "NOT_COMPUTABLE"})

    hold_value = sum(holds) / len(holds) if len(holds) >= minimum_sample else None
    bias_value = sum(biases) / len(biases) if len(biases) >= minimum_sample else None
    stale_rate = sum(stale_values) / len(stale_values) if len(stale_values) >= minimum_sample else None
    fields["hold"] = "COMPUTED" if len(holds) >= minimum_sample else "NOT_COMPUTABLE"
    fields["bias"] = "COMPUTED" if len(biases) >= minimum_sample else "NOT_COMPUTABLE"
    fields["stale_rate"] = "COMPUTED" if len(stale_values) >= minimum_sample else "NOT_COMPUTABLE"
    computed_any = any(value == "COMPUTED" for value in fields.values())
    return BookmakerFingerprint(
        status="COMPUTED" if computed_any else "NOT_COMPUTABLE",
        bookmaker=bookmaker,
        sample_size=sample_size,
        minimum_sample=minimum_sample,
        brier=brier,
        log_loss=log_loss,
        ece=ece,
        hold=hold_value,
        bias=bias_value,
        stale_rate=stale_rate,
        fields=fields,
        field_sample_sizes=field_sample_sizes,
        reason=None if computed_any else "no supported evidence fields supplied",
        source_provenance=provenance,
    )
