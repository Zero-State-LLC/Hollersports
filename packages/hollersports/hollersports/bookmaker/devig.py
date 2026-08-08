"""Deterministic de-vig helpers for observed bookmaker prices.

Return NOT_COMPUTABLE packets when inputs are insufficient and never invent probabilities.
"""
from __future__ import annotations
import math
from collections.abc import Mapping
from .models import DevigResult, OutcomePrice

_EPS = 1e-12


def american_to_implied_probability(american_odds: int) -> float:
    """Convert observed American odds to raw implied probability."""
    if american_odds in (-100, 0):
        raise ValueError("invalid american odds")
    return 100.0 / (american_odds + 100.0) if american_odds > 0 else abs(float(american_odds)) / (abs(float(american_odds)) + 100.0)


def outcome_implied_probability(outcome: OutcomePrice) -> float | None:
    """Return raw implied probability from observed fields, or None."""
    if outcome.observed_probability is not None:
        return outcome.observed_probability
    if outcome.decimal_odds is not None:
        return 1.0 / outcome.decimal_odds
    if outcome.american_odds is not None:
        return american_to_implied_probability(outcome.american_odds)
    return None


def _raw_probabilities(outcomes: tuple[OutcomePrice, ...]) -> tuple[dict[str, float], str | None]:
    raw: dict[str, float] = {}
    if not outcomes:
        return raw, "no outcomes supplied"
    for outcome in outcomes:
        p = outcome_implied_probability(outcome)
        if p is None or not math.isfinite(p) or p <= 0.0 or p >= 1.0:
            return {}, f"invalid or missing observed probability for {outcome.selection}"
        if outcome.selection in raw:
            return {}, f"duplicate selection {outcome.selection}"
        raw[outcome.selection] = p
    total = sum(raw.values())
    if total <= 0.0 or not math.isfinite(total):
        return {}, "invalid probability total"
    return raw, None


def _uncertainty(raw: Mapping[str, float], fair: Mapping[str, float]) -> float:
    if not raw or not fair:
        return 1.0
    return float(sum(abs(raw[k] - fair[k]) for k in fair if k in raw) / 2.0)


def _packet(method: str, parameters: Mapping[str, object], raw: Mapping[str, float], fair: Mapping[str, float] | None, reason: str | None) -> DevigResult:
    overround = sum(raw.values()) - 1.0 if raw else None
    if fair is None:
        return DevigResult(status="NOT_COMPUTABLE", method=method, parameters=dict(parameters), raw_probabilities=dict(raw), overround=overround, uncertainty=1.0, reason=reason)
    return DevigResult(status="COMPUTED", method=method, parameters=dict(parameters), raw_probabilities=dict(raw), overround=overround, fair_probabilities=dict(sorted(fair.items())), uncertainty=_uncertainty(raw, fair), reason=reason)


def devig(outcomes: tuple[OutcomePrice, ...], method: str = "MULTIPLICATIVE", **parameters: object) -> DevigResult:
    """Run a deterministic de-vig method and return a fail-closed result packet."""
    normalized = method.upper()
    if normalized == "MULTIPLICATIVE":
        return multiplicative_devig(outcomes, **parameters)
    if normalized == "ADDITIVE":
        return additive_devig(outcomes, **parameters)
    if normalized == "POWER":
        return power_devig(outcomes, **parameters)
    if normalized == "SHIN":
        return shin_devig(outcomes, **parameters)
    raw, reason = _raw_probabilities(outcomes)
    return _packet("MULTIPLICATIVE", {"requested_method": method, **parameters}, raw, None, reason or "unsupported de-vig method")


def multiplicative_devig(outcomes: tuple[OutcomePrice, ...], *, min_overround: float = -0.25, max_overround: float = 0.75) -> DevigResult:
    """Remove hold by dividing each raw probability by the raw total."""
    raw, reason = _raw_probabilities(outcomes)
    params = {"min_overround": min_overround, "max_overround": max_overround}
    if reason:
        return _packet("MULTIPLICATIVE", params, raw, None, reason)
    overround = sum(raw.values()) - 1.0
    if overround < min_overround or overround > max_overround:
        return _packet("MULTIPLICATIVE", params, raw, None, "overround outside explicit bounds")
    total = sum(raw.values())
    return _packet("MULTIPLICATIVE", params, raw, {k: v / total for k, v in raw.items()}, None)


