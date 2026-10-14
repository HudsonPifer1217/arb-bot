"""
Realistic paper-trading simulation on top of account_manager.

simulate_arb() places every leg of an arb against the account balances and
records it as an open bet. The money stays tied up until the game is over:
settle_due_bets() (called once per cycle) settles open bets whose
commence_time + SETTLE_AFTER_HOURS has passed, picks a random winning leg,
credits the winning book and appends a row to simulation_trades.csv.

All timestamps are UTC.
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

TRADES_FILE = os.path.join(os.path.dirname(__file__), "simulation_trades.csv")
PENDING_FILE = os.path.join(os.path.dirname(__file__), "pending_bets.json")

TS_FORMAT = "%Y-%m-%d %H:%M:%S"

_pending_lock = threading.RLock()

CSV_COLUMNS = [
    "timestamp",
    "placed_at",
    "game",
    "sport",
    "market",
    "line",
    "market_type",
    "book_a",
    "book_b",
    "book_c",
    "odds_a",
    "odds_b",
    "odds_c",
    "stake_a",
    "stake_b",
    "stake_c",
    "winner",
    "winning_book",
    "losing_book",
    "profit_on_winner",
    "loss_on_loser",
    "net_profit",
    "book_a_balance_after",
    "book_b_balance_after",
    "book_c_balance_after",
    "total_bankroll_after",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_csv_header() -> None:
    """Create simulation_trades.csv, or rewrite an older file to the current columns."""
    if not os.path.exists(TRADES_FILE):
        with open(TRADES_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_COLUMNS).writeheader()
        return
    with open(TRADES_FILE, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames == CSV_COLUMNS:
            return
        rows = list(reader)
    with open(TRADES_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})


def load_pending() -> list[dict]:
    with _pending_lock:
        if not os.path.exists(PENDING_FILE):
            return []
        with open(PENDING_FILE) as f:
            return json.load(f)


def _save_pending(pending: list[dict]) -> None:
    with _pending_lock:
        tmp = PENDING_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(pending, f, indent=2)
        os.replace(tmp, PENDING_FILE)


def open_stakes_total() -> float:
    """Money currently tied up in bets that haven't settled."""
    return round(sum(leg["stake"] for bet in load_pending() for leg in bet["legs"]), 2)


def total_bankroll(account_manager) -> float:
    """Account balances plus stakes on open bets."""
    accounts = account_manager.load_accounts()
    return round(sum(a["balance"] for a in accounts.values()) + open_stakes_total(), 2)


