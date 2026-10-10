# FILE: hollersports/engine/boost_integration.py
# Integration layer: wires boost-aware execution into existing Monte Carlo simulation pipeline.
# This connects the existing simulation.py and picks_generator.py with the new boost module.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import logging
import hashlib
import json

from hollersports.engine.boost import BoostPolicy, CardSimResult, decide_boost_aware_two_card_system
from hollersports.engine.presets import TwoCardPreset, run_boost_aware_execution

logger = logging.getLogger(__name__)


def compute_card_sweep_probability(
    picks: List[Dict[str, Any]],
    *,
    assume_independence: bool = False,
    correlation_adjustment: float = 0.0,
) -> float:
    """
    Compute the aggregate probability that all picks in a card hit.

    Args:
        picks: List of individual picks with win_probability
        assume_independence: If True, multiply probabilities directly
        correlation_adjustment: Adjustment factor for correlation (0.0 to 1.0)
            Higher values reduce the aggregate probability to account for correlation

    Returns:
        Aggregate sweep probability
    """
    if not picks:
        return 0.0

    # Base case: independent probability (product of all win probabilities)
    p_independent = 1.0
    for pick in picks:
        p_independent *= pick.get("win_probability", 0.5)

    if assume_independence or correlation_adjustment == 0.0:
        return p_independent

    # Adjust for correlation (simple model: reduce probability by correlation factor)
    # More sophisticated models would use copulas or historical correlation matrices
    adjusted_prob = p_independent * (1.0 - correlation_adjustment * 0.5)

    return max(0.0, min(1.0, adjusted_prob))


def estimate_correlation_proxy(picks: List[Dict[str, Any]]) -> float:
    """
    Estimate a correlation proxy for a set of picks.

    This is a placeholder - in production, you'd use:
    - Historical correlation matrices
    - Same-game correlation models
    - Player correlation data

    Args:
        picks: List of individual picks

    Returns:
        Correlation proxy (0.0 = independent, 1.0 = fully correlated)
    """
    if len(picks) <= 1:
        return 0.0

    # Simple heuristic: check for same-game picks
    game_ids = set()
    same_game_count = 0

    for pick in picks:
        game_id = pick.get("game_id")
        if game_id:
            if game_id in game_ids:
                same_game_count += 1
            game_ids.add(game_id)

    # Correlation increases with same-game picks
    # 0 same-game = ~0.05 (low baseline correlation)
    # All same-game = ~0.25 (moderate correlation)
    if len(picks) > 1:
        same_game_ratio = same_game_count / (len(picks) - 1)
        return 0.05 + (same_game_ratio * 0.20)

    return 0.05


