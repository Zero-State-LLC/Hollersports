#!/usr/bin/env python3
# FILE: examples/boost_aware_execution_example.py
# Example: Full integration of boost-aware execution with Monte Carlo simulation pipeline.
#
# This demonstrates how to:
# 1. Set up a slate with markets
# 2. Run Monte Carlo simulations
# 3. Generate optimal picks
# 4. Apply boost-aware 2-card execution logic
# 5. Display execution plan

from __future__ import annotations

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from engine.reset_state import init_new_slate_state
from engine.simulation import run_monte_carlo_simulations
from engine.picks_generator import select_optimal_picks
from hollersports.engine import (
    run_boost_aware_two_card_execution,
    format_execution_plan_for_console,
)
from hollersports.engine.boost import BoostPolicy


def create_sample_slate():
    """Create a sample slate with NBA player props."""

    # Define sample markets (player props) - these will be the lines payload
    lines_payload = {
        "lebron_pts_over": {
            "sport": "NBA",
            "game_id": "lal_den_20250115",
            "player_id": "lebron_james",
            "player_name": "LeBron James",
            "market": "PTS",
            "line": 25.5,
        },
        "lebron_ast_over": {
            "sport": "NBA",
            "game_id": "lal_den_20250115",
            "player_id": "lebron_james",
            "player_name": "LeBron James",
            "market": "AST",
            "line": 7.5,
        },
        "lebron_reb_over": {
            "sport": "NBA",
            "game_id": "lal_den_20250115",
            "player_id": "lebron_james",
            "player_name": "LeBron James",
            "market": "REB",
            "line": 8.5,
        },
        "jokic_pts_over": {
            "sport": "NBA",
            "game_id": "lal_den_20250115",
            "player_id": "nikola_jokic",
            "player_name": "Nikola Jokic",
            "market": "PTS",
            "line": 26.5,
        },
        "jokic_reb_over": {
            "sport": "NBA",
            "game_id": "lal_den_20250115",
            "player_id": "nikola_jokic",
            "player_name": "Nikola Jokic",
            "market": "REB",
            "line": 12.5,
        },
        "curry_pts_over": {
            "sport": "NBA",
            "game_id": "gsw_bos_20250115",
            "player_id": "stephen_curry",
            "player_name": "Stephen Curry",
            "market": "PTS",
            "line": 27.5,
        },
        "curry_3pm_over": {
            "sport": "NBA",
            "game_id": "gsw_bos_20250115",
            "player_id": "stephen_curry",
            "player_name": "Stephen Curry",
            "market": "3PM",
            "line": 4.5,
        },
    }

    # Games payload
    games_payload = {
        "lal_den_20250115": {
            "game_id": "lal_den_20250115",
            "home_team": "LAL",
            "away_team": "DEN",
            "game_time": "2025-01-15T19:00:00Z",
        },
        "gsw_bos_20250115": {
            "game_id": "gsw_bos_20250115",
            "home_team": "BOS",
            "away_team": "GSW",
            "game_time": "2025-01-15T19:30:00Z",
        },
    }

    # Initialize slate state
    state = init_new_slate_state(
        slate_id="nba_2025_01_15_main",
        sport="NBA",
        provider="PrizePicks",
        games_payload=games_payload,
        lines_payload=lines_payload,
    )

    # Add game context
    state.game_context.by_game_id["lal_den_20250115"] = {
        "venue": "home",  # Lakers home
        "pace_factor": 1.03,  # Fast pace
        "days_rest": 1,
        "opponent_defensive_rating": 108.0,
    }
    state.game_context.by_game_id["gsw_bos_20250115"] = {
        "venue": "away",  # Warriors away
        "pace_factor": 0.98,  # Slower pace
        "days_rest": 2,
        "opponent_defensive_rating": 102.0,  # Elite defense
    }

    return state


def main():
    """Run complete boost-aware execution example."""
    print("=" * 80)
    print("BOOST-AWARE EXECUTION EXAMPLE")
    print("=" * 80)
    print()

    # 1. Create slate
    print("Step 1: Creating sample slate...")
    state = create_sample_slate()
    print(f"  ✓ Created slate with {len(state.market.lines)} markets")
    print()

    # 2. Run Monte Carlo simulations
    print("Step 2: Running Monte Carlo simulations...")
    state.simulations = run_monte_carlo_simulations(
        state,
        iterations=10000,
        seed=42,  # For reproducibility
    )
    print(f"  ✓ Simulated {len(state.simulations)} markets")
    print()

    # 3. Generate optimal picks
    print("Step 3: Generating optimal picks...")
    picks = select_optimal_picks(
        state,
        strategy="edge",
        min_edge=0.03,  # 3% minimum edge
        max_picks=10,
    )
    print(f"  ✓ Selected {len(picks)} picks")
    if picks:
        print(f"  ✓ Average edge: {sum(p['edge'] for p in picks) / len(picks):.1%}")
    print()

    if not picks:
        print("ERROR: No picks generated - cannot proceed with boost execution")
        return 1

    # 4. Run boost-aware 2-card execution
    print("Step 4: Running boost-aware 2-card execution...")

    # Scenario A: Large boost (75%)
    print("\n  Scenario A: 75% Profit Boost")
    print("  " + "-" * 76)

    policy = BoostPolicy(
        min_ev_units=0.03,
        min_margin_over_breakeven=0.05,
        boost_floor_to_expand=0.30,
        boost_floor_to_split=0.50,
    )

    plan_75 = run_boost_aware_two_card_execution(
        picks=picks,
        profit_boost_frac=0.75,
        policy=policy,
        slate_fingerprint=state.slate.source_fingerprint,
        sim_fingerprint=str(state.provenance.get("simulation_seed", "")),
    )

    print(format_execution_plan_for_console(plan_75))
    print()

    # Scenario B: Small boost (25%)
    print("\n  Scenario B: 25% Profit Boost")
    print("  " + "-" * 76)

    plan_25 = run_boost_aware_two_card_execution(
        picks=picks,
        profit_boost_frac=0.25,
        policy=policy,
        slate_fingerprint=state.slate.source_fingerprint,
        sim_fingerprint=str(state.provenance.get("simulation_seed", "")),
    )

    print(format_execution_plan_for_console(plan_25))
    print()

    # Scenario C: No boost (0%)
    print("\n  Scenario C: No Profit Boost (0%)")
    print("  " + "-" * 76)

    plan_0 = run_boost_aware_two_card_execution(
        picks=picks,
        profit_boost_frac=0.0,
        policy=policy,
        slate_fingerprint=state.slate.source_fingerprint,
        sim_fingerprint=str(state.provenance.get("simulation_seed", "")),
    )

    print(format_execution_plan_for_console(plan_0))
    print()

    print("=" * 80)
    print("EXAMPLE COMPLETE")
    print("=" * 80)
    print()
    print("Key Observations:")
    print("  • Higher boosts lower the breakeven win rate")
    print("  • Boost-aware logic adjusts card selection and stake allocation")
    print("  • Safe Card (A) always gets higher allocation than Edge Card (B)")
    print("  • Small boosts favor conservative 1-card execution")
    print("  • Large boosts enable 2-card split with controlled risk")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
