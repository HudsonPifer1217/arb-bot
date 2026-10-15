import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("API_KEY")
POLLING_INTERVAL = 300
# Distributed bankroll settings
STARTING_BALANCE_PER_ACCOUNT = 1000.00
LOW_BALANCE_THRESHOLD = 250.00  # an account below this gets topped up
# After each cycle, top up every account below LOW_BALANCE_THRESHOLD to
# AUTO_REBALANCE_TARGET by moving money from the accounts with the most cash
# (a donor is never taken below AUTO_REBALANCE_TARGET). Set False to only warn;
# the `transfer` / `rebalance` commands still do it on demand.
AUTO_REBALANCE = True
AUTO_REBALANCE_TARGET = 500.00
MAX_STAKE_PCT = 0.70        # max 70% of account balance per bet
MAX_REALISTIC_ROI = 0.30    # reject arbs above 30% as likely bad data
MIN_GAME_START_MINUTES = 0  # include all future games regardless of tipoff time
# Simulated bets settle this long after commence_time (money stays tied up until then)
SETTLE_AFTER_HOURS = 3.5

# NOTE: this is a raw percentage (e.g. 0.2 = 0.2%), NOT multiplied by 100 before comparison
# 0.5% skips razor-thin arbs that a line move or rounding would erase on real books.
MIN_PROFIT_THRESHOLD = 0.5  # require at least 0.5% guaranteed profit

# The same game + books + line is simulated once; it is only re-simulated if
# the odds move by more than 5% or this many minutes have passed.
DUPLICATE_WINDOW_MINUTES = 720

# Skip a bookmaker's line if the API says it was last updated more than this
# many minutes ago. None disables the check.
MAX_LINE_AGE_MINUTES = None

# Set to True to enable verbose pipeline tracing (games received, filter counts, best arb_pct seen)
DEBUG = False
SPORTS = [
    "basketball_nba",
    "baseball_mlb",
    "basketball_ncaab",
    "icehockey_nhl",
    "soccer_uefa_champs_league",
    "mma_mixed_martial_arts",
    "soccer_epl",
]
# Odds API cost per call = (number of regions) x (number of markets).
# 7 sports x 2 regions x 1 market = 14 credits per cycle.
# eu/uk books are only useful if you hold accounts there (see account_manager.SPORTSBOOKS).
REGIONS = "us,us2"
# h2h, spreads and totals are all supported by the detector; each extra market costs 1 credit per region per sport.
MARKETS = "h2h"
ODDS_FORMAT = "american"
# Player props need the per-event endpoint (one call per game), which get_odds() does not use.
# Leave empty unless you build that; see scrapers/odds_fetcher.get_props.
PROPS_SPORTS = []
PROP_MARKETS = "player_points,player_rebounds,player_assists,player_strikeouts,player_home_runs,player_hits"
