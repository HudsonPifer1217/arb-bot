"""
CLI backtester for arb-bot paper trade logs.

Reads paper_trades.csv, filters rows within a user-supplied date range, and
computes gross profit, net profit after slippage, win rate, and daily P&L,
then prints a formatted ASCII report. A 0.5% slippage factor is applied to
both legs of each trade to model real-world execution friction.

Usage:
    python backtest/backtest.py --start 2026-01-01 --end 2026-03-31

Arguments:
    --start   Start date inclusive (YYYY-MM-DD)
    --end     End date inclusive (YYYY-MM-DD)
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper_trades.csv")

SLIPPAGE_RATE = 0.005        # 0.5% per bet (applied to both legs)
EXECUTION_WINDOW_SEC = 60    # assumed execution within this many seconds


def parse_args() -> argparse.Namespace:
    """Parse --start and --end command-line arguments.

    Returns:
        argparse.Namespace with attributes start (str) and end (str),
        both expected in YYYY-MM-DD format.
    """
    parser = argparse.ArgumentParser(description="Backtest arb-bot paper trades over a date range.")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end",   required=True, help="End date (YYYY-MM-DD)")
    return parser.parse_args()


def load_trades(start_dt: datetime, end_dt: datetime) -> list[dict]:
    """Load and filter trades from paper_trades.csv within a date range.

    Reads every row from the CSV, parses the timestamp, and returns only rows
    whose timestamp falls within [start_dt, end_dt] inclusive. Rows with
    unparseable timestamps are silently skipped. Exits with an error message
    if the CSV file does not exist.

    Args:
        start_dt: Inclusive start of the date range.
        end_dt: Inclusive end of the date range (should have time 23:59:59).

    Returns:
        List of trade dicts with keys: timestamp (datetime), date (date),
        game, sport, stake_a, stake_b, guaranteed_profit, roi_pct.
    """
    if not os.path.exists(CSV_PATH):
        print(f"Error: {CSV_PATH} not found. Run main.py first to generate trades.")
        sys.exit(1)

    trades = []
    with open(CSV_PATH, newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if start_dt <= ts <= end_dt:
                trades.append({
                    "timestamp": ts,
                    "date": ts.date(),
                    "game": row["game"],
                    "sport": row["sport"],
                    "stake_a": float(row["stake_a"]),
                    "stake_b": float(row["stake_b"]),
                    "guaranteed_profit": float(row["guaranteed_profit"]),
                    "roi_pct": float(row["roi_pct"]),
                })
    return trades


def apply_slippage(trade: dict) -> float:
    """Calculate net profit for a single trade after applying slippage.

    Slippage models the real-world cost of getting a slightly worse fill price
    than the quoted odds. It is charged as a percentage of total stake (both legs),
    reducing the guaranteed gross profit.

    Args:
        trade: A trade dict containing stake_a, stake_b, and guaranteed_profit.

    Returns:
        Net profit in USD after subtracting slippage cost from guaranteed_profit.
    """
    slippage_cost = (trade["stake_a"] + trade["stake_b"]) * SLIPPAGE_RATE
    return trade["guaranteed_profit"] - slippage_cost


def run_backtest(trades: list[dict]) -> dict | None:
    """Aggregate backtest statistics across all trades.

    Computes gross profit, net profit after slippage, win rate (trades that
    remain profitable after slippage), and per-day P&L. Identifies the best
    and worst performing days.

    Args:
        trades: List of trade dicts as returned by load_trades().

    Returns:
        Results dict containing: total_bets, wins, win_rate, gross_profit,
        net_profit, slippage_cost, daily (dict of date → net P&L),
        best_day, best_day_profit, worst_day, worst_day_profit.
        Returns None if trades is empty.
    """
    if not trades:
        return None

    gross_profit = sum(t["guaranteed_profit"] for t in trades)
    net_profits = [apply_slippage(t) for t in trades]
    net_profit = sum(net_profits)

    # A bet "wins" (stays profitable after slippage) if net profit > 0
    wins = sum(1 for p in net_profits if p > 0)
    win_rate = wins / len(trades) * 100

    # Daily P&L
    daily = {}
    for trade, net in zip(trades, net_profits):
        day = trade["date"]
        daily[day] = daily.get(day, 0.0) + net

    best_day  = max(daily, key=daily.get)
    worst_day = min(daily, key=daily.get)

    return {
        "total_bets": len(trades),
        "wins": wins,
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "slippage_cost": gross_profit - net_profit,
        "daily": daily,
        "best_day": best_day,
        "best_day_profit": daily[best_day],
        "worst_day": worst_day,
        "worst_day_profit": daily[worst_day],
    }


def print_report(start_dt: datetime, end_dt: datetime, results: dict) -> None:
    """Print a formatted backtest performance report to stdout.

    Displays period, slippage assumptions, total bets, win rate, gross/net
    profit, best/worst day, and an ASCII bar chart of daily P&L when more than
    one day is present.

    Args:
        start_dt: Start of the backtest period.
        end_dt: End of the backtest period.
        results: Results dict as returned by run_backtest().
    """
    sep = "─" * 48
    print(sep)
    print("  ARB-BOT BACKTEST REPORT")
    print(sep)
    print(f"  Period        : {start_dt.date()} → {end_dt.date()}")
    print(f"  Execution     : within {EXECUTION_WINDOW_SEC}s assumed")
    print(f"  Slippage rate : {SLIPPAGE_RATE * 100:.1f}% per leg")
    print(sep)
    print(f"  Total bets    : {results['total_bets']}")
    print(f"  Profitable    : {results['wins']}  ({results['win_rate']:.1f}% win rate)")
    print(sep)
    print(f"  Gross profit  : ${results['gross_profit']:>10.2f}")
    print(f"  Slippage cost : ${results['slippage_cost']:>10.2f}")
    print(f"  Net profit    : ${results['net_profit']:>10.2f}")
    print(sep)
    print(f"  Best day      : {results['best_day']}  (+${results['best_day_profit']:.2f})")
    print(f"  Worst day     : {results['worst_day']}  (${results['worst_day_profit']:.2f})")
    print(sep)

    if len(results["daily"]) > 1:
        print("\n  Daily breakdown:")
        for day in sorted(results["daily"]):
            pnl = results["daily"][day]
            bar = "█" * max(0, int(abs(pnl) / 5))
            sign = "+" if pnl >= 0 else "-"
            print(f"    {day}  {sign}${abs(pnl):6.2f}  {bar}")
        print()


def main() -> None:
    """Entry point for the backtest CLI.

    Parses --start and --end arguments, validates the date range, loads matching
    trades from paper_trades.csv, runs the backtest, and prints the report.
    Exits with a non-zero status code on invalid input or missing data.
    """
    args = parse_args()

    try:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
        end_dt   = datetime.strptime(args.end,   "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        print("Error: dates must be in YYYY-MM-DD format.")
        sys.exit(1)

    if start_dt > end_dt:
        print("Error: --start must be before --end.")
        sys.exit(1)

    trades = load_trades(start_dt, end_dt)

    if not trades:
        print(f"No trades found between {start_dt.date()} and {end_dt.date()}.")
        sys.exit(0)

    results = run_backtest(trades)
    print_report(start_dt, end_dt, results)


if __name__ == "__main__":
    main()