def _settle_time(arb: dict) -> datetime:
    commence = arb.get("commence_time")
    try:
        start = datetime.fromisoformat(commence.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        start = _now()
    return start + timedelta(hours=config.SETTLE_AFTER_HOURS)


def simulate_arb(arb: dict, account_manager) -> dict | None:
    """Place all legs of an arb and record it as an open bet.

    Expects arb to already contain realistic_stake_* fields as produced by
    calculate_realistic_stakes. If any leg can't be placed, the legs already
    placed are refunded (stake back, no winnings) and None is returned.

    Returns the open-bet record. It is settled later by settle_due_bets().
    """
    letters = "abc" if arb.get("market_type") == "3-way" else "ab"
    legs = []
    for l in letters:
        legs.append({
            "label": arb.get(f"outcome_{l}") or arb.get(f"team_{l}") or f"outcome_{l}",
            "book": arb[f"book_{l}"],
            "stake": arb[f"realistic_stake_{l}"],
            "odds": arb[f"odds_{l}"],
        })

    # Two legs can be at the same book (3-way arbs), so check each book can
    # cover its combined stake before placing anything.
    per_book: dict[str, float] = {}
    for leg in legs:
        per_book[leg["book"]] = per_book.get(leg["book"], 0.0) + leg["stake"]
    if any(account_manager.get_balance(b) < total for b, total in per_book.items()):
        return None

    placed = []
    for leg in legs:
        if not account_manager.place_bet(leg["book"], leg["stake"], leg["odds"]):
            for done in placed:
                account_manager.refund_bet(done["book"], done["stake"])
            return None
        placed.append(leg)

    bet = {
        "id": uuid.uuid4().hex[:12],
        "placed_at": _now().strftime(TS_FORMAT),
        "settle_at": _settle_time(arb).strftime(TS_FORMAT),
        "game": arb.get("game", ""),
        "sport": arb.get("sport", ""),
        "market": arb.get("market", "h2h"),
        "line": arb.get("line"),
        "market_type": arb.get("market_type", "2-way"),
        "expected_profit": arb.get("realistic_profit"),
        "legs": legs,
    }
    with _pending_lock:
        pending = load_pending()
        pending.append(bet)
        _save_pending(pending)
    return bet


def _settle_one(bet: dict, account_manager) -> dict:
    legs = bet["legs"]
    winner_idx = random.randrange(len(legs))

    results = []
    for i, leg in enumerate(legs):
        results.append(account_manager.settle_bet(leg["book"], leg["stake"], leg["odds"], won=(i == winner_idx)))

    winning = legs[winner_idx]
    losing = [leg for i, leg in enumerate(legs) if i != winner_idx]
    net_profit = round(sum(results), 2)

    trade = {
        "timestamp": _now().strftime(TS_FORMAT),
        "placed_at": bet["placed_at"],
        "game": bet["game"],
        "sport": bet["sport"],
        "market": bet["market"],
        "line": "" if bet["line"] is None else bet["line"],
        "market_type": bet["market_type"],
        "winner": winning["label"],
        "winning_book": winning["book"],
        "losing_book": "/".join(leg["book"] for leg in losing),
        "profit_on_winner": results[winner_idx],
        "loss_on_loser": round(sum(r for i, r in enumerate(results) if i != winner_idx), 2),
        "net_profit": net_profit,
    }
    for l, leg in zip("abc", legs):
        trade[f"book_{l}"] = leg["book"]
        trade[f"odds_{l}"] = leg["odds"]
        trade[f"stake_{l}"] = leg["stake"]
        trade[f"book_{l}_balance_after"] = account_manager.get_balance(leg["book"])
    return trade


def settle_due_bets(account_manager, now: datetime | None = None) -> list[dict]:
    """Settle every open bet whose settle_at time has passed. Returns the settled trades."""
    now = now or _now()
    settled = []
    with _pending_lock:
        pending = load_pending()
        still_open = []
        for bet in pending:
            settle_at = datetime.strptime(bet["settle_at"], TS_FORMAT).replace(tzinfo=timezone.utc)
            if settle_at <= now:
                settled.append(_settle_one(bet, account_manager))
            else:
                still_open.append(bet)
        if settled:
            _save_pending(still_open)
            _ensure_csv_header()
            bankroll_after = total_bankroll(account_manager)
            with open(TRADES_FILE, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                for trade in settled:
                    trade["total_bankroll_after"] = bankroll_after
                    writer.writerow({col: trade.get(col, "") for col in CSV_COLUMNS})
    return settled


def rebalance_check(account_manager, threshold: float = config.LOW_BALANCE_THRESHOLD) -> None:
    """Print rebalance suggestions for accounts below the threshold."""
    accounts = account_manager.load_accounts()
    low = [a for a in accounts.values() if a["balance"] < threshold]
    if not low:
        print(f"All accounts are above the ${threshold:.2f} threshold.")
        return

    # Highest-balance account is the suggested donor
    high = max(accounts.values(), key=lambda a: a["balance"])

    for acct in low:
        needed = round(threshold - acct["balance"], 2)
        surplus = round(high["balance"] - threshold, 2)
        if surplus <= 0:
            print(
                f"⚠️  {acct['name']} low (${acct['balance']:.2f}). "
                f"No accounts with sufficient surplus to top up."
            )
            continue
        transfer = min(needed, surplus)
        print(
            f"⚠️  {acct['name']} low (${acct['balance']:.2f}). "
            f"Consider transferring ${transfer:.2f} from {high['name']} "
            f"(balance: ${high['balance']:.2f})"
        )


def session_summary(account_manager) -> None:
    """Print a high-level summary of the current simulation session."""
    accounts = account_manager.load_accounts()
    acct_list = list(accounts.values())

    starting = account_manager.starting_bankroll(accounts)
    open_stakes = open_stakes_total()
    current_bankroll = round(sum(a["balance"] for a in acct_list) + open_stakes, 2)
    net = round(current_bankroll - starting, 2)
    total_bets = sum(a["bet_count"] for a in acct_list)
    needs_rebalance = sum(1 for a in acct_list if a["balance"] < config.LOW_BALANCE_THRESHOLD)

    best = max(acct_list, key=account_manager.net_pl)
    worst = min(acct_list, key=account_manager.net_pl)

    net_sign = "+" if net >= 0 else ""
    best_net = account_manager.net_pl(best)
    worst_net = account_manager.net_pl(worst)
    best_sign = "+" if best_net >= 0 else ""
    worst_sign = "+" if worst_net >= 0 else ""

    print("=" * 44)
    print("         SIMULATION SESSION SUMMARY")
    print("=" * 44)
    print(f"  Starting bankroll:        ${starting:,.2f}")
    print(f"  Current bankroll:         ${current_bankroll:,.2f}")
    print(f"    tied up in open bets:   ${open_stakes:,.2f}")
    print(f"  Net profit/loss:          {net_sign}${net:,.2f}")
    print(f"  Total bets placed:        {total_bets}")
    print(f"  Accounts needing rebal.:  {needs_rebalance}")
    print(f"  Best performing account:  {best['name']} ({best_sign}${best_net:.2f})")
    print(f"  Worst performing account: {worst['name']} ({worst_sign}${worst_net:.2f})")
    print("=" * 44)
