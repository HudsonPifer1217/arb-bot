"""
Calculates optimal stake sizes for arbitrage opportunities.

Given an arb opportunity dict and a bankroll, sizes each leg so that both
outcomes produce an identical payout, guaranteeing equal profit regardless of
result. Stakes always sum to exactly the bankroll.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
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


def calculate_realistic_stakes(arb: dict, account_manager) -> dict | None:
    """Calculate stakes constrained by real account balances.

    Looks up the current balance at each leg's book, caps the total staked at
    each book at config.MAX_STAKE_PCT of that account's balance (legs at the
    same book share one cap), then solves for the largest
    equal-payout bet that fits within every cap. Works for 2-way and 3-way arbs.
    If any account has less than $10, returns None.

    Args:
        arb: Arb opportunity dict containing at minimum:
            book_a, book_b, odds_a, odds_b, arb_pct (plus book_c, odds_c for 3-way).
        account_manager: Module (or object) exposing get_balance(bookmaker).

    Returns:
        A new dict merging all fields from arb with added keys:
            realistic_stake_a, realistic_stake_b[, realistic_stake_c] (float)
            realistic_profit (float): Worst-case profit at these rounded stakes.
            realistic_roi (float): ROI as a percentage of total staked.
            constrained_by (str): Name of the account that limited the stakes.
        Returns None if any balance is below $10.
    """
    letters = "abc" if arb.get("market_type") == "3-way" else "ab"
    books = [arb[f"book_{l}"] for l in letters]
    balances = [account_manager.get_balance(b) for b in books]
    if any(bal < 10.0 for bal in balances):
        return None

    decs = [american_to_decimal(arb[f"odds_{l}"]) for l in letters]
    arb_pct = arb["arb_pct"]

    # Stake per $1 of total bankroll on each leg; scale up to the largest
    # bankroll whose legs all fit within their caps. Legs at the same book share
    # one cap, so their units are combined before applying MAX_STAKE_PCT.
    units = [(1 / d) / arb_pct for d in decs]
    book_units: dict[str, float] = {}
    book_balance: dict[str, float] = {}
    for b, bal, u in zip(books, balances, units):
        book_units[b] = book_units.get(b, 0.0) + u
        book_balance[b] = bal
    max_bankrolls = {b: book_balance[b] * config.MAX_STAKE_PCT / book_units[b] for b in book_units}
    constrained_by = min(max_bankrolls, key=max_bankrolls.get)
    bankroll = max_bankrolls[constrained_by]

    stakes = [round(bankroll * u, 2) for u in units]
    total_staked = round(sum(stakes), 2)
    # Rounding cents can make the payouts differ slightly; report the worst case.
    payouts = [round(st * d, 2) for st, d in zip(stakes, decs)]
    realistic_profit = round(min(payouts) - total_staked, 2)
    realistic_roi = round((realistic_profit / total_staked) * 100, 4) if total_staked else 0.0

    result = {**arb}
    for l, st in zip(letters, stakes):
        result[f"realistic_stake_{l}"] = st
    result.update({
        "realistic_profit": realistic_profit,
        "realistic_roi": realistic_roi,
        "constrained_by": constrained_by,
    })
    return result
