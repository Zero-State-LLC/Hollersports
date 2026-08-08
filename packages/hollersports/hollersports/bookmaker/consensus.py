"""Consensus calculations across observed bookmaker quotes."""
from __future__ import annotations
from .devig import proportional_devig
from .models import BookmakerQuote

def consensus_probabilities(quotes: tuple[BookmakerQuote, ...]) -> dict[str, float] | None:
    """Average devigged observed probabilities by selection across bookmakers."""
    buckets: dict[str, list[float]] = {}
    for quote in quotes:
        devigged = proportional_devig(quote.outcomes)
        if devigged is None: continue
        for selection, probability in devigged.items(): buckets.setdefault(selection, []).append(probability)
    return None if not buckets else {s: sum(v)/len(v) for s, v in sorted(buckets.items())}

def consensus_summary(quotes: tuple[BookmakerQuote, ...]) -> dict[str, object]:
    """Return advisory-only consensus metadata for observed quotes."""
    c = consensus_probabilities(quotes)
    return {"mode":"SHADOW_ONLY","advisory_mode":"ADVISORY_ONLY","capital_authority":False,"execution_authority":False,"status":"COMPUTED" if c is not None else "NOT_COMPUTABLE","probabilities": c or {},"bookmakers_observed": sorted({q.bookmaker for q in quotes})}
