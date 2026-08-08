"""Pricing residuals between observed devigged prices and supplied baselines."""
from __future__ import annotations

def pricing_residuals(observed: dict[str, float], baseline: dict[str, float]) -> dict[str, float] | None:
    """Return observed minus baseline for exactly matching selections, else None."""
    if not observed or not baseline or set(observed) != set(baseline): return None
    return {s: observed[s] - baseline[s] for s in sorted(observed)}
