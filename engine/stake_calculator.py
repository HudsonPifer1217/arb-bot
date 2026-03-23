"""
Calculates optimal stake sizes for arbitrage opportunities.

Given an arb opportunity dict and a bankroll, sizes each leg so that both
outcomes produce an identical payout, guaranteeing equal profit regardless of
result. Stakes always sum to exactly the bankroll.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.odds_fetcher import american_to_decimal


def calculate_stakes(opportunity: dict, bankroll: float) -> dict:
    """Calculate optimal stakes for both legs of an arbitrage opportunity.

    Stakes are sized so that both legs produce an identical payout
    (bankroll / arb_pct), guaranteeing the same profit regardless of outcome.
    Formula: stake = bankroll * (1 / decimal_odds) / arb_pct.
    The two stakes always sum to exactly the bankroll.

    Args:
        opportunity: Arb opportunity dict as returned by find_arbs(), containing
            at minimum: odds_a, odds_b (american), and arb_pct.
        bankroll: Total amount to allocate across both legs, in USD.

    Returns:
        A new dict merging all fields from opportunity with four added keys:
            stake_a (float): Dollar amount to bet on team_a.
            stake_b (float): Dollar amount to bet on team_b.
            guaranteed_profit (float): Profit in USD regardless of outcome.
            roi_pct (float): Return on investment as a percentage of bankroll.
    """
    dec_a = american_to_decimal(opportunity["odds_a"])
    dec_b = american_to_decimal(opportunity["odds_b"])
    arb_pct = opportunity["arb_pct"]

    stake_a = bankroll * (1 / dec_a) / arb_pct
    stake_b = bankroll * (1 / dec_b) / arb_pct

    # Both legs pay out bankroll / arb_pct; total staked equals bankroll
    guaranteed_profit = (bankroll / arb_pct) - bankroll
    roi_pct = (guaranteed_profit / bankroll) * 100

    return {
        **opportunity,
        "stake_a": round(stake_a, 2),
        "stake_b": round(stake_b, 2),
        "guaranteed_profit": round(guaranteed_profit, 2),
        "roi_pct": round(roi_pct, 4),
    }
