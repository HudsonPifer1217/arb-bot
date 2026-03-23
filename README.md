# Arb Bot — Sports Arbitrage Detection System

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Mode](https://img.shields.io/badge/Mode-Paper%20Trading-orange)

Arb Bot is a real-time sports arbitrage scanner that monitors odds across 40+ bookmakers, detects guaranteed-profit opportunities by identifying cross-book pricing inefficiencies, and calculates optimal stake sizes to lock in profit regardless of outcome. Built in pure Python with a live Streamlit dashboard, the system operates in paper trading mode — logging every qualifying opportunity to CSV for full performance analysis without risking real capital.

---

## How It Works

```
┌──────────────────────┐
│    The Odds API      │  REST endpoint: /v4/sports/{sport}/odds/
└──────────┬───────────┘
           │  raw JSON — odds per game per bookmaker
           ▼
┌──────────────────────┐
│   odds_fetcher.py    │  polls game odds + player prop markets
│  (scrapers/)         │  handles 401 / 422 / 429 / timeout
└──────────┬───────────┘
           │  parsed odds dicts
           ▼
┌──────────────────────┐
│   arb_detector.py    │  finds best odds per side across all books
│  (engine/)           │  flags games where Σ(1/odds) < 1.0
└──────────┬───────────┘
           │  arbitrage opportunity dicts
           ▼
┌──────────────────────┐
│ stake_calculator.py  │  sizes each leg: stake = bankroll × (1/odds) / arb%
│  (engine/)           │  guarantees equal profit on either outcome
└──────────┬───────────┘
           │  opportunity + computed stake fields
           ▼
┌──────────────────────┐
│     logger.py        │  appends to paper_trades.csv
│  (paper_trader/)     │  prints live cycle summary to terminal
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│    dashboard.py      │  Streamlit UI — cumulative P&L chart,
│                      │  sortable arb table, bookmaker frequency
└──────────────────────┘
```

---

## Features

- **Real-time odds monitoring** across 40+ bookmakers via The Odds API
- **Arbitrage detection** across NBA, MLB, and NCAA Basketball (game odds + player props)
- **Automated stake calculation** for guaranteed profit on each qualifying opportunity
- **Paper trading mode** with full CSV logging — sport, game, books, odds, stakes, profit, ROI
- **Streamlit dashboard** with live cumulative P&L chart, sortable arb table, and bookmaker stats
- **Deduplication logic** to prevent double-counting the same opportunity across polling cycles

---

## Tech Stack

| | Library | Purpose |
|---|---|---|
| ![Python](https://img.shields.io/badge/-Python-3776AB?logo=python&logoColor=white&style=flat-square) | `Python 3.9+` | Core runtime |
| ![Requests](https://img.shields.io/badge/-requests-grey?style=flat-square) | `requests 2.32.3` | HTTP calls to The Odds API |
| ![Pandas](https://img.shields.io/badge/-pandas-150458?logo=pandas&logoColor=white&style=flat-square) | `pandas 2.2.2` | CSV loading and aggregation in the dashboard |
| ![Streamlit](https://img.shields.io/badge/-Streamlit-FF4B4B?logo=streamlit&logoColor=white&style=flat-square) | `streamlit 1.37.1` | Interactive web dashboard |
| ![dotenv](https://img.shields.io/badge/-python--dotenv-ECD53F?style=flat-square) | `python-dotenv 0.21.0` | API key loading from `.env` |

---

## Project Structure

```
arb-bot/
├── main.py                        # Entry point — polling loop and orchestration
├── config.py                      # All tunable parameters
├── dashboard.py                   # Streamlit dashboard
├── requirements.txt               # Pinned dependencies
├── .env                           # API key (not committed)
├── .env.example                   # Template for .env
├── .gitignore
├── paper_trades.csv               # Live paper trading log
│
├── scrapers/
│   └── odds_fetcher.py            # Fetches game odds + player props from The Odds API
│
├── engine/
│   ├── arb_detector.py            # Detects arbitrage opportunities
│   └── stake_calculator.py        # Calculates optimal leg stakes
│
├── paper_trader/
│   ├── logger.py                  # Logs arbs to CSV, prints cycle summaries
│   └── simulator.py               # Paper trading simulation helpers
│
├── backtest/
│   └── backtest.py                # Historical backtesting utilities
│
└── tests/
    ├── test_arb_detector.py
    ├── test_stake_calculator.py
    └── test_logger.py
```

---

## Setup & Installation

**1. Clone the repo**
```bash
git clone https://github.com/yourname/arb-bot.git
cd arb-bot
```

**2. Create your `.env` from the example**
```bash
cp .env.example .env
# Then open .env and add your API key:
# API_KEY=your_odds_api_key_here
```
Get a free key at [the-odds-api.com](https://the-odds-api.com).

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Run the bot**
```bash
python main.py
```

**5. Run the dashboard** *(in a separate terminal)*
```bash
streamlit run dashboard.py
```

---

## Configuration

All tunable parameters live in [config.py](config.py):

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | *(from `.env`)* | Your Odds API key, loaded via `python-dotenv` |
| `POLLING_INTERVAL` | `300` | Seconds between full scan cycles |
| `BANKROLL` | `1000` | Simulated bankroll in USD used for stake sizing |
| `MIN_PROFIT_THRESHOLD` | `0.01` | Minimum arbitrage margin to log (e.g. `0.01` = 1%) |
| `SPORTS` | `["basketball_nba", "baseball_mlb", "basketball_ncaab"]` | Sports to scan for game odds |
| `REGIONS` | `"us"` | Bookmaker regions to include in API requests |
| `MARKETS` | `"h2h,spreads,totals"` | Game market types to scan |
| `ODDS_FORMAT` | `"american"` | Odds format returned by the API |
| `PROPS_SPORTS` | `["basketball_nba", "baseball_mlb", "basketball_ncaab"]` | Sports to scan for player prop odds |
| `PROP_MARKETS` | `"player_points,player_rebounds,player_assists,player_strikeouts,player_home_runs,player_hits"` | Player prop markets to scan |

---

## Sample Output

**Terminal**
```
====================================================
         ARB BOT — PAPER TRADING MODE
====================================================
  Bankroll:          $1,000.00
  Min profit:        1.00%
  Sports:            basketball_nba, baseball_mlb, basketball_ncaab
  Polling interval:  300s
====================================================

[2026-03-22 10:14:03] basketball_nba | Requests remaining: 487
[2026-03-22 10:14:04] baseball_mlb   | Requests remaining: 486
[2026-03-22 10:14:05] basketball_ncaab | Requests remaining: 485
[PROPS] [2026-03-22 10:14:06] basketball_nba | Requests remaining: 484

  [ARB] Los Angeles Lakers @ Boston Celtics
        Lakers ML (DraftKings +215) vs Celtics ML (FanDuel -190)
        Stake A: $317.46 | Stake B: $682.54 | Profit: $31.22 | ROI: 3.12%

Total opportunities logged : 4
Total simulated profit     : $87.43
Average ROI                : 2.19%
Best arb (ROI 3.12%)       : Lakers @ Celtics — DraftKings vs FanDuel

--- Cycle complete, sleeping 300s ---
```

**Dashboard**

> Screenshot coming soon — will show cumulative P&L line chart, sortable arbitrage table with sport/game/books/ROI columns, and bookmaker frequency bar chart.

---

## Results

> Paper trading results will be updated after 7-day session.

| Metric | Value |
|---|---|
| Observation period | — |
| Total cycles run | — |
| Arbs detected | — |
| Total simulated profit | — |
| Average ROI per arb | — |
| Most frequent bookmaker | — |

---

## Disclaimer

This project is built for **educational and research purposes only**. Arbitrage betting may violate the terms of service of individual sportsbooks and can result in account limitations or closures. No real money is placed by this software. The authors accept no liability for any financial loss arising from use of this tool. Always verify local regulations and gamble responsibly within the laws of your jurisdiction.

---

## License

This project is licensed under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
