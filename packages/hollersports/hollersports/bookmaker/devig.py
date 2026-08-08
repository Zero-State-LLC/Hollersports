"""Deterministic devig helpers for observed bookmaker prices.

Return None when inputs are insufficient and never invent probabilities.
"""
from __future__ import annotations
from .models import OutcomePrice

def american_to_implied_probability(american_odds: int) -> float:
    """Convert observed American odds to raw implied probability."""
    if american_odds in (-100, 0): raise ValueError("invalid american odds")
    return 100.0/(american_odds+100.0) if american_odds > 0 else abs(float(american_odds))/(abs(float(american_odds))+100.0)

def outcome_implied_probability(outcome: OutcomePrice) -> float | None:
    """Return raw implied probability from observed fields, or None."""
    if outcome.observed_probability is not None: return outcome.observed_probability
    if outcome.decimal_odds is not None: return 1.0/outcome.decimal_odds
    if outcome.american_odds is not None: return american_to_implied_probability(outcome.american_odds)
    return None

def proportional_devig(outcomes: tuple[OutcomePrice, ...]) -> dict[str, float] | None:
    """Remove overround proportionally for a complete observed outcome set."""
    raw={}
    for outcome in outcomes:
        p=outcome_implied_probability(outcome)
        if p is None or p <= 0.0: return None
        raw[outcome.selection]=p
    total=sum(raw.values())
    return None if total <= 0.0 else {k:v/total for k,v in raw.items()}
