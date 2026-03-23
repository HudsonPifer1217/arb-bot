"""
Unit tests for engine/arb_detector.py.

Verifies that find_arbs() correctly detects genuine arbitrage opportunities,
ignores non-arb games, returns the right number of results, identifies the
correct bookmakers, and computes the expected profit percentage.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.arb_detector import find_arbs

# ---------------------------------------------------------------------------
# Sample payload mimicking The Odds API v4 response format.
#
# Game 1 — ARB OPPORTUNITY:
#   Lakers +150 (DraftKings) → decimal 2.5   → implied 40.0%
#   Celtics +150 (FanDuel)   → decimal 2.5   → implied 40.0%
#   arb_pct = 0.80  →  profit_pct = 20.0%
#
# Game 2 — NO ARB:
#   Bulls -110 (DraftKings)  → decimal ~1.909 → implied ~52.4%
#   Heat  -110 (FanDuel)     → decimal ~1.909 → implied ~52.4%
#   arb_pct ≈ 1.047  →  no profit
# ---------------------------------------------------------------------------

SAMPLE_ODDS = [
    {
        "id": "game_001",
        "sport_key": "basketball_nba",
        "sport_title": "NBA",
        "commence_time": "2026-03-22T20:00:00Z",
        "home_team": "Boston Celtics",
        "away_team": "Los Angeles Lakers",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Los Angeles Lakers", "price": 150},
                            {"name": "Boston Celtics",     "price": -180},
                        ],
                    }
                ],
            },
            {
                "key": "fanduel",
                "title": "FanDuel",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Los Angeles Lakers", "price": -200},
                            {"name": "Boston Celtics",     "price": 150},
                        ],
                    }
                ],
            },
        ],
    },
    {
        "id": "game_002",
        "sport_key": "basketball_nba",
        "sport_title": "NBA",
        "commence_time": "2026-03-22T22:30:00Z",
        "home_team": "Miami Heat",
        "away_team": "Chicago Bulls",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Chicago Bulls", "price": -110},
                            {"name": "Miami Heat",    "price": -110},
                        ],
                    }
                ],
            },
            {
                "key": "fanduel",
                "title": "FanDuel",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Chicago Bulls", "price": -110},
                            {"name": "Miami Heat",    "price": -110},
                        ],
                    }
                ],
            },
        ],
    },
]


def run_tests():
    arbs = find_arbs("basketball_nba", SAMPLE_ODDS)

    # --- Test 1: arb opportunity was detected ---
    arb_games = [a["game"] for a in arbs]
    expected_game = "Los Angeles Lakers @ Boston Celtics"
    if any(expected_game in g for g in arb_games):
        print(f"PASS  Arb correctly detected: {expected_game}")
    else:
        print(f"FAIL  Expected arb not found for: {expected_game}")

    # --- Test 2: non-arb game was NOT flagged ---
    no_arb_game = "Chicago Bulls @ Miami Heat"
    if not any(no_arb_game in g for g in arb_games):
        print(f"PASS  Non-arb game correctly ignored: {no_arb_game}")
    else:
        print(f"FAIL  Non-arb game was incorrectly flagged: {no_arb_game}")

    # --- Test 3: exactly one opportunity returned ---
    if len(arbs) == 1:
        print(f"PASS  Exactly 1 arb opportunity returned")
    else:
        print(f"FAIL  Expected 1 opportunity, got {len(arbs)}")

    # --- Test 4: correct books and profit % ---
    if arbs:
        opp = arbs[0]
        books = {opp["book_a"], opp["book_b"]}
        if books == {"DraftKings", "FanDuel"}:
            print(f"PASS  Correct bookmakers identified: {books}")
        else:
            print(f"FAIL  Unexpected bookmakers: {books}")

        expected_profit = 20.0
        if abs(opp["profit_pct"] - expected_profit) < 0.01:
            print(f"PASS  Profit % correct: {opp['profit_pct']}%")
        else:
            print(f"FAIL  Expected profit {expected_profit}%, got {opp['profit_pct']}%")

        print(f"\nOpportunity detail: {opp}")


if __name__ == "__main__":
    run_tests()
