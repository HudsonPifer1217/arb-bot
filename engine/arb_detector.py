"""
Detects arbitrage opportunities in Odds API responses.

Scans each game's bookmakers for the best available odds per side of every
line, then flags lines where the sum of implied probabilities falls below
1.0 — indicating a guaranteed profit is available across books. Supports:
  - h2h (moneyline): 2-way, or 3-way home/draw/away for soccer
  - spreads: Team A -3.5 vs Team B +3.5 (same line, opposite sides)
  - totals: Over 220.5 vs Under 220.5 (same line)

Games are filtered to pre-game lines only: any game that has already started or
starts within MIN_LEAD_MINUTES is skipped to avoid live/volatile lines.

Lines are rejected when every leg comes from the same bookmaker (a book never
offers a real arb against itself; that is stale or bad data) and when the
profit exceeds MAX_REALISTIC_ROI.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scrapers.odds_fetcher import american_to_decimal

# Minimum minutes before tipoff required to consider a game's lines stable
MIN_LEAD_MINUTES = config.MIN_GAME_START_MINUTES

SUPPORTED_MARKETS = ("h2h", "spreads", "totals")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _is_stale(market: dict, bookmaker: dict, now_utc: datetime) -> bool:
    """True if the line is older than MAX_LINE_AGE_MINUTES (when that check is on)."""
    max_age = getattr(config, "MAX_LINE_AGE_MINUTES", None)
    if max_age is None:
        return False
    updated = _parse_time(market.get("last_update") or bookmaker.get("last_update"))
    if updated is None:
        return False
    return (now_utc - updated).total_seconds() / 60 > max_age


def _side_and_line(market_key: str, outcome: dict, home_team: str) -> tuple[str, float | None] | None:
    """Return (side label, line key) for an outcome, or None if it can't be grouped.

    Outcomes with the same line key are the complementary sides of one bet:
      h2h:     line None, sides are team names (and "Draw")
      totals:  line is the total, sides are "Over 220.5" / "Under 220.5"
      spreads: line is the spread from the home team's view, so
               Home -3.5 and Away +3.5 share line -3.5
    """
    name = outcome.get("name")
    if name is None:
        return None
    if market_key == "h2h":
        return name, None
    point = outcome.get("point")
    if point is None:
        return None
    if market_key == "totals":
        return f"{name} {point:g}", float(point)
    # spreads
    home_line = float(point) if name == home_team else -float(point)
    return f"{name} {point:+g}", home_line


def find_arbs(sport: str, odds_json: list[dict], allowed_books: set[str] | None = None) -> list[dict]:
    """Scan a raw Odds API response for arbitrage opportunities.

    Args:
        sport: Sport key string (e.g. "basketball_nba"), stored on each result.
        odds_json: Raw list of game dicts as returned by get_odds().
        allowed_books: If given, only bookmakers whose title is in this set are
            considered, so the best price on each side is one you can actually
            bet (you hold an account there). None considers every bookmaker.

    Returns:
        List of arb opportunity dicts. Each dict contains:
            sport, game, market, line, market_type ("2-way" / "3-way"),
            team_a, team_b (side labels; outcome_a/b/c for 3-way),
            book_a, book_b[, book_c], odds_a, odds_b[, odds_c] (american),
            arb_pct, profit_pct (percent), time_to_game (hours),
            commence_time (ISO UTC), timestamp (UTC "%Y-%m-%d %H:%M:%S").
        Returns an empty list if odds_json is falsy or no arbs are found.
    """
    if not odds_json:
        if config.DEBUG:
            print(f"  [DEBUG/{sport}] odds_json is empty or None — nothing to scan")
        return []

    opportunities = []
    now_utc = datetime.now(timezone.utc)
    timestamp = now_utc.strftime("%Y-%m-%d %H:%M:%S")

    total_games = len(odds_json)
    games_skipped_time = 0
    games_skipped_parse = 0
    lines_checked = 0
    lines_wrong_sides = 0
    rejected_by_roi = 0
    rejected_same_book = 0
    stale_lines = 0
    unlisted_books: set[str] = set()
    best_arb_pct = None
    best_arb_label = None

    for game in odds_json:
        # --- Pre-game filter: skip started or near-tipoff games ---
        commence_str = game.get("commence_time", "")
        commence_dt = _parse_time(commence_str)
        if commence_dt is None:
            games_skipped_parse += 1
            continue

        minutes_to_game = (commence_dt - now_utc).total_seconds() / 60
        if minutes_to_game < MIN_LEAD_MINUTES:
            games_skipped_time += 1
            if config.DEBUG and minutes_to_game >= 0:
                game_label = f"{game.get('away_team')} @ {game.get('home_team')}"
                print(f"  [DEBUG/{sport}] TIME FILTER: {game_label} starts in {minutes_to_game:.1f}m (need >{MIN_LEAD_MINUTES}m)")
            continue

        time_to_game = round(minutes_to_game / 60, 2)

        home_team = game.get("home_team")
        away_team = game.get("away_team")
        game_name = f"{away_team} @ {home_team}"

        # lines maps (market, line) -> {side label: (best_decimal_odds, bookmaker_title, american_price)}
        lines: dict[tuple[str, float | None], dict[str, tuple[float, str, float]]] = {}

        for bookmaker in game.get("bookmakers", []):
            book_title = bookmaker.get("title")
            if allowed_books is not None and book_title not in allowed_books:
                unlisted_books.add(book_title)
                continue
            for market in bookmaker.get("markets", []):
                market_key = market.get("key")
                if market_key not in SUPPORTED_MARKETS:
                    continue
                if _is_stale(market, bookmaker, now_utc):
                    stale_lines += 1
                    continue
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    grouped = _side_and_line(market_key, outcome, home_team)
                    if price is None or grouped is None:
                        continue
                    side, line = grouped
                    decimal = american_to_decimal(price)
                    sides = lines.setdefault((market_key, line), {})
                    if side not in sides or decimal > sides[side][0]:
                        sides[side] = (decimal, book_title, price)

        for (market_key, line), sides in lines.items():
            n_sides = len(sides)
            # 3 sides only make sense for a moneyline with a draw
            if n_sides != 2 and not (n_sides == 3 and market_key == "h2h"):
                lines_wrong_sides += 1
                if config.DEBUG:
                    print(f"  [DEBUG/{sport}] SKIP ({market_key} {line}): {game_name} — {n_sides} sides found")
                continue

            lines_checked += 1
            labels = list(sides.keys())
            legs = [sides[label] for label in labels]
            arb_pct = sum(1 / dec for dec, _, _ in legs)
            label = f"{game_name} [{market_key}{'' if line is None else f' {line:g}'}]"

            if best_arb_pct is None or arb_pct < best_arb_pct:
                best_arb_pct = arb_pct
                best_arb_label = label

            if config.DEBUG:
                gap_pct = (arb_pct - 1.0) * 100
                qualifier = "ARB" if arb_pct < 1.0 else f"no arb (gap {gap_pct:+.4f}%)"
                leg_str = " / ".join(f"{book} {raw:+}" for _, book, raw in legs)
                print(f"  [DEBUG/{sport}] {label}: {leg_str} | arb_pct={arb_pct:.6f} — {qualifier}")

            if arb_pct >= 1.0:
                continue

            if len({book for _, book, _ in legs}) == 1:
                rejected_same_book += 1
                if config.DEBUG:
                    print(f"  [DEBUG/{sport}] SAME-BOOK REJECT: {label} — every leg at {legs[0][1]}")
                continue

            profit_pct = (1 - arb_pct) * 100
            if profit_pct > config.MAX_REALISTIC_ROI * 100:
                rejected_by_roi += 1
                if config.DEBUG:
                    print(
                        f"  [DEBUG/{sport}] ROI SANITY REJECT: {label} "
                        f"profit={profit_pct:.2f}% > MAX_REALISTIC_ROI={config.MAX_REALISTIC_ROI*100:.0f}%"
                    )
                continue

            opp = {
                "sport": sport,
                "game": game_name,
                "market": market_key,
                "line": line,
                "market_type": f"{n_sides}-way",
                "arb_pct": round(arb_pct, 6),
                "profit_pct": round(profit_pct, 4),
                "time_to_game": time_to_game,
                "commence_time": commence_str,
                "timestamp": timestamp,
            }
            for letter, side, (_, book, raw) in zip("abc", labels, legs):
                opp[f"book_{letter}"] = book
                opp[f"odds_{letter}"] = raw
                opp[f"outcome_{letter}"] = side
            if n_sides == 2:
                opp["team_a"], opp["team_b"] = labels
            opportunities.append(opp)

    if config.DEBUG:
        print(
            f"  [DEBUG/{sport}] SUMMARY: games={total_games} | "
            f"time_filtered={games_skipped_time} | parse_err={games_skipped_parse} | "
            f"lines_checked={lines_checked} | wrong_sides={lines_wrong_sides} | "
            f"arbs_found={len(opportunities)} | roi_rejected={rejected_by_roi} | "
            f"same_book_rejected={rejected_same_book} | stale_lines={stale_lines}"
        )
        if unlisted_books:
            print(f"  [DEBUG/{sport}] Ignored books with no account: {', '.join(sorted(b for b in unlisted_books if b))}")
        if best_arb_pct is not None:
            gap = (best_arb_pct - 1.0) * 100
            print(
                f"  [DEBUG/{sport}] CLOSEST ARB: {best_arb_label} "
                f"arb_pct={best_arb_pct:.6f} (need <1.0, gap={gap:+.4f}%)"
            )
        else:
            print(f"  [DEBUG/{sport}] No lines were checked — cannot report closest arb")

    return opportunities
