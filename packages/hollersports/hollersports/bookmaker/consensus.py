"""Consensus calculations across observed bookmaker quotes."""
from __future__ import annotations
import math
from collections.abc import Mapping
from typing import Any
from .devig import devig
from .models import BookmakerQuote, ConsensusResult

_FACTOR_KEYS = ("calibration", "freshness", "leadership", "specialization")


def _factor_value(factors: Mapping[str, Mapping[str, float]] | None, bookmaker: str, key: str) -> float | None:
    if not factors or bookmaker not in factors or key not in factors[bookmaker]:
        return None
    value = factors[bookmaker][key]
    return float(value) if isinstance(value, int | float) and math.isfinite(float(value)) and value >= 0.0 else None


def _quote_weight(quote: BookmakerQuote, factors: Mapping[str, Mapping[str, float]] | None) -> tuple[float, dict[str, float], str | None]:
    supplied: dict[str, float] = {}
    for key in _FACTOR_KEYS:
        value = _factor_value(factors, quote.bookmaker, key)
        if value is not None:
            supplied[key] = value
    if not supplied:
        return 1.0, supplied, None
    weight = 1.0
    for value in supplied.values():
        weight *= value
    if weight <= 0.0 or not math.isfinite(weight):
        return 0.0, supplied, "non-positive supplied factor product"
    return weight, supplied, None


def consensus_probabilities(quotes: tuple[BookmakerQuote, ...]) -> dict[str, float] | None:
    """Average multiplicative de-vigged observed probabilities by selection."""
    result = weighted_consensus(quotes)
    return result.probabilities if result.status == "COMPUTED" else None


def weighted_consensus(
    quotes: tuple[BookmakerQuote, ...],
    *,
    factors: Mapping[str, Mapping[str, float]] | None = None,
    method: str = "MULTIPLICATIVE",
    method_parameters: Mapping[str, Any] | None = None,
) -> ConsensusResult:
    """Build a fail-closed weighted consensus from supplied observed quotes.

    Per-book factors are evidence supplied by the caller. Missing calibration is
    neutral and is not labeled BOOK_CALIBRATED.
    """
    params = dict(method_parameters or {})
    accum: dict[str, float] = {}
    raw_weight_by_book: dict[str, float] = {}
    provenance: list[dict[str, Any]] = []
    reasons: list[str] = []

    for quote in quotes:
        d = devig(quote.outcomes, method=method, **params)
        provenance.append({
            "bookmaker": quote.bookmaker,
            "source": quote.source,
            "source_hash": quote.source_hash,
            "market_id": quote.market_id,
            "devig_status": d.status,
            "devig_method": d.method,
        })
        if d.status != "COMPUTED":
            reasons.append(f"{quote.bookmaker}: {d.reason or 'de-vig not computable'}")
            continue
        weight, supplied, weight_reason = _quote_weight(quote, factors)
        provenance[-1]["weight_factors_supplied"] = supplied
        provenance[-1]["calibration_status"] = "SUPPLIED" if "calibration" in supplied else "NOT_COMPUTABLE"
        if weight_reason or weight <= 0.0:
            reasons.append(f"{quote.bookmaker}: {weight_reason or 'invalid weight'}")
            continue
        raw_weight_by_book[quote.bookmaker] = raw_weight_by_book.get(quote.bookmaker, 0.0) + weight
        for selection, probability in d.fair_probabilities.items():
            accum[selection] = accum.get(selection, 0.0) + probability * weight

    total_weight = sum(raw_weight_by_book.values())
    if not accum or total_weight <= 0.0:
        return ConsensusResult(status="NOT_COMPUTABLE", bookmakers_observed=sorted({q.bookmaker for q in quotes}), source_provenance=provenance, reason="; ".join(reasons) or "no computable bookmaker probabilities")

    probabilities = {selection: value / total_weight for selection, value in accum.items()}
    prob_total = sum(probabilities.values())
    if prob_total <= 0.0 or any(v < 0.0 or not math.isfinite(v) for v in probabilities.values()):
        return ConsensusResult(status="NOT_COMPUTABLE", raw_weights=raw_weight_by_book, bookmakers_observed=sorted({q.bookmaker for q in quotes}), source_provenance=provenance, reason="invalid consensus probabilities")
    probabilities = {k: v / prob_total for k, v in probabilities.items()}
    normalized_weights = {book: weight / total_weight for book, weight in raw_weight_by_book.items()}
    entropy = -sum(w * math.log(w) for w in normalized_weights.values() if w > 0.0)
    effective = math.exp(entropy)
    return ConsensusResult(
        status="COMPUTED",
        probabilities=dict(sorted(probabilities.items())),
        weights=dict(sorted(normalized_weights.items())),
        raw_weights=dict(sorted(raw_weight_by_book.items())),
        entropy=entropy,
        effective_book_count=effective,
        bookmakers_observed=sorted({q.bookmaker for q in quotes}),
        source_provenance=provenance,
        reason=None,
    )


def consensus_summary(quotes: tuple[BookmakerQuote, ...]) -> dict[str, object]:
    """Return advisory-only consensus metadata for observed quotes."""
    return weighted_consensus(quotes).model_dump()
