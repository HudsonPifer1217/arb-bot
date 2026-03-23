"""
Logs arbitrage opportunities to paper_trades.csv and reports aggregate stats.

Handles CSV creation and schema migration, deduplicates opportunities within a
configurable time window (suppressing re-logs unless odds shift significantly),
and provides get_summary_stats() / print_summary() for cycle reporting.
"""

import csv
import hashlib
import os
from datetime import datetime, timedelta

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper_trades.csv")

COLUMNS = [
    "arb_id", "timestamp", "sport", "game", "team_a", "team_b",
    "book_a", "book_b", "odds_a", "odds_b",
    "stake_a", "stake_b", "guaranteed_profit", "roi_pct", "arb_pct", "status",
]

DUPLICATE_WINDOW_MINUTES = 15
ODDS_CHANGE_THRESHOLD = 0.05  # 5% change in decimal odds on either leg triggers a re-log


def _ensure_csv() -> None:
    """Create paper_trades.csv with a header row if it does not already exist.

    If the file exists but is missing the arb_id column (written by an older
    version), rewrites it in place with arb_id added as blank for all prior rows.
    """
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=COLUMNS).writeheader()
        return

    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        if "arb_id" in existing_fields:
            return
        rows = list(reader)

    # Migrate: rewrite file with arb_id column
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in COLUMNS})


def _make_arb_id(arb: dict) -> str:
    """Generate a short stable hash identifying a unique bookmaker/game matchup.

    Hashes the combination of game + book_a + book_b so that the same pairing
    across multiple polling cycles produces the same ID regardless of odds movement.

    Args:
        arb: Arb opportunity dict containing game, book_a, book_b.

    Returns:
        First 12 hex characters of the MD5 hash of the combined key.
    """
    key = f"{arb.get('game', '')}{arb.get('book_a', '')}{arb.get('book_b', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _to_decimal(american: float) -> float:
    """Convert American odds to decimal odds.

    Args:
        american: American odds value (positive or negative).

    Returns:
        Equivalent decimal odds.
    """
    if american > 0:
        return (american / 100) + 1
    return (100 / abs(american)) + 1


def _find_recent_duplicate(arb_id: str, now: datetime) -> dict | None:
    """Search paper_trades.csv for the most recent row matching arb_id within the duplicate window.

    Args:
        arb_id: Hash string as produced by _make_arb_id().
        now: Current timestamp used to compute the lookback cutoff.

    Returns:
        The most recent matching CSV row as a dict, or None if no match is found
        within DUPLICATE_WINDOW_MINUTES.
    """
    cutoff = now - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    candidates = []
    with open(CSV_PATH, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("arb_id") != arb_id:
                continue
            try:
                ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if ts >= cutoff:
                candidates.append((ts, row))
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]


def _odds_changed_significantly(new_arb: dict, old_row: dict) -> bool:
    """Return True if either leg's decimal odds shifted by more than ODDS_CHANGE_THRESHOLD.

    Used to allow re-logging an arb that was recently seen but whose odds have
    moved enough to represent a genuinely different opportunity.

    Args:
        new_arb: Incoming arb opportunity dict with odds_a and odds_b (american).
        old_row: Previously logged CSV row dict with odds_a and odds_b.

    Returns:
        True if the relative change on either leg exceeds ODDS_CHANGE_THRESHOLD.
    """
    try:
        new_a = _to_decimal(float(new_arb["odds_a"]))
        new_b = _to_decimal(float(new_arb["odds_b"]))
        old_a = _to_decimal(float(old_row["odds_a"]))
        old_b = _to_decimal(float(old_row["odds_b"]))
    except (KeyError, ValueError, ZeroDivisionError):
        return False
    change_a = abs(new_a - old_a) / old_a if old_a else 0
    change_b = abs(new_b - old_b) / old_b if old_b else 0
    return change_a > ODDS_CHANGE_THRESHOLD or change_b > ODDS_CHANGE_THRESHOLD


def log_opportunity(arb: dict, status: str = "open") -> None:
    """Append a single arb opportunity as a new row in paper_trades.csv.

    Before writing, checks whether an identical matchup (same game + book_a +
    book_b) was already logged within DUPLICATE_WINDOW_MINUTES. If so, skips
    logging and prints a skip message — unless the odds on either leg have
    shifted by more than ODDS_CHANGE_THRESHOLD, in which case the opportunity
    is treated as genuinely new and logged regardless.

    Generates an arb_id hash of game + book_a + book_b for fast dedup lookup.

    Args:
        arb: Arb opportunity dict, typically the output of calculate_stakes().
            Expected keys: timestamp, sport, game, team_a, team_b, book_a,
            book_b, odds_a, odds_b, stake_a, stake_b, guaranteed_profit,
            roi_pct, arb_pct.
        status: Lifecycle label for the trade. Defaults to "open".
    """
    _ensure_csv()
    now = datetime.now()
    arb_id = _make_arb_id(arb)

    duplicate = _find_recent_duplicate(arb_id, now)
    if duplicate:
        if not _odds_changed_significantly(arb, duplicate):
            prior_ts = datetime.strptime(duplicate["timestamp"], "%Y-%m-%d %H:%M:%S")
            mins_ago = int((now - prior_ts).total_seconds() / 60)
            print(f" [SKIP] Duplicate arb, already logged {mins_ago} min(s) ago — {arb.get('game')}")
            return

    row = {col: arb.get(col, "") for col in COLUMNS}
    row["arb_id"] = arb_id
    row["timestamp"] = arb.get("timestamp", now.strftime("%Y-%m-%d %H:%M:%S"))
    row["status"] = status
    with open(CSV_PATH, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=COLUMNS).writerow(row)


def get_summary_stats() -> dict | None:
    """Return aggregate stats across all logged trades as a dict.

    Reads paper_trades.csv and computes total opportunities, total simulated
    profit, and average ROI. Returns None if the CSV is empty.

    Returns:
        Dict with keys total (int), total_profit (float), avg_roi (float),
        or None if no trades have been logged yet.
    """
    _ensure_csv()
    with open(CSV_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    roi_values = [float(r["roi_pct"]) for r in rows]
    return {
        "total": len(rows),
        "total_profit": sum(float(r["guaranteed_profit"]) for r in rows),
        "avg_roi": sum(roi_values) / len(roi_values),
    }


def print_summary() -> None:
    """Print a summary of all logged arbs to stdout.

    Reads paper_trades.csv and prints total opportunities, total simulated
    profit, average ROI, and the single best arb by ROI. Prints a no-data
    message and returns early if the CSV is empty.
    """
    _ensure_csv()
    with open(CSV_PATH, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No trades logged yet.")
        return

    total = len(rows)
    total_profit = sum(float(r["guaranteed_profit"]) for r in rows)
    roi_values = [float(r["roi_pct"]) for r in rows]
    best = max(rows, key=lambda r: float(r["roi_pct"]))
    avg_roi = sum(roi_values) / len(roi_values)

    print(f"Total opportunities logged : {total}")
    print(f"Total simulated profit     : ${total_profit:.2f}")
    print(f"Average ROI                : {avg_roi:.4f}%")
    print(f"Best arb (ROI {best['roi_pct']}%)     : {best['game']} — {best['team_a']} ({best['book_a']}) vs {best['team_b']} ({best['book_b']})")
