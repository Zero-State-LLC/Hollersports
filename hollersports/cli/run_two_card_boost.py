# FILE: hollersports/cli/run_two_card_boost.py
# Minimal CLI: takes a JSON payload with simulated sweep probs + boost, returns execution plan.

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

from hollersports.engine.presets import TwoCardPreset, run_boost_aware_execution

def _load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main(argv: List[str]) -> int:
    """
    Usage:
      python -m hollersports.cli.run_two_card_boost input.json

    input.json schema:
    {
      "boost_frac": 0.75,
      "preset": {
        "card_a_legs": ["<market_key>", "...", "..."],
        "card_b_legs": ["<market_key>", "...", "...", "..."]
      },
      "sim": {
        "p_sweep_a": 0.407,
        "p_sweep_b": 0.279,
        "corr_a": 0.12,
        "corr_b": 0.18,
        "provenance": {"slate_fp":"...", "sim_fp":"..."}
      }
    }
    """
    if len(argv) < 2:
        print("Usage: python -m hollersports.cli.run_two_card_boost input.json")
        return 2

    inp: Dict[str, Any] = _load(argv[1])

    preset = TwoCardPreset(
        card_a_id="A_SAFE_3",
        card_b_id="B_EDGE_4",
        card_a_legs=tuple(inp["preset"]["card_a_legs"]),
        card_b_legs=tuple(inp["preset"]["card_b_legs"]),
    )

    plan = run_boost_aware_execution(
        preset=preset,
        profit_boost_frac=float(inp["boost_frac"]),
        p_sweep_card_a=float(inp["sim"]["p_sweep_a"]),
        p_sweep_card_b=float(inp["sim"]["p_sweep_b"]),
        corr_proxy_a=float(inp["sim"]["corr_a"]),
        corr_proxy_b=float(inp["sim"]["corr_b"]),
        sim_provenance=dict(inp["sim"]["provenance"]),
    )

    print(json.dumps(plan, sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