def additive_devig(outcomes: tuple[OutcomePrice, ...], *, min_probability: float = 1e-9) -> DevigResult:
    """Subtract equal probability mass from each selection, then normalize."""
    raw, reason = _raw_probabilities(outcomes)
    params = {"min_probability": min_probability}
    if reason:
        return _packet("ADDITIVE", params, raw, None, reason)
    n = len(raw)
    adjusted = {k: v - ((sum(raw.values()) - 1.0) / n) for k, v in raw.items()}
    if any(v <= min_probability or not math.isfinite(v) for v in adjusted.values()):
        return _packet("ADDITIVE", params, raw, None, "additive adjustment produced non-positive probability")
    total = sum(adjusted.values())
    return _packet("ADDITIVE", params, raw, {k: v / total for k, v in adjusted.items()}, None)


def power_devig(outcomes: tuple[OutcomePrice, ...], *, tolerance: float = 1e-12, max_iterations: int = 100) -> DevigResult:
    """Find exponent c such that sum(raw_probability ** c) equals one."""
    raw, reason = _raw_probabilities(outcomes)
    params = {"tolerance": tolerance, "max_iterations": max_iterations}
    if reason:
        return _packet("POWER", params, raw, None, reason)
    if max_iterations <= 0 or tolerance <= 0:
        return _packet("POWER", params, raw, None, "invalid power solver parameters")
    lo, hi = 0.01, 100.0
    for _ in range(max_iterations):
        mid = (lo + hi) / 2.0
        value = sum(p**mid for p in raw.values())
        if abs(value - 1.0) <= tolerance:
            fair = {k: v**mid for k, v in raw.items()}
            return _packet("POWER", {**params, "exponent": mid}, raw, fair, None)
        if value > 1.0:
            lo = mid
        else:
            hi = mid
    exponent = (lo + hi) / 2.0
    fair = {k: v**exponent for k, v in raw.items()}
    total = sum(fair.values())
    return _packet("POWER", {**params, "exponent": exponent}, raw, {k: v / total for k, v in fair.items()}, "power solver reached max_iterations")


def shin_devig(outcomes: tuple[OutcomePrice, ...], *, z: float = 0.0) -> DevigResult:
    """Apply the deterministic Shin-style insider adjustment with explicit z.

    z=0 is equivalent to multiplicative de-vig. Larger z shifts mass away from
    shorter prices. The caller must supply z from evidence when using calibration.
    """
    raw, reason = _raw_probabilities(outcomes)
    params = {"z": z}
    if reason:
        return _packet("SHIN", params, raw, None, reason)
    if z < 0.0 or z >= 1.0 or not math.isfinite(z):
        return _packet("SHIN", params, raw, None, "invalid Shin z parameter")
    if z == 0.0:
        total = sum(raw.values())
        return _packet("SHIN", params, raw, {k: v / total for k, v in raw.items()}, None)
    adjusted = {k: math.sqrt(z * z + 4.0 * (1.0 - z) * v * v / sum(raw.values())) - z for k, v in raw.items()}
    if any(v <= 0.0 or not math.isfinite(v) for v in adjusted.values()):
        return _packet("SHIN", params, raw, None, "Shin adjustment produced invalid probability")
    total = sum(adjusted.values())
    return _packet("SHIN", params, raw, {k: v / total for k, v in adjusted.items()}, None)


def proportional_devig(outcomes: tuple[OutcomePrice, ...]) -> dict[str, float] | None:
    """Backward-compatible multiplicative fair probabilities for observed outcomes."""
    result = multiplicative_devig(outcomes)
    return result.fair_probabilities if result.status == "COMPUTED" else None
