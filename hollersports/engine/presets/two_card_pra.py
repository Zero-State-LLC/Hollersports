# FILE: hollersports/engine/presets/two_card_pra.py
# Two-card PRA system preset + boost-aware execution.
# This module expects that your simulation layer supplies p_sweep for each card.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from hollersports.engine.boost import (
    BoostPolicy,
    CardSimResult,
    BoostDecision,
    decide_boost_aware_two_card_system,
)


@dataclass(frozen=True)
class TwoCardPreset:
    """
    Immutable description of the 2-card system.
    legs are represented as stable string identifiers (market_key or readable token).
    """
    card_a_id: str
    card_b_id: str
    card_a_legs: Tuple[str, ...]   # Safe (3)
    card_b_legs: Tuple[str, ...]   # Edge (4)

    def fingerprint(self) -> str:
        import hashlib, json
        payload = {
            "card_a_id": self.card_a_id,
            "card_b_id": self.card_b_id,
            "card_a_legs": self.card_a_legs,
            "card_b_legs": self.card_b_legs,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def run_boost_aware_execution(
    *,
    preset: TwoCardPreset,
    profit_boost_frac: float,
    p_sweep_card_a: float,
    p_sweep_card_b: float,
    corr_proxy_a: float,
    corr_proxy_b: float,
    sim_provenance: Dict[str, Any],
    policy: BoostPolicy | None = None,
) -> Dict[str, Any]:
    """
    Returns decision + printable execution plan.
    """
    card_a = CardSimResult(
        card_id="A_SAFE_3",
        legs=preset.card_a_legs,
        p_sweep=float(p_sweep_card_a),
        corr_proxy=float(corr_proxy_a),
        provenance=sim_provenance,
    )
    card_b = CardSimResult(
        card_id="B_EDGE_4",
        legs=preset.card_b_legs,
        p_sweep=float(p_sweep_card_b),
        corr_proxy=float(corr_proxy_b),
        provenance=sim_provenance,
    )

    decision: BoostDecision = decide_boost_aware_two_card_system(
        profit_boost_frac=float(profit_boost_frac),
        card_a=card_a,
        card_b=card_b,
        policy=policy,
    )

    plan = {
        "preset_fingerprint": preset.fingerprint(),
        "boost_frac": float(profit_boost_frac),
        "allowed_cards": decision.allowed_cards,
        "stake_weights": decision.stake_weights,
        "breakeven": decision.breakeven,
        "ev_units": decision.ev_units,
        "decision_fingerprint": decision.decision_fingerprint,
        "cards": {
            "A_SAFE_3": {"legs": list(preset.card_a_legs), "p_sweep": float(p_sweep_card_a), "corr": float(corr_proxy_a)},
            "B_EDGE_4": {"legs": list(preset.card_b_legs), "p_sweep": float(p_sweep_card_b), "corr": float(corr_proxy_b)},
        },
        "provenance": sim_provenance,
    }
    return plan
