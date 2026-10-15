"""
Entry point for arb-bot paper trading mode.

Runs an infinite polling loop: fetches game odds and player prop odds for all
configured sports, detects arbitrage opportunities above MIN_PROFIT_THRESHOLD at
books you hold accounts with, calculates realistic per-account stakes, places
each new arb as an open simulated bet (logged to paper_trades.csv), settles
bets once their game is over (logged to simulation_trades.csv), and prints a
formatted cycle summary to the terminal. Sleeps POLLING_INTERVAL seconds
between cycles.

A daemon thread runs alongside the polling loop and accepts typed commands from
stdin at any time (including during the sleep period between cycles). See _COMMANDS
for the full list of supported commands.
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from datetime import datetime

import config
from scrapers.odds_fetcher import get_odds, get_props
from engine.arb_detector import find_arbs
from engine.stake_calculator import calculate_realistic_stakes
from paper_trader.logger import log_opportunity, get_summary_stats, is_recent_duplicate
from paper_trader import account_manager
from paper_trader.simulator import simulate_arb, settle_due_bets, rebalance_check, session_summary

SEP = "━" * 49
REBALANCE_THRESHOLD = config.LOW_BALANCE_THRESHOLD

# ---------------------------------------------------------------------------
# Shared state — updated by the main polling loop, read by the command thread
# ---------------------------------------------------------------------------
_state_lock = threading.Lock()
_bot_state = {
    "cycle_count": 0,
    "total_arbs": 0,
    "simulated_profit": 0.0,
    "requests_remaining": None,
}


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _print_transfers(transfers: list[tuple[str, str, float]]) -> None:
    for src, dst, amount in transfers:
        print(f" 🔁 REBALANCE: moved ${amount:.2f} from {src} to {dst}")


def _execute_transfers(confirm: bool) -> None:
    """Top up every account below LOW_BALANCE_THRESHOLD to AUTO_REBALANCE_TARGET
    from the accounts with the most cash (see account_manager.auto_rebalance)."""
    accounts = account_manager.load_accounts()
    low = [a for a in accounts.values() if a["balance"] < REBALANCE_THRESHOLD]

    if not low:
        print(f"\n All accounts are at or above ${REBALANCE_THRESHOLD:.2f}. No transfers needed.")
        return

    if confirm:
        print(
            f"\n This will move funds between {len(low)} account(s). Confirm? (y/n): ",
            end="",
            flush=True,
        )
        try:
            answer = sys.stdin.readline().strip().lower()
        except Exception:
            answer = ""
        if answer != "y":
            print(" Transfer cancelled.")
            return

    _print_transfers(account_manager.auto_rebalance())
    print(" accounts.json saved.")


def _cmd_transfer() -> None:
    _execute_transfers(confirm=False)


def _cmd_balances() -> None:
    print()
    account_manager.get_account_summary()
    print()


def _cmd_summary() -> None:
    print()
    session_summary(account_manager)
    print()


def _cmd_rebalance() -> None:
    _execute_transfers(confirm=True)


def _cmd_status() -> None:
    with _state_lock:
        cycle = _bot_state["cycle_count"]
        total_arbs = _bot_state["total_arbs"]
        profit = _bot_state["simulated_profit"]
        remaining = _bot_state["requests_remaining"]

    remaining_str = str(remaining) if remaining is not None else "unknown"
    print(
        f"\n Cycle: {cycle}  |  Total arbs: {total_arbs}  |  "
        f"Settled profit this run: ${profit:.2f}  |  Requests remaining: {remaining_str}\n"
    )


def _cmd_help() -> None:
    print("""
 Available commands:
   transfer   — top up low accounts now (also automatic when AUTO_REBALANCE is on)
   balances   — print full account balance table
   summary    — print session summary
   rebalance  — execute transfers with confirmation prompt
   status     — show cycle, arbs found, profit, requests remaining
   help       — show this help message
