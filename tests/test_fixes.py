"""
Regression tests for the Oct 2026 bug fixes: detection guards, spreads/totals,
account-only books, UTC dedup, refunds, deferred settlement and bankroll math.

Run with:  python -m pytest tests
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

import config

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.arb_detector import find_arbs
from engine.stake_calculator import calculate_realistic_stakes
import paper_trader.account_manager as am
import paper_trader.logger as logger
import paper_trader.simulator as sim

START = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _game(books, market="h2h"):
    """books: list of (title, [outcome dicts])"""
    return {
        "commence_time": START,
        "home_team": "Home",
        "away_team": "Away",
        "bookmakers": [
            {"title": t, "markets": [{"key": market, "outcomes": outs}]} for t, outs in books
        ],
    }


def _h2h(away, home):
    return [{"name": "Away", "price": away}, {"name": "Home", "price": home}]


@pytest.fixture
def isolated_files(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "ACCOUNTS_FILE", str(tmp_path / "accounts.json"))
    monkeypatch.setattr(logger, "CSV_PATH", str(tmp_path / "paper_trades.csv"))
    monkeypatch.setattr(sim, "TRADES_FILE", str(tmp_path / "simulation_trades.csv"))
    monkeypatch.setattr(sim, "PENDING_FILE", str(tmp_path / "pending_bets.json"))
    return tmp_path


# ── Detection ────────────────────────────────────────────────────────────────

def test_same_book_both_sides_is_rejected():
    assert find_arbs("nba", [_game([("DraftKings", _h2h(150, 150))])]) == []


def test_cross_book_arb_found():
    arbs = find_arbs("nba", [_game([("DraftKings", _h2h(150, -170)), ("FanDuel", _h2h(-170, 150))])])
    assert len(arbs) == 1 and {arbs[0]["book_a"], arbs[0]["book_b"]} == {"DraftKings", "FanDuel"}
    assert arbs[0]["commence_time"] == START


def test_books_without_accounts_are_ignored():
    game = _game([("DraftKings", _h2h(150, -170)), ("Betfair", _h2h(-170, 150))])
    assert find_arbs("nba", [game], allowed_books={"DraftKings", "FanDuel"}) == []
    # ...but they no longer hide an arb between two books you do have
    game = _game([("DraftKings", _h2h(150, -170)), ("FanDuel", _h2h(-170, 145)), ("Betfair", _h2h(-170, 160))])
    arbs = find_arbs("nba", [game], allowed_books={"DraftKings", "FanDuel"})
    assert len(arbs) == 1 and arbs[0]["odds_b"] == 145


def test_totals_arb_detected_on_same_line_only():
    over_dk = [{"name": "Over", "price": 150, "point": 220.5}, {"name": "Under", "price": -200, "point": 220.5}]
    under_fd = [{"name": "Over", "price": -200, "point": 220.5}, {"name": "Under", "price": 150, "point": 220.5}]
    arbs = find_arbs("nba", [_game([("DraftKings", over_dk), ("FanDuel", under_fd)], market="totals")])
    assert len(arbs) == 1 and arbs[0]["market"] == "totals" and arbs[0]["line"] == 220.5

    # Different lines are different bets, never combined
    under_fd_other = [{"name": "Over", "price": -200, "point": 221.5}, {"name": "Under", "price": 150, "point": 221.5}]
    assert find_arbs("nba", [_game([("DraftKings", over_dk), ("FanDuel", under_fd_other)], market="totals")]) == []


def test_spreads_pair_opposite_sides():
    dk = [{"name": "Home", "price": 150, "point": -3.5}, {"name": "Away", "price": -200, "point": 3.5}]
    fd = [{"name": "Home", "price": -200, "point": -3.5}, {"name": "Away", "price": 150, "point": 3.5}]
    arbs = find_arbs("nba", [_game([("DraftKings", dk), ("FanDuel", fd)], market="spreads")])
    assert len(arbs) == 1
    assert {arbs[0]["team_a"], arbs[0]["team_b"]} == {"Home -3.5", "Away +3.5"}


# ── Accounts and simulation ──────────────────────────────────────────────────

def test_refund_returns_only_the_stake(isolated_files):
    assert am.place_bet("DraftKings", 100.0, 150)
    am.refund_bet("DraftKings", 100.0)
    acct = am.load_accounts()["DraftKings"]
    assert acct["balance"] == am.DEFAULT_BALANCE
    assert acct["bet_count"] == 0 and acct["total_won"] == 0


def test_failed_second_leg_does_not_create_money(isolated_files):
    accounts = am.load_accounts()
    accounts["FanDuel"]["balance"] = 1.0  # can't cover leg B
    am.save_accounts(accounts)
    before = sum(a["balance"] for a in am.load_accounts().values())
    arb = {"book_a": "DraftKings", "book_b": "FanDuel", "odds_a": 150, "odds_b": 150,
           "realistic_stake_a": 50.0, "realistic_stake_b": 50.0, "market_type": "2-way"}
    assert sim.simulate_arb(arb, am) is None
    assert sum(a["balance"] for a in am.load_accounts().values()) == before


def test_bets_settle_after_the_game_and_profit_is_real(isolated_files):
    game = _game([("DraftKings", _h2h(150, -170)), ("FanDuel", _h2h(-170, 150))])
    arb = find_arbs("nba", [game])[0]
    staked = calculate_realistic_stakes(arb, am)
    bet = sim.simulate_arb(staked, am)
    assert bet is not None

    # Nothing settles before the game is over; the stakes are tied up
    assert sim.settle_due_bets(am) == []
    assert sim.open_stakes_total() > 0

    later = datetime.now(timezone.utc) + timedelta(days=1)
    settled = sim.settle_due_bets(am, now=later)
    assert len(settled) == 1 and sim.load_pending() == []
    assert settled[0]["net_profit"] > 0
    assert settled[0]["net_profit"] == pytest.approx(staked["realistic_profit"], abs=0.02)


def test_starting_bankroll_matches_accounts(isolated_files):
    accounts = am.load_accounts()
    assert am.starting_bankroll(accounts) == len(am.SPORTSBOOKS) * am.DEFAULT_BALANCE


def test_transfer_keeps_per_account_pl_neutral(isolated_files):
    am.transfer_funds("FanDuel", "DraftKings", 200.0)
    accounts = am.load_accounts()
    assert am.net_pl(accounts["FanDuel"]) == 0
    assert am.net_pl(accounts["DraftKings"]) == 0
    assert am.starting_bankroll(accounts) == len(am.SPORTSBOOKS) * am.DEFAULT_BALANCE


# ── Dedup ────────────────────────────────────────────────────────────────────

def test_dedup_uses_utc_and_blocks_resimulation(isolated_files):
    game = _game([("DraftKings", _h2h(150, -170)), ("FanDuel", _h2h(-170, 150))])
    arb = find_arbs("nba", [game])[0]
    assert not logger.is_recent_duplicate(arb)
    assert logger.log_opportunity(arb)
    # Seen again next cycle with the same odds: already bet
    assert logger.is_recent_duplicate(arb)
    # Odds moved more than 5%: a new opportunity
    moved = {**arb, "odds_a": 190}
    assert not logger.is_recent_duplicate(moved)


def test_dedup_window_is_not_shifted_by_local_timezone(isolated_files, monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    if hasattr(__import__("time"), "tzset"):
        __import__("time").tzset()
    game = _game([("DraftKings", _h2h(150, -170)), ("FanDuel", _h2h(-170, 150))])
    arb = find_arbs("nba", [game])[0]
    old = {**arb, "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=logger.DUPLICATE_WINDOW_MINUTES + 5)).strftime("%Y-%m-%d %H:%M:%S")}
    logger.log_opportunity(old)
    assert not logger.is_recent_duplicate(arb)


# ── Open bets and shared-book caps ───────────────────────────────────────────

def test_open_bet_blocks_rebet_after_window(isolated_files, monkeypatch):
    game = _game([("DraftKings", _h2h(150, -170)), ("FanDuel", _h2h(-170, 150))])
    arb = find_arbs("nba", [game])[0]
    staked = calculate_realistic_stakes(arb, am)
    assert sim.simulate_arb(staked, am) is not None
    assert logger.log_opportunity(arb)
    # The CSV window has expired, but the bet is still open: no re-bet
    monkeypatch.setattr(logger, "DUPLICATE_WINDOW_MINUTES", 0)
    assert logger._find_recent_duplicate(logger._make_arb_id(arb), logger._utc_now()) is None
    assert logger.is_recent_duplicate(arb)
    # Odds moved more than 5%: a new opportunity even with the bet open
    assert not logger.is_recent_duplicate({**arb, "odds_a": 190})
    # Once settled, the window rules alone apply again
    sim.settle_due_bets(am, now=datetime.now(timezone.utc) + timedelta(days=1))
    assert not logger.is_recent_duplicate(arb)


def test_shared_book_legs_share_one_stake_cap(isolated_files):
    accounts = am.load_accounts()
    accounts["BetOnline.ag"]["balance"] = 480.11
    am.save_accounts(accounts)
    arb = {"game": "AEK Athens @ Shakhtar Donetsk", "market_type": "3-way", "arb_pct": 0.998889,
           "book_a": "BetOnline.ag", "book_b": "BetOnline.ag", "book_c": "BetUS",
           "odds_a": 176, "odds_b": 173, "odds_c": 270,
           "outcome_a": "AEK Athens", "outcome_b": "Draw", "outcome_c": "Shakhtar Donetsk"}
    staked = calculate_realistic_stakes(arb, am)
    combined = staked["realistic_stake_a"] + staked["realistic_stake_b"]
    assert combined <= 480.11 * config.MAX_STAKE_PCT + 0.02
    assert staked["constrained_by"] == "BetOnline.ag"
    assert sim.simulate_arb(staked, am) is not None


def test_simulate_rejects_shared_book_overdraw_without_placing(isolated_files):
    accounts = am.load_accounts()
    accounts["BetOnline.ag"]["balance"] = 100.0
    am.save_accounts(accounts)
    before = {k: v["balance"] for k, v in am.load_accounts().items()}
    arb = {"book_a": "BetOnline.ag", "book_b": "BetOnline.ag", "book_c": "BetUS",
           "odds_a": 176, "odds_b": 173, "odds_c": 270, "market_type": "3-way",
           "realistic_stake_a": 60.0, "realistic_stake_b": 60.0, "realistic_stake_c": 50.0}
    assert sim.simulate_arb(arb, am) is None
    after = {k: v["balance"] for k, v in am.load_accounts().items()}
    assert after == before and am.load_accounts()["BetOnline.ag"]["bet_count"] == 0
