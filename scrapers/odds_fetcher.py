"""
Fetches game odds and player prop odds from The Odds API (v4).

Provides get_odds() for h2h/spreads/totals markets and get_props() for player
prop markets. Both functions return (data, requests_remaining) and handle 401,
422, 429, and timeout errors without raising exceptions. Also exposes
american_to_decimal() for converting odds format, shared by engine modules.

Each game dict in the returned list includes a commence_time field (UTC ISO 8601,
e.g. "2026-03-22T20:00:00Z") that downstream consumers use to filter out games
that have already started or are too close to tipoff.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import config

def american_to_decimal(odds: int | float) -> float:
    """Convert American odds to decimal odds.

    Args:
        odds: American odds value (e.g. +150 or -110).

    Returns:
        Equivalent decimal odds (e.g. 2.5 or 1.909).
    """
    if odds > 0:
        return (odds / 100) + 1
    else:
        return (100 / abs(odds)) + 1

def get_odds(sport: str) -> tuple[list[dict] | None, str]:
    """Fetch game odds for a sport from The Odds API.

    Calls the /v4/sports/{sport}/odds/ endpoint using the markets and regions
    defined in config. Prints an error message on non-200 responses but does
    not print status lines — callers are responsible for output formatting.

    Args:
        sport: Sport key as defined by The Odds API (e.g. "basketball_nba").

    Returns:
        A tuple of (data, requests_remaining) where data is the parsed JSON
        list of game dicts (or None on error) and requests_remaining is the
        value of the x-requests-remaining header (or "?" on timeout).
    """
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": config.API_KEY,
        "regions": config.REGIONS,
        "markets": config.MARKETS,
        "oddsFormat": config.ODDS_FORMAT,
    }
    try:
        response = requests.get(url, params=params, timeout=10)
    except requests.exceptions.Timeout:
        print(f"  [{sport}] Network timeout after 10 seconds.")
        return None, "?"
    except requests.exceptions.RequestException as e:
        print(f"  [{sport}] Network error: {e.__class__.__name__}")
        return None, "?"

    requests_remaining = response.headers.get("x-requests-remaining", "?")

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError:
            print(f"  [{sport}] Response was not valid JSON.")
            return None, requests_remaining
        if config.DEBUG:
            books_per_game = [len(g.get("bookmakers", [])) for g in data]
            avg_books = sum(books_per_game) / len(books_per_game) if books_per_game else 0
            print(
                f"  [DEBUG/{sport}] games: {len(data)} | "
                f"bookmakers/game: min={min(books_per_game, default=0)} "
                f"max={max(books_per_game, default=0)} "
                f"avg={avg_books:.1f}"
            )
            if data:
                g = data[0]
                book_titles = [b.get("title") for b in g.get("bookmakers", [])]
                print(
                    f"  [DEBUG/{sport}] sample game: "
                    f"{g.get('away_team')} @ {g.get('home_team')} "
                    f"({g.get('commence_time')}) | "
                    f"books: {book_titles}"
                )
        return data, requests_remaining
    elif response.status_code == 401:
        print(f"  [{sport}] Error 401: Invalid API key.")
    elif response.status_code == 429:
        print(f"  [{sport}] Error 429: Rate limit hit.")
    else:
        print(f"  [{sport}] Error {response.status_code}: Unexpected response.")
    return None, requests_remaining

def get_props(sport: str) -> tuple[list[dict] | None, str]:
    """Fetch player prop odds for a sport from The Odds API.

    NOTE: The Odds API only serves player props from the per-event endpoint
    (/v4/sports/{sport}/events/{event_id}/odds), one call per game. This
    function calls the bulk /odds endpoint, which answers 422 for prop markets,
    so it never returns data. config.PROPS_SPORTS is empty for that reason.
    The arb detector also only understands h2h, spreads and totals.

    Args:
        sport: Sport key as defined by The Odds API (e.g. "basketball_nba").

    Returns:
        A tuple of (data, requests_remaining) where data is the parsed JSON
        list of game dicts (or None on error) and requests_remaining is the
        value of the x-requests-remaining header (or "?" on timeout).
    """
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": config.API_KEY,
        "regions": config.REGIONS,
        "markets": config.PROP_MARKETS,
        "oddsFormat": config.ODDS_FORMAT,
    }
    try:
        response = requests.get(url, params=params, timeout=10)
    except requests.exceptions.Timeout:
        print(f"  [PROPS/{sport}] Network timeout after 10 seconds.")
        return None, "?"
    except requests.exceptions.RequestException as e:
        print(f"  [PROPS/{sport}] Network error: {e.__class__.__name__}")
        return None, "?"

    requests_remaining = response.headers.get("x-requests-remaining", "?")

    if response.status_code == 200:
        return response.json(), requests_remaining
    elif response.status_code == 401:
        print(f"  [PROPS/{sport}] Error 401: Invalid API key.")
    elif response.status_code == 422:
        print(f"  [PROPS/{sport}] Error 422: props are not served by the bulk /odds endpoint.")
    elif response.status_code == 429:
        print(f"  [PROPS/{sport}] Error 429: Rate limit hit.")
    else:
        print(f"  [PROPS/{sport}] Error {response.status_code}: Unexpected response.")
    return None, requests_remaining


def run_loop() -> None:
    """Poll game odds and prop odds for all configured sports in an infinite loop.

    Calls get_odds() for each sport in config.SPORTS and get_props() for each
    sport in config.PROPS_SPORTS, then sleeps for config.POLLING_INTERVAL seconds
    before repeating. Intended for standalone use when running odds_fetcher directly.
    """
    while True:
        for sport in config.SPORTS:
            get_odds(sport)
        for sport in config.PROPS_SPORTS:
            get_props(sport)
        print(f" Sleeping {config.POLLING_INTERVAL}s...")
        time.sleep(config.POLLING_INTERVAL)

if __name__ == "__main__":
    run_loop()
