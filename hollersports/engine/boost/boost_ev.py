# FILE: hollersports/engine/boost/boost_ev.py
# Boost-aware modifier for HollerSports.
# Deterministic, auditable, no live scraping.
#
# Concept:
# - Profit boosts change PAYOUT, not probability.
# - We compute breakeven win-rate for a given boost and odds model.
# - Then we gate: which card(s) are allowed, and how to size stakes.
#
# Supports:
# - 2-card system (Card A safer 3-leg, Card B 4-leg expansion)
# - Boost-aware selection + stake weights
#
# NOTE: This module DOES NOT change projections. It only changes execution policy.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple
import hashlib
import json


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# -----------------------------
# Core EV math
# -----------------------------

def breakeven_win_rate_profit_boost(
    *,
    profit_boost_frac: float,
    base_profit_per_unit: float = 1.0,
    loss_per_unit: float = 1.0,
) -> float:
    """
    Profit boost means:
      win profit = base_profit_per_unit * (1 + boost)
      loss = loss_per_unit

    Breakeven p solves:
      p*win_profit - (1-p)*loss = 0

    Returns p in [0,1].
    """
    b = max(0.0, float(profit_boost_frac))
    win_profit = float(base_profit_per_unit) * (1.0 + b)
    loss = float(loss_per_unit)
    denom = win_profit + loss
    if denom <= 0:
        return 1.0
    return _clamp(loss / denom, 0.0, 1.0)


def expected_value_units(
    *,
    p_win: float,
    profit_boost_frac: float,
    base_profit_per_unit: float = 1.0,
    loss_per_unit: float = 1.0,
) -> float:
    """
    EV in stake units for a bet with win probability p_win.
    """
    p = _clamp(float(p_win), 0.0, 1.0)
    b = max(0.0, float(profit_boost_frac))
    win_profit = float(base_profit_per_unit) * (1.0 + b)
    loss = float(loss_per_unit)
    return p * win_profit - (1.0 - p) * loss


# -----------------------------
# Policy config
# -----------------------------

CardId = Literal["A_SAFE_3", "B_EDGE_4"]

@dataclass(frozen=True)
class BoostPolicy:
    """
    Governs how boosts modify execution.
    This DOES NOT alter projections; it only gates which cards are allowed and stake weights.

    - min_ev_units: minimum EV (per unit stake) required to allow a card when boost is present.
    - min_margin_over_breakeven: required probability margin above breakeven to allow a card.
    - safe_card_max_allocation: cap on allocation to Card A (usually high)
    - edge_card_max_allocation: cap on allocation to Card B (usually lower)
    """
    min_ev_units: float = 0.05
    min_margin_over_breakeven: float = 0.07

    safe_card_max_allocation: float = 0.85
    edge_card_max_allocation: float = 0.35

    # guardrail: if boost is small, don't push risk just because it's "a boost"
    boost_floor_to_expand: float = 0.30  # 30%+
    boost_floor_to_split: float = 0.50   # 50%+ prefer 2-card split

    def fingerprint(self) -> str:
        return _sha256(_stable_json(self.__dict__))


@dataclass(frozen=True)
class CardSimResult:
    """
    Input from your simulation layer.
    """
    card_id: CardId
    legs: Tuple[str, ...]              # stable identifiers (market_keys or human labels)
    p_sweep: float                     # simulated probability the card hits
    corr_proxy: float                  # correlation proxy for the card
    provenance: Dict[str, Any]         # sim fingerprint, slate fingerprint, etc.

    def fingerprint(self) -> str:
        payload = {
            "card_id": self.card_id,
            "legs": self.legs,
            "p_sweep": self.p_sweep,
            "corr_proxy": self.corr_proxy,
            "provenance": self.provenance,
        }
        return _sha256(_stable_json(payload))


@dataclass(frozen=True)
class BoostDecision:
    """
    Output: execution decision & sizing.
    """
    allowed_cards: Tuple[CardId, ...]
    stake_weights: Dict[CardId, float]   # sums to <= 1.0
    ev_units: Dict[CardId, float]
    breakeven: float
    policy_fingerprint: str
    decision_fingerprint: str


# -----------------------------
# Decision engine
# -----------------------------

