"""
Fetches game odds and player prop odds from The Odds API (v4).

Provides get_odds() for h2h/spreads/totals markets and get_props() for player
prop markets. Both functions return (data, requests_remaining) and handle 401,
422, 429, and timeout errors without raising exceptions. Also exposes
american_to_decimal() for converting odds format, shared by engine modules.
"""

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

    requests_remaining = response.headers.get("x-requests-remaining", "?")

    if response.status_code == 200:
        return response.json(), requests_remaining
    elif response.status_code == 401:
        print(f"  [{sport}] Error 401: Invalid API key.")
    elif response.status_code == 429:
        print(f"  [{sport}] Error 429: Rate limit hit.")
    else:
        print(f"  [{sport}] Error {response.status_code}: Unexpected response.")
    return None, requests_remaining

def get_props(sport: str) -> tuple[list[dict] | None, str]:
    """Fetch player prop odds for a sport from The Odds API.

    Identical to get_odds() but uses PROP_MARKETS from config instead of MARKETS.
    HTTP 422 (market not available on current plan) is silently swallowed so it
    does not clutter the terminal. Other errors are printed. Callers are
    responsible for output formatting.

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

    requests_remaining = response.headers.get("x-requests-remaining", "?")

    if response.status_code == 200:
        return response.json(), requests_remaining
    elif response.status_code == 401:
        print(f"  [PROPS/{sport}] Error 401: Invalid API key.")
    elif response.status_code == 422:
        pass  # market not available on current plan — suppress silently
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
