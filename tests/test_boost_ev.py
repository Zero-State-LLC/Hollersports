# FILE: tests/test_boost_ev.py
import unittest

from hollersports.engine.boost import (
    breakeven_win_rate_profit_boost,
    expected_value_units,
    BoostPolicy,
    CardSimResult,
    decide_boost_aware_two_card_system,
)

class TestBoostEV(unittest.TestCase):
    def test_breakeven_75pct(self):
        p = breakeven_win_rate_profit_boost(profit_boost_frac=0.75)
        # 1 / (2 + 0.75) = 0.363636...
        self.assertAlmostEqual(p, 0.36363636, places=6)

    def test_ev_positive_above_breakeven(self):
        ev = expected_value_units(p_win=0.55, profit_boost_frac=0.75)
        self.assertGreater(ev, 0.0)

    def test_decision_prefers_safe_when_boost_small(self):
        policy = BoostPolicy(boost_floor_to_expand=0.30)
        # With 10% boost, breakeven is ~47.6%, so card_a at 55% should pass
        card_a = CardSimResult("A_SAFE_3", ("a","b","c"), 0.55, 0.10, {"sim":"x"})
        card_b = CardSimResult("B_EDGE_4", ("a","b","c","d"), 0.52, 0.18, {"sim":"x"})

        # small boost: shouldn't allocate much to B even if allowed
        dec = decide_boost_aware_two_card_system(
            profit_boost_frac=0.10,
            card_a=card_a,
            card_b=card_b,
            policy=policy,
        )
        self.assertIn("A_SAFE_3", dec.allowed_cards)
        self.assertGreaterEqual(dec.stake_weights["A_SAFE_3"], dec.stake_weights["B_EDGE_4"])

    def test_decision_splits_when_boost_large(self):
        policy = BoostPolicy(boost_floor_to_split=0.50)
        card_a = CardSimResult("A_SAFE_3", ("a","b","c"), 0.41, 0.10, {"sim":"x"})
        card_b = CardSimResult("B_EDGE_4", ("a","b","c","d"), 0.28, 0.18, {"sim":"x"})

        dec = decide_boost_aware_two_card_system(
            profit_boost_frac=0.75,
            card_a=card_a,
            card_b=card_b,
            policy=policy,
        )
        self.assertIn("A_SAFE_3", dec.allowed_cards)
        if "B_EDGE_4" in dec.allowed_cards:
            self.assertGreater(dec.stake_weights["B_EDGE_4"], 0.0)

if __name__ == "__main__":
    unittest.main()
