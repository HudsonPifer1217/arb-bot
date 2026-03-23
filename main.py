"""
Entry point for arb-bot paper trading mode.

Runs an infinite polling loop: fetches game odds and player prop odds for all
configured sports, detects arbitrage opportunities above MIN_PROFIT_THRESHOLD,
calculates optimal stakes, logs each qualifying arb to paper_trades.csv, and
prints a formatted cycle summary to the terminal. Sleeps POLLING_INTERVAL
seconds between cycles.
"""

import time
from datetime import datetime

import config
from scrapers.odds_fetcher import get_odds, get_props
from engine.arb_detector import find_arbs
from engine.stake_calculator import calculate_stakes
from paper_trader.logger import log_opportunity, get_summary_stats

SEP = "━" * 49


def _process_arbs(sport: str, odds_json: list[dict]) -> list[dict]:
    """Run arb detection and stake calculation for one sport's odds response.

    Filters out opportunities below MIN_PROFIT_THRESHOLD, calculates stakes
    for qualifying arbs, and logs each one to paper_trades.csv.

    Args:
        sport: Sport key string, passed through to find_arbs().
        odds_json: Raw odds response from get_odds() or get_props().

    Returns:
        List of fully calculated arb dicts (output of calculate_stakes())
        that met the profit threshold.
    """
    results = []
    for arb in find_arbs(sport, odds_json):
        if arb["profit_pct"] < config.MIN_PROFIT_THRESHOLD * 100:
            continue
        result = calculate_stakes(arb, config.BANKROLL)
        log_opportunity(result)
        results.append(result)
    return results


def run() -> None:
    """Start the arb bot in paper trading mode.

    Prints a startup banner with current config, then loops forever:
    fetches game odds and player prop odds for all configured sports,
    runs arb detection, calculates optimal stakes for any opportunity above
    MIN_PROFIT_THRESHOLD, logs each qualifying arb to paper_trades.csv,
    prints a formatted cycle block with sport statuses and any arbs found,
    and sleeps for POLLING_INTERVAL seconds between cycles.
    """
    print(SEP)
    print("        ARB BOT — PAPER TRADING MODE")
    print(SEP)
    print(f"  Bankroll:          ${config.BANKROLL:,.2f}")
    print(f"  Min profit:        {config.MIN_PROFIT_THRESHOLD * 100:.2f}%")
    print(f"  Sports:            {', '.join(config.SPORTS)}")
    print(f"  Polling interval:  {config.POLLING_INTERVAL}s")
    print(SEP)
    print()

    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(SEP)
        print(f" CYCLE {timestamp}")
        print(SEP)

        cycle_arbs = []

        for sport in config.SPORTS:
            data, remaining = get_odds(sport)
            if data:
                print(f" {sport:<18} ✓  requests remaining: {remaining}")
                cycle_arbs.extend(_process_arbs(sport, data))
            else:
                print(f" {sport:<18} ✗  requests remaining: {remaining}")

        for sport in config.PROPS_SPORTS:
            data, remaining = get_props(sport)
            if data:
                print(f" {sport:<18} ✓  requests remaining: {remaining}  [props]")
                cycle_arbs.extend(_process_arbs(sport, data))

        for result in cycle_arbs:
            print(
                f"\n 🎯 ARB FOUND: {result['game']}\n"
                f"    {result['book_a']} vs {result['book_b']} | "
                f"Profit: {result['profit_pct']}% | ROI: {result['roi_pct']}%"
            )

        stats = get_summary_stats()
        if stats:
            print(
                f"\n Total arbs: {stats['total']}  |  "
                f"Simulated profit: ${stats['total_profit']:.2f}  |  "
                f"Avg ROI: {stats['avg_roi']:.2f}%"
            )

        print(SEP)
        print(f" Sleeping {config.POLLING_INTERVAL}s...\n")
        time.sleep(config.POLLING_INTERVAL)


if __name__ == "__main__":
    run()
