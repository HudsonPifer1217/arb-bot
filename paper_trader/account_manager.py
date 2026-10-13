"""
Simulated sportsbook accounts, persisted to accounts.json.

Each account tracks its balance plus lifetime stats. Money moved between your
own accounts with transfer_funds() is recorded as transferred_in/out, not as a
deposit, so per-account P/L and the total starting bankroll stay correct.

All read-modify-write operations hold a lock, because main.py's command thread
(transfer/rebalance) and the polling loop both change accounts.json.
"""

from __future__ import annotations

import json
import os
import sys
import threading

from tabulate import tabulate

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

_lock = threading.RLock()

ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), "accounts.json")

SPORTSBOOKS = [
    "DraftKings",
    "FanDuel",
    "BetMGM",
    "Caesars",
    "PointsBet",
    "BetRivers",
    "Bovada",
    "MyBookie.ag",
    "BetOnline.ag",
    "Unibet",
    "WynnBET",
    "Barstool",
    "SI Sportsbook",
    "Betway",
    "TwinSpires",
    "Hard Rock Bet",
    "Fanatics",
    "ESPN BET",
    "Circa Sports",
    "BetUS",
    "bet365",           
    "SuperBook",        
    "Fliff",            
    "Bally Bet",
    "Pinnacle"        
]

DEFAULT_BALANCE = config.STARTING_BALANCE_PER_ACCOUNT


def _default_account(name: str) -> dict:
    return {
        "name": name,
        "balance": DEFAULT_BALANCE,
        "starting_balance": DEFAULT_BALANCE,
        "total_deposited": DEFAULT_BALANCE,
        "transferred_in": 0.0,
        "transferred_out": 0.0,
        "total_wagered": 0.0,
        "total_won": 0.0,
        "total_lost": 0.0,
        "bet_count": 0,
        "status": "active",
    }


def load_accounts() -> dict:
    with _lock:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, "r") as f:
                data = json.load(f)
            # Add any new sportsbooks not yet in the saved file
            for name in SPORTSBOOKS:
                if name not in data:
                    data[name] = _default_account(name)
            for acct in data.values():
                # Files written before these fields existed: every account started at the default
                acct.setdefault("starting_balance", DEFAULT_BALANCE)
                acct.setdefault("transferred_in", 0.0)
                acct.setdefault("transferred_out", 0.0)
            return data
        return {name: _default_account(name) for name in SPORTSBOOKS}


def save_accounts(accounts: dict) -> None:
    with _lock:
        tmp = ACCOUNTS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(accounts, f, indent=2)
        os.replace(tmp, ACCOUNTS_FILE)


def account_names() -> set[str]:
    """Titles of every account, for filtering odds to books you can bet at."""
    return set(load_accounts().keys())


def starting_bankroll(accounts: dict | None = None) -> float:
    """Total real money put in: every account's starting balance plus external deposits."""
    accounts = accounts if accounts is not None else load_accounts()
    return round(sum(a["total_deposited"] for a in accounts.values()), 2)


def net_pl(acct: dict) -> float:
    """Betting profit/loss for one account, excluding money moved between your own accounts."""
    return round(acct["balance"] - acct["total_deposited"] - acct.get("transferred_in", 0.0) + acct.get("transferred_out", 0.0), 2)


def _resolve_name(bookmaker: str, accounts: dict) -> str | None:
    if bookmaker in accounts:
        return bookmaker
    lower = bookmaker.lower()
    for name in accounts:
        if name.lower() == lower:
            return name
    return None


def get_balance(bookmaker: str) -> float:
    accounts = load_accounts()
    key = _resolve_name(bookmaker, accounts)
    if key is None:
        raise ValueError(f"Unknown bookmaker: {bookmaker}")
    return accounts[key]["balance"]


def _place_bet_unlocked(bookmaker: str, stake: float, odds: float) -> bool:
    """
    Deduct stake from bookmaker balance.
    odds: American format (e.g. -110, +150).
    Returns False if insufficient funds or account not active.
    """
    accounts = load_accounts()
    key = _resolve_name(bookmaker, accounts)
    if key is None:
        raise ValueError(f"Unknown bookmaker: {bookmaker}")
    acct = accounts[key]
    if acct["status"] != "active":
        print(f"[!] {key} account is not active.")
        return False
    if acct["balance"] < stake:
        print(f"[!] Insufficient funds at {key}: ${acct['balance']:.2f} < ${stake:.2f}")
        return False
    acct["balance"] -= stake
    acct["balance"] = round(acct["balance"], 2)
    acct["total_wagered"] = round(acct["total_wagered"] + stake, 2)
    acct["bet_count"] += 1
    save_accounts(accounts)
    return True


