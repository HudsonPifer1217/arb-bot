"""
Unit tests for engine/stake_calculator.py.

Verifies that calculate_stakes() produces legs that sum to the bankroll,
yields equal payouts on either outcome, computes the correct guaranteed profit
and ROI, and that profit equals payout minus bankroll.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.arb_detector import find_arbs
from engine.stake_calculator import calculate_stakes
from scrapers.odds_fetcher import american_to_decimal
from tests.test_arb_detector import SAMPLE_ODDS

BANKROLL = 1000.0
TOLERANCE = 0.01  # cents


FAILURES = []


def _fail(msg):
    FAILURES.append(msg)
    print(msg)


def run_tests():
    arbs = find_arbs("basketball_nba", SAMPLE_ODDS)
    assert arbs, "No arb opportunities found — cannot run stake tests."
    opp = arbs[0]

    result = calculate_stakes(opp, BANKROLL)

    stake_a = result["stake_a"]
    stake_b = result["stake_b"]
    guaranteed_profit = result["guaranteed_profit"]
    roi_pct = result["roi_pct"]

    # --- Test 1: stakes sum to bankroll ---
    total_staked = stake_a + stake_b
    if abs(total_staked - BANKROLL) < TOLERANCE:
        print(f"PASS  Stakes sum to bankroll: ${stake_a} + ${stake_b} = ${total_staked:.2f}")
    else:
        _fail(f"FAIL  Stakes don't sum to bankroll: ${total_staked:.2f} != ${BANKROLL}")

    # --- Test 2: payout is equal regardless of which team wins ---
    dec_a = american_to_decimal(opp["odds_a"])
    dec_b = american_to_decimal(opp["odds_b"])
    payout_if_a_wins = stake_a * dec_a
    payout_if_b_wins = stake_b * dec_b

    if abs(payout_if_a_wins - payout_if_b_wins) < TOLERANCE:
        print(f"PASS  Equal payout on either outcome: ${payout_if_a_wins:.2f}")
    else:
        _fail(f"FAIL  Payouts differ: ${payout_if_a_wins:.2f} vs ${payout_if_b_wins:.2f}")

    # --- Test 3: guaranteed profit matches expected ---
    # +150/+150, arb_pct=0.80 → profit = 1000/0.80 - 1000 = 250.00
    expected_profit = 250.00
    if abs(guaranteed_profit - expected_profit) < TOLERANCE:
        print(f"PASS  Guaranteed profit correct: ${guaranteed_profit}")
    else:
        _fail(f"FAIL  Expected profit ${expected_profit}, got ${guaranteed_profit}")

    # --- Test 4: profit equals payout minus bankroll ---
    if abs((payout_if_a_wins - BANKROLL) - guaranteed_profit) < TOLERANCE:
        print(f"PASS  Profit = payout - bankroll: ${payout_if_a_wins:.2f} - ${BANKROLL} = ${guaranteed_profit}")
    else:
        _fail(f"FAIL  Profit doesn't match payout - bankroll")

    # --- Test 5: ROI matches expected ---
    expected_roi = 25.0  # 250 / 1000 * 100
    if abs(roi_pct - expected_roi) < TOLERANCE:
        print(f"PASS  ROI correct: {roi_pct}%")
    else:
        _fail(f"FAIL  Expected ROI {expected_roi}%, got {roi_pct}%")

    # --- Breakdown ---
    print(f"""
Stake breakdown — {opp['game']}
  {opp['team_a']} ({opp['book_a']}) @ {opp['odds_a']:+d}  →  stake ${stake_a}
  {opp['team_b']} ({opp['book_b']}) @ {opp['odds_b']:+d}  →  stake ${stake_b}
  Total staked:        ${total_staked:.2f}
  Guaranteed profit:   ${guaranteed_profit}
  ROI:                 {roi_pct}%""")

    if FAILURES:
        raise AssertionError(f"{len(FAILURES)} check(s) failed: {FAILURES}")


def test_stake_calculator():
    """pytest entry point."""
    FAILURES.clear()
    run_tests()


if __name__ == "__main__":
    run_tests()