def build_two_card_system_from_picks(
    picks: List[Dict[str, Any]],
    *,
    safe_card_size: int = 3,
    edge_card_size: int = 4,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Build a 2-card system from a ranked list of picks.

    Card A (Safe): Top N picks (default 3)
    Card B (Edge): Top N+1 picks (default 4)

    Args:
        picks: List of picks sorted by score/edge
        safe_card_size: Number of legs for safe card
        edge_card_size: Number of legs for edge card

    Returns:
        Tuple of (card_a_picks, card_b_picks)
    """
    if len(picks) < safe_card_size:
        logger.warning(f"Not enough picks ({len(picks)}) for safe card (needs {safe_card_size})")
        return [], []

    card_a_picks = picks[:safe_card_size]

    if len(picks) < edge_card_size:
        logger.warning(f"Not enough picks ({len(picks)}) for edge card (needs {edge_card_size})")
        card_b_picks = []
    else:
        card_b_picks = picks[:edge_card_size]

    return card_a_picks, card_b_picks


def run_boost_aware_two_card_execution(
    picks: List[Dict[str, Any]],
    *,
    profit_boost_frac: float,
    policy: BoostPolicy | None = None,
    safe_card_size: int = 3,
    edge_card_size: int = 4,
    slate_fingerprint: str = "",
    sim_fingerprint: str = "",
) -> Dict[str, Any]:
    """
    Main integration function: takes picks from existing pipeline and runs boost-aware execution.

    Args:
        picks: List of picks from select_optimal_picks()
        profit_boost_frac: Profit boost fraction (e.g., 0.75 for 75% boost)
        policy: Optional custom BoostPolicy
        safe_card_size: Number of legs for Card A
        edge_card_size: Number of legs for Card B
        slate_fingerprint: Fingerprint of the slate
        sim_fingerprint: Fingerprint of the simulation

    Returns:
        Execution plan dict with decision, cards, and metadata
    """
    if not picks:
        logger.error("No picks provided - cannot build cards")
        return {
            "error": "No picks provided",
            "allowed_cards": [],
            "stake_weights": {},
        }

    # Build 2-card system
    card_a_picks, card_b_picks = build_two_card_system_from_picks(
        picks,
        safe_card_size=safe_card_size,
        edge_card_size=edge_card_size,
    )

    if not card_a_picks:
        logger.error("Could not build safe card")
        return {
            "error": "Not enough picks for safe card",
            "allowed_cards": [],
            "stake_weights": {},
        }

    # Compute sweep probabilities
    corr_a = estimate_correlation_proxy(card_a_picks)
    p_sweep_a = compute_card_sweep_probability(card_a_picks, correlation_adjustment=corr_a)

    if card_b_picks:
        corr_b = estimate_correlation_proxy(card_b_picks)
        p_sweep_b = compute_card_sweep_probability(card_b_picks, correlation_adjustment=corr_b)
    else:
        corr_b = 0.0
        p_sweep_b = 0.0

    # Build card legs (market_keys)
    card_a_legs = tuple(pick["market_key"] for pick in card_a_picks)
    card_b_legs = tuple(pick["market_key"] for pick in card_b_picks) if card_b_picks else ()

    # Create preset
    preset = TwoCardPreset(
        card_a_id="A_SAFE_3",
        card_b_id="B_EDGE_4",
        card_a_legs=card_a_legs,
        card_b_legs=card_b_legs if card_b_legs else ("placeholder",),  # Handle empty case
    )

    # Build provenance
    provenance = {
        "slate_fp": slate_fingerprint,
        "sim_fp": sim_fingerprint,
        "preset_fp": preset.fingerprint(),
    }

    # Run boost-aware execution
    if not card_b_picks:
        # Only Card A available - still run decision engine but with dummy Card B
        logger.info("Only Card A available - running single-card execution")

    plan = run_boost_aware_execution(
        preset=preset,
        profit_boost_frac=float(profit_boost_frac),
        p_sweep_card_a=float(p_sweep_a),
        p_sweep_card_b=float(p_sweep_b),
        corr_proxy_a=float(corr_a),
        corr_proxy_b=float(corr_b),
        sim_provenance=provenance,
        policy=policy,
    )

    # Enrich plan with pick details
    plan["pick_details"] = {
        "A_SAFE_3": [
            {
                "market_key": p["market_key"],
                "player_name": p.get("player_name"),
                "market": p.get("market"),
                "line": p.get("line"),
                "side": p.get("side"),
                "win_prob": p.get("win_probability"),
                "edge": p.get("edge"),
            }
            for p in card_a_picks
        ],
        "B_EDGE_4": [
            {
                "market_key": p["market_key"],
                "player_name": p.get("player_name"),
                "market": p.get("market"),
                "line": p.get("line"),
                "side": p.get("side"),
                "win_prob": p.get("win_probability"),
                "edge": p.get("edge"),
            }
            for p in card_b_picks
        ] if card_b_picks else [],
    }

    logger.info(
        f"Boost-aware execution complete | "
        f"Boost: {profit_boost_frac:.1%} | "
        f"Breakeven: {plan['breakeven']:.1%} | "
        f"Allowed: {plan['allowed_cards']} | "
        f"Weights: A={plan['stake_weights'].get('A_SAFE_3', 0):.1%}, "
        f"B={plan['stake_weights'].get('B_EDGE_4', 0):.1%}"
    )

    return plan


def format_execution_plan_for_console(plan: Dict[str, Any]) -> str:
    """
    Format execution plan as human-readable console output.

    Args:
        plan: Execution plan from run_boost_aware_two_card_execution

    Returns:
        Formatted string for console display
    """
    lines = []
    lines.append("=" * 80)
    lines.append("BOOST-AWARE EXECUTION PLAN")
    lines.append("=" * 80)

    if "error" in plan:
        lines.append(f"ERROR: {plan['error']}")
        return "\n".join(lines)

    lines.append(f"\nBoost: {plan['boost_frac']:.1%}")
    lines.append(f"Breakeven Win Rate: {plan['breakeven']:.1%}")
    lines.append(f"\nAllowed Cards: {', '.join(plan['allowed_cards']) if plan['allowed_cards'] else 'NONE'}")

    lines.append("\n" + "-" * 80)
    lines.append("STAKE ALLOCATION")
    lines.append("-" * 80)

    for card_id, weight in plan['stake_weights'].items():
        ev = plan['ev_units'].get(card_id, 0.0)
        card_info = plan['cards'].get(card_id, {})
        p_sweep = card_info.get('p_sweep', 0.0)

        lines.append(f"\n{card_id}:")
        lines.append(f"  Stake Weight: {weight:.1%}")
        lines.append(f"  Sweep Probability: {p_sweep:.1%}")
        lines.append(f"  EV (units): {ev:+.3f}")

        if card_id in plan.get('pick_details', {}):
            lines.append(f"  Legs ({len(plan['pick_details'][card_id])}):")
            for i, leg in enumerate(plan['pick_details'][card_id], 1):
                lines.append(
                    f"    {i}. {leg['player_name']} {leg['market']} "
                    f"{leg['side']} {leg['line']} "
                    f"(p={leg['win_prob']:.1%}, edge={leg['edge']:+.1%})"
                )

    lines.append("\n" + "=" * 80)
    lines.append(f"Decision Fingerprint: {plan['decision_fingerprint'][:16]}...")
    lines.append("=" * 80)

    return "\n".join(lines)
