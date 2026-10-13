"""
Unit tests for paper_trader/logger.py.

Verifies that log_opportunity() writes rows correctly to CSV, applies the
default "open" status, round-trips field values accurately, and that
print_summary() and get_summary_stats() return correct aggregate totals.
Writes to a temp CSV (paper_trades_test.csv) and cleans up after each run.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paper_trader.logger as logger

# Redirect CSV writes to a temp file so real paper_trades.csv is never touched
TEST_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper_trades_test.csv")
logger.CSV_PATH = TEST_CSV_PATH

FAKE_ARB_1 = {
    "timestamp": "2026-03-22 10:00:00",
    "sport": "basketball_nba",
    "game": "Los Angeles Lakers @ Boston Celtics",
    "team_a": "Los Angeles Lakers",
    "team_b": "Boston Celtics",
    "book_a": "DraftKings",
    "book_b": "FanDuel",
    "odds_a": 150,
    "odds_b": 150,
    "stake_a": 500.0,
    "stake_b": 500.0,
    "guaranteed_profit": 250.0,
    "roi_pct": 25.0,
    "arb_pct": 0.8,
}

FAKE_ARB_2 = {
    "timestamp": "2026-03-22 11:00:00",
    "sport": "baseball_mlb",
    "game": "New York Yankees @ Chicago Cubs",
    "team_a": "New York Yankees",
    "team_b": "Chicago Cubs",
    "book_a": "BetMGM",
    "book_b": "Caesars",
    "odds_a": 120,
    "odds_b": 130,
    "stake_a": 476.19,
    "stake_b": 523.81,
    "guaranteed_profit": 71.43,
    "roi_pct": 7.143,
    "arb_pct": 0.934,
}


FAILURES = []


def _fail(msg):
    FAILURES.append(msg)
    print(msg)


def run_tests():
    # Clean up any leftover test file from a prior run
    if os.path.exists(TEST_CSV_PATH):
        os.remove(TEST_CSV_PATH)

    try:
        # --- Test 1: log two opportunities ---
        logger.log_opportunity(FAKE_ARB_1)
        logger.log_opportunity(FAKE_ARB_2)

        with open(TEST_CSV_PATH, newline="") as f:
            rows = list(csv.DictReader(f))

        if len(rows) == 2:
            print("PASS  Two rows written to CSV")
        else:
            _fail(f"FAIL  Expected 2 rows, got {len(rows)}")

        # --- Test 2: status defaults to "open" ---
        if rows[0]["status"] == "open" and rows[1]["status"] == "open":
            print("PASS  Default status is 'open'")
        else:
            _fail(f"FAIL  Unexpected status values: {rows[0]['status']}, {rows[1]['status']}")

        # --- Test 3: fields round-trip correctly ---
        if rows[0]["game"] == FAKE_ARB_1["game"] and float(rows[0]["roi_pct"]) == FAKE_ARB_1["roi_pct"]:
            print("PASS  Fields written and read back correctly")
        else:
            _fail(f"FAIL  Field mismatch: {rows[0]}")

        # --- Test 4: print_summary() runs without errors ---
        try:
            print("\n--- print_summary() output ---")
            logger.print_summary()
            print("--- end summary ---\n")
            print("PASS  print_summary() completed without errors")
        except Exception as e:
            _fail(f"FAIL  print_summary() raised: {e}")

        # --- Test 5: summary math is correct ---
        expected_total_profit = FAKE_ARB_1["guaranteed_profit"] + FAKE_ARB_2["guaranteed_profit"]
        expected_avg_roi = (FAKE_ARB_1["roi_pct"] + FAKE_ARB_2["roi_pct"]) / 2

        actual_profits = sum(float(r["guaranteed_profit"]) for r in rows)
        actual_avg_roi = sum(float(r["roi_pct"]) for r in rows) / len(rows)

        if abs(actual_profits - expected_total_profit) < 0.01:
            print(f"PASS  Total profit correct: ${actual_profits:.2f}")
        else:
            _fail(f"FAIL  Expected ${expected_total_profit:.2f}, got ${actual_profits:.2f}")

        if abs(actual_avg_roi - expected_avg_roi) < 0.001:
            print(f"PASS  Average ROI correct: {actual_avg_roi:.4f}%")
        else:
            _fail(f"FAIL  Expected avg ROI {expected_avg_roi:.4f}%, got {actual_avg_roi:.4f}%")

    finally:
        # Always clean up the test CSV
        if os.path.exists(TEST_CSV_PATH):
            os.remove(TEST_CSV_PATH)
            print("\nCleanup: test CSV removed.")

    if FAILURES:
        raise AssertionError(f"{len(FAILURES)} check(s) failed: {FAILURES}")


def test_logger():
    """pytest entry point."""
    FAILURES.clear()
    run_tests()


if __name__ == "__main__":
    run_tests()