def _settle_bet_unlocked(bookmaker: str, stake: float, odds: float, won: bool) -> float:
    """
    Settle a previously placed bet.
    Adds winnings back to balance if won; records loss otherwise.
    Returns profit (positive) or loss (negative, as -stake).
    """
    accounts = load_accounts()
    key = _resolve_name(bookmaker, accounts)
    if key is None:
        raise ValueError(f"Unknown bookmaker: {bookmaker}")
    acct = accounts[key]

    if odds >= 0:
        profit = round(stake * (odds / 100), 2)
    else:
        profit = round(stake * (100 / abs(odds)), 2)

    if won:
        payout = round(stake + profit, 2)
        acct["balance"] = round(acct["balance"] + payout, 2)
        acct["total_won"] = round(acct["total_won"] + profit, 2)
        result = profit
    else:
        acct["total_lost"] = round(acct["total_lost"] + stake, 2)
        result = -stake

    save_accounts(accounts)
    return result


def place_bet(bookmaker: str, stake: float, odds: float) -> bool:
    """Deduct stake from bookmaker balance. Returns False if insufficient funds or account not active."""
    with _lock:
        return _place_bet_unlocked(bookmaker, stake, odds)


def settle_bet(bookmaker: str, stake: float, odds: float, won: bool) -> float:
    """Settle a previously placed bet. Returns profit (positive) or loss (-stake)."""
    with _lock:
        return _settle_bet_unlocked(bookmaker, stake, odds, won)


def refund_bet(bookmaker: str, stake: float) -> None:
    """Undo a placed bet that never went through (e.g. the other leg failed).

    Returns the stake only and reverses the bet's effect on the stats.
    """
    with _lock:
        accounts = load_accounts()
        key = _resolve_name(bookmaker, accounts)
        if key is None:
            raise ValueError(f"Unknown bookmaker: {bookmaker}")
        acct = accounts[key]
        acct["balance"] = round(acct["balance"] + stake, 2)
        acct["total_wagered"] = round(acct["total_wagered"] - stake, 2)
        acct["bet_count"] -= 1
        save_accounts(accounts)


def transfer_funds(from_book: str, to_book: str, amount: float) -> None:
    """Simulate rebalancing by moving funds between accounts."""
    with _lock:
        _transfer_funds_unlocked(from_book, to_book, amount)


def get_account_summary() -> None:
    accounts = load_accounts()
    rows = []
    for acct in accounts.values():
        net = net_pl(acct)
        rows.append([
            acct["name"],
            f"${acct['balance']:.2f}",
            f"${acct['total_deposited']:.2f}",
            f"${acct['total_wagered']:.2f}",
            f"${acct['total_won']:.2f}",
            f"${acct['total_lost']:.2f}",
            acct["bet_count"],
            f"{'+'if net >= 0 else ''}{net:.2f}",
            acct["status"],
        ])
    headers = ["Bookmaker", "Balance", "Deposited", "Wagered", "Won", "Lost", "Bets", "Net P/L", "Status"]
    print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))


def flag_low_balance(threshold: float = config.LOW_BALANCE_THRESHOLD) -> None:
    accounts = load_accounts()
    flagged = [acct for acct in accounts.values() if acct["balance"] < threshold]
    if not flagged:
        print(f"All accounts are above the ${threshold:.2f} threshold.")
        return
    print(f"WARNING: The following accounts are below ${threshold:.2f}:")
    for acct in flagged:
        print(f"  - {acct['name']}: ${acct['balance']:.2f}")


def _transfer_funds_unlocked(from_book: str, to_book: str, amount: float) -> None:
    """Simulate rebalancing by moving funds between accounts."""
    accounts = load_accounts()
    from_key = _resolve_name(from_book, accounts)
    to_key = _resolve_name(to_book, accounts)
    if from_key is None:
        raise ValueError(f"Unknown bookmaker: {from_book}")
    if to_key is None:
        raise ValueError(f"Unknown bookmaker: {to_book}")
    if accounts[from_key]["balance"] < amount:
        print(
            f"[!] Insufficient funds in {from_key} to transfer ${amount:.2f} "
            f"(available: ${accounts[from_key]['balance']:.2f})"
        )
        return
    accounts[from_key]["balance"] = round(accounts[from_key]["balance"] - amount, 2)
    accounts[to_key]["balance"] = round(accounts[to_key]["balance"] + amount, 2)
    accounts[from_key]["transferred_out"] = round(accounts[from_key].get("transferred_out", 0.0) + amount, 2)
    accounts[to_key]["transferred_in"] = round(accounts[to_key].get("transferred_in", 0.0) + amount, 2)
    save_accounts(accounts)
    print(f"Transferred ${amount:.2f} from {from_key} to {to_key}.")
    print(f"  {from_key} balance: ${accounts[from_key]['balance']:.2f}")
    print(f"  {to_key} balance:   ${accounts[to_key]['balance']:.2f}")