def decide_boost_aware_two_card_system(
    *,
    profit_boost_frac: float,
    card_a: CardSimResult,
    card_b: CardSimResult,
    policy: Optional[BoostPolicy] = None,
    base_profit_per_unit: float = 1.0,
    loss_per_unit: float = 1.0,
) -> BoostDecision:
    """
    Given simulated sweep probabilities for Card A and Card B, decide:
    - which cards to play
    - stake weights (allocation)
    - with boost-aware gating

    Deterministic: same inputs => same output.
    """
    if policy is None:
        policy = BoostPolicy()

    b = max(0.0, float(profit_boost_frac))
    breakeven = breakeven_win_rate_profit_boost(
        profit_boost_frac=b,
        base_profit_per_unit=base_profit_per_unit,
        loss_per_unit=loss_per_unit,
    )

    # EV per unit for each card
    ev_a = expected_value_units(
        p_win=card_a.p_sweep,
        profit_boost_frac=b,
        base_profit_per_unit=base_profit_per_unit,
        loss_per_unit=loss_per_unit,
    )
    ev_b = expected_value_units(
        p_win=card_b.p_sweep,
        profit_boost_frac=b,
        base_profit_per_unit=base_profit_per_unit,
        loss_per_unit=loss_per_unit,
    )

    # Probability margins over breakeven
    m_a = float(card_a.p_sweep - breakeven)
    m_b = float(card_b.p_sweep - breakeven)

    allow_a = (ev_a >= policy.min_ev_units) and (m_a >= policy.min_margin_over_breakeven)
    allow_b = (ev_b >= policy.min_ev_units) and (m_b >= policy.min_margin_over_breakeven)

    allowed: List[CardId] = []
    if allow_a:
        allowed.append("A_SAFE_3")
    if allow_b:
        allowed.append("B_EDGE_4")

    # Default: if nothing passes, fall back to safest only if it is not catastrophically negative
    if not allowed:
        # Fail-safe: allow Card A if it's at least above breakeven (even if margins not met)
        if card_a.p_sweep >= breakeven:
            allowed = ["A_SAFE_3"]

    # Stake allocation logic
    weights: Dict[CardId, float] = {}
    if not allowed:
        weights = {"A_SAFE_3": 0.0, "B_EDGE_4": 0.0}
    elif allowed == ["A_SAFE_3"]:
        weights["A_SAFE_3"] = _clamp(policy.safe_card_max_allocation, 0.0, 1.0)
        weights["B_EDGE_4"] = 0.0
    elif allowed == ["B_EDGE_4"]:
        # Rare: only play B if A failed but B passed
        weights["A_SAFE_3"] = 0.0
        weights["B_EDGE_4"] = _clamp(policy.edge_card_max_allocation, 0.0, 1.0)
    else:
        # Both allowed: split based on boost size and relative EV
        # More boost => more permission to allocate small % to B.
        # But keep B capped and A dominant.
        boost_factor = _clamp((b - policy.boost_floor_to_expand) / max(1e-9, (1.0 - policy.boost_floor_to_expand)), 0.0, 1.0)

        # Relative EV weighting, with tiny smoothing to avoid zero division
        ev_pos_a = max(0.0, ev_a)
        ev_pos_b = max(0.0, ev_b)
        total = ev_pos_a + ev_pos_b + 1e-9
        rel_b = ev_pos_b / total

        # Compute B weight: capped, scaled by boost_factor and its relative EV
        b_weight = _clamp(rel_b * boost_factor * policy.edge_card_max_allocation, 0.05 if b >= policy.boost_floor_to_split else 0.0, policy.edge_card_max_allocation)
        a_weight = _clamp(1.0 - b_weight, 0.0, policy.safe_card_max_allocation)

        # Ensure dominance of A
        if a_weight < 0.50:
            a_weight = 0.50
            b_weight = _clamp(1.0 - a_weight, 0.0, policy.edge_card_max_allocation)

        weights["A_SAFE_3"] = a_weight
        weights["B_EDGE_4"] = b_weight

    # Normalize to <=1.0 (not required to sum to 1; you might hold cash)
    total_w = weights.get("A_SAFE_3", 0.0) + weights.get("B_EDGE_4", 0.0)
    if total_w > 1.0:
        weights["A_SAFE_3"] /= total_w
        weights["B_EDGE_4"] /= total_w

    decision_payload = {
        "profit_boost_frac": b,
        "breakeven": breakeven,
        "policy": policy.__dict__,
        "card_a": {"fp": card_a.fingerprint(), "p": card_a.p_sweep, "ev": ev_a, "m": m_a},
        "card_b": {"fp": card_b.fingerprint(), "p": card_b.p_sweep, "ev": ev_b, "m": m_b},
        "allowed": allowed,
        "weights": weights,
    }

    return BoostDecision(
        allowed_cards=tuple(allowed),
        stake_weights=weights,
        ev_units={"A_SAFE_3": float(ev_a), "B_EDGE_4": float(ev_b)},
        breakeven=float(breakeven),
        policy_fingerprint=policy.fingerprint(),
        decision_fingerprint=_sha256(_stable_json(decision_payload)),
    )