""")


_COMMANDS = {
    "transfer": _cmd_transfer,
    "balances": _cmd_balances,
    "summary": _cmd_summary,
    "rebalance": _cmd_rebalance,
    "status": _cmd_status,
    "help": _cmd_help,
}


# ---------------------------------------------------------------------------
# Command listener thread
# ---------------------------------------------------------------------------

def _command_listener() -> None:
    """Daemon thread: read lines from stdin and dispatch to command handlers."""
    while True:
        try:
            line = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        cmd = line.strip().lower()
        if not cmd:
            continue
        handler = _COMMANDS.get(cmd)
        if handler:
            handler()
        else:
            print(" Unknown command. Type 'help' for available commands.")


def _process_arbs(sport: str, odds_json: list[dict]) -> tuple[list[dict], float]:
    """Run arb detection and stake calculation for one sport's odds response.

    Only books you hold an account with are considered. Filters out
    opportunities below MIN_PROFIT_THRESHOLD and ones already bet (same game,
    market, line and books, odds unchanged), calculates realistic stakes
    against current account balances, places each viable arb as an open bet,
    and logs it to paper_trades.csv.

    Args:
        sport: Sport key string, passed through to find_arbs().
        odds_json: Raw odds response from get_odds() or get_props().

    Returns:
        Tuple of (list of open-bet records placed, total expected profit of those bets).
    """
    results = []
    cycle_profit = 0.0
    for arb in find_arbs(sport, odds_json, allowed_books=account_manager.account_names()):
        # MIN_PROFIT_THRESHOLD is a raw percentage (e.g. 0.2 means 0.2%)
        if arb["profit_pct"] < config.MIN_PROFIT_THRESHOLD:
            if config.DEBUG:
                print(
                    f"  [DEBUG] PROFIT FILTER: {arb['game']} "
                    f"profit={arb['profit_pct']:.4f}% < threshold={config.MIN_PROFIT_THRESHOLD}%"
                )
            continue

        if is_recent_duplicate(arb):
            if config.DEBUG:
                print(f"  [DEBUG] ALREADY BET: {arb['game']} ({arb['market']}) — skipping")
            continue

        if config.AUTO_REBALANCE:
            # Top up a low book before sizing, as you would before placing the bet
            letters = "abc" if arb.get("market_type") == "3-way" else "ab"
            _print_transfers(account_manager.auto_rebalance(only=[arb[f"book_{l}"] for l in letters]))

        try:
            result = calculate_realistic_stakes(arb, account_manager)
        except ValueError as e:
            if config.DEBUG:
                print(f"  [DEBUG] BALANCE LOOKUP ERROR: {arb['game']} — {e}")
            continue

        if result is None:
            if config.DEBUG:
                bal_a = account_manager.get_balance(arb["book_a"]) if arb["book_a"] in account_manager.load_accounts() else "?"
                bal_b = account_manager.get_balance(arb["book_b"]) if arb["book_b"] in account_manager.load_accounts() else "?"
                print(
                    f"  [DEBUG] BALANCE REJECT: {arb['game']} — "
                    f"{arb['book_a']}=${bal_a} {arb['book_b']}=${bal_b} (need >$10 each)"
                )
            continue

        bet = simulate_arb(result, account_manager)
        if bet is None:
            if config.DEBUG:
                print(f"  [DEBUG] SIMULATE FAIL: {arb['game']} — place_bet returned False")
            continue

        # paper_trades.csv records the stakes actually placed, not a full-bankroll stake
        letters = "abc" if result.get("market_type") == "3-way" else "ab"
        log_row = {**result, "guaranteed_profit": result["realistic_profit"], "roi_pct": result["realistic_roi"]}
        for l in letters:
            log_row[f"stake_{l}"] = result[f"realistic_stake_{l}"]
        log_opportunity(log_row)

        cycle_profit += result["realistic_profit"]
        results.append(bet)
    return results, cycle_profit


def _run_cycle() -> None:
    """Settle finished bets, top up low accounts, then fetch odds, detect and place new arbs."""
    for trade in settle_due_bets(account_manager):
        with _state_lock:
            _bot_state["simulated_profit"] += trade["net_profit"]
        print(
            f"\n ✅ SETTLED: {trade['game']} ({trade['market']})\n"
            f"    Winner: {trade['winner']} at {trade['winning_book']}  |  "
            f"Net P/L: ${trade['net_profit']:+.2f}  |  "
            f"Total bankroll: ${trade['total_bankroll_after']:,.2f}"
        )

    if config.AUTO_REBALANCE:
        _print_transfers(account_manager.auto_rebalance())

    cycle_bets = []
    last_remaining = None

    for sport in config.SPORTS:
        data, remaining = get_odds(sport)
        last_remaining = remaining
        if data:
            print(f" {sport:<18} ✓  requests remaining: {remaining}")
            bets, _ = _process_arbs(sport, data)
            cycle_bets.extend(bets)
        else:
            print(f" {sport:<18} ✗  requests remaining: {remaining}")

    for sport in config.PROPS_SPORTS:
        data, remaining = get_props(sport)
        last_remaining = remaining
        if data:
            print(f" {sport:<18} ✓  requests remaining: {remaining}  [props]")
            bets, _ = _process_arbs(sport, data)
            cycle_bets.extend(bets)

    with _state_lock:
        _bot_state["total_arbs"] += len(cycle_bets)
        if last_remaining is not None:
            _bot_state["requests_remaining"] = last_remaining

    for bet in cycle_bets:
        legs = " vs ".join(f"{leg['book']} {leg['label']} (${leg['stake']:.2f})" for leg in bet["legs"])
        print(
            f"\n 🎯 ARB PLACED: {bet['game']} ({bet['market']})\n"
            f"    {legs}\n"
            f"    Expected profit: ${bet['expected_profit']:+.2f}  |  Settles after {bet['settle_at']} UTC"
        )

    stats = get_summary_stats()
    if stats:
        print(
            f"\n Total arbs: {stats['total']}  |  "
            f"Expected profit: ${stats['total_profit']:.2f}  |  "
            f"Avg ROI: {stats['avg_roi']:.2f}%"
        )


def run() -> None:
    """Start the arb bot in paper trading mode.

    Prints a startup banner and full account summary table, then loops forever:
    fetches odds, detects arbs, simulates realistic stakes against account
    balances, logs results, checks for low-balance accounts, and prints a
    session summary every 5 cycles.
    """
    print(SEP)
    print("        ARB BOT — PAPER TRADING MODE")
    print(SEP)
    print(f"  Min profit:        {config.MIN_PROFIT_THRESHOLD}%")
    print(f"  Regions/markets:   {config.REGIONS} / {config.MARKETS}")
    print(f"  Sports:            {', '.join(config.SPORTS)}")
    print(f"  Polling interval:  {config.POLLING_INTERVAL}s")
    print(SEP)
    print()

    if not config.API_KEY:
        print(" No API_KEY found. Add API_KEY=... to your .env file and start again.")
        sys.exit(1)

    # Initialize accounts (loads from accounts.json or creates fresh state)
    print(" ACCOUNT BALANCES ON STARTUP")
    print(SEP)
    account_manager.get_account_summary()
    print()

    # Start command listener in a daemon thread so it exits with the main process
    listener = threading.Thread(target=_command_listener, daemon=True, name="cmd-listener")
    listener.start()
    print(" Type 'help' for available commands.\n")

    cycle_count = 0

    while True:
        cycle_count += 1
        with _state_lock:
            _bot_state["cycle_count"] = cycle_count

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(SEP)
        print(f" CYCLE {cycle_count}  {timestamp}")
        print(SEP)

        try:
            _run_cycle()
        except Exception:
            # Keep the bot alive through a bad response or a bug in one cycle
            print(" ⚠️  Cycle failed with an error; continuing next cycle:")
            traceback.print_exc()

        # Flag any accounts running low
        print()
        rebalance_check(account_manager)

        # Full session summary every 5 cycles
        if cycle_count % 5 == 0:
            print()
            session_summary(account_manager)

        print()
        print(SEP)
        print(f" Sleeping {config.POLLING_INTERVAL}s...\n")
        time.sleep(config.POLLING_INTERVAL)


if __name__ == "__main__":
    run()
