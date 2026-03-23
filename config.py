import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("API_KEY")
POLLING_INTERVAL = 300
BANKROLL = 1000
MIN_PROFIT_THRESHOLD = 0.01
SPORTS = ["basketball_nba", "baseball_mlb", "basketball_ncaab"]
REGIONS = "us"
MARKETS = "h2h,spreads,totals"
ODDS_FORMAT = "american"
PROPS_SPORTS = ["basketball_nba", "baseball_mlb", "basketball_ncaab"]
PROP_MARKETS = "player_points,player_rebounds,player_assists,player_strikeouts,player_home_runs,player_hits"
