"""
Detects arbitrage opportunities in Odds API responses.

Scans each game's bookmakers for the best available odds per side, then flags
games where the sum of implied probabilities (1/odds_a + 1/odds_b) falls below
1.0 — indicating a guaranteed profit is available across books. Only 2-way
(h2h) markets are evaluated.

Games are filtered to pre-game lines only: any game that has already started or
starts within MIN_LEAD_MINUTES is skipped to avoid live/volatile lines.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.odds_fetcher import american_to_decimal

# Minimum minutes before tipoff required to consider a game's lines stable
MIN_LEAD_MINUTES = 15


def find_arbs(sport: str, odds_json: list[dict]) -> list[dict]:
    """Scan a raw Odds API response for arbitrage opportunities.

    For each game, finds the best available decimal odds for each side across all
    bookmakers, then checks whether (1/odds_a + 1/odds_b) < 1.0. Only 2-way
    (h2h) markets are evaluated; games with more or fewer than two sides are skipped.

    Games that have already started or commence within MIN_LEAD_MINUTES are skipped
    to avoid live or volatile lines. Games with an unparseable commence_time are
    also skipped.

    Args:
        sport: Sport key string (e.g. "basketball_nba"), stored on each result.
        odds_json: Raw list of game dicts as returned by get_odds() or get_props().

    Returns:
        List of arb opportunity dicts. Each dict contains:
            sport, game, team_a, team_b, book_a, book_b,
            odds_a (american), odds_b (american), arb_pct, profit_pct,
            time_to_game (float, hours until tipoff), timestamp.
        Returns an empty list if odds_json is falsy or no arbs are found.
    """
    if not odds_json:
        return []

    opportunities = []
    now_utc = datetime.now(timezone.utc)
    timestamp = now_utc.strftime("%Y-%m-%d %H:%M:%S")

    for game in odds_json:
        # --- Pre-game filter: skip started or near-tipoff games ---
        commence_str = game.get("commence_time", "")
        try:
            commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue  # unparseable timestamp — skip

        minutes_to_game = (commence_dt - now_utc).total_seconds() / 60
        if minutes_to_game < MIN_LEAD_MINUTES:
            continue

        time_to_game = round(minutes_to_game / 60, 2)

        home_team = game.get("home_team")
        away_team = game.get("away_team")
        game_name = f"{away_team} @ {home_team}"

        # best_odds maps team name -> (best_decimal_odds, bookmaker_title)
        best_odds = {}

        for bookmaker in game.get("bookmakers", []):
            book_title = bookmaker.get("title")
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    team = outcome.get("name")
                    price = outcome.get("price")
                    if team is None or price is None:
                        continue
                    decimal = american_to_decimal(price)
                    if team not in best_odds or decimal > best_odds[team][0]:
                        best_odds[team] = (decimal, book_title, price)

        # Only evaluate 2-way markets (h2h)
        teams = list(best_odds.keys())
        if len(teams) != 2:
            continue

        team_a, team_b = teams[0], teams[1]
        dec_a, book_a, raw_a = best_odds[team_a]
        dec_b, book_b, raw_b = best_odds[team_b]

        arb_pct = (1 / dec_a) + (1 / dec_b)

        if arb_pct < 1.0:
            opportunities.append({
                "sport": sport,
                "game": game_name,
                "team_a": team_a,
                "team_b": team_b,
                "book_a": book_a,
                "book_b": book_b,
                "odds_a": raw_a,
                "odds_b": raw_b,
                "arb_pct": round(arb_pct, 6),
                "profit_pct": round((1 - arb_pct) * 100, 4),
                "time_to_game": time_to_game,
                "timestamp": timestamp,
            })

    return opportunities
