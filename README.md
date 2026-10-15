# Arb Bot — Sports Arbitrage Detection System

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Mode](https://img.shields.io/badge/Mode-Paper%20Trading-orange)

Arb Bot is a sports arbitrage scanner. It polls The Odds API, finds games where the best prices at different sportsbooks guarantee a profit whatever the outcome, sizes each leg against simulated account balances, and places the bet on paper. Bets stay open until the game is over and then settle against the simulated accounts. A Streamlit dashboard shows the logged arbs, balances and P/L. No real money is ever placed.

---

## How It Works

```
┌──────────────────────┐
│    The Odds API      │  REST endpoint: /v4/sports/{sport}/odds/
└──────────┬───────────┘
           │  raw JSON — odds per game per bookmaker
           ▼
┌──────────────────────┐
│   odds_fetcher.py    │  polls game odds per sport
│  (scrapers/)         │  survives network errors and bad JSON
└──────────┬───────────┘
           │  parsed odds dicts
           ▼
┌──────────────────────┐
│   arb_detector.py    │  best odds per side at books you have accounts at
│  (engine/)           │  flags lines where Σ(1/odds) < 1.0
└──────────┬───────────┘
           │  arbitrage opportunity dicts
           ▼
┌──────────────────────┐
│ stake_calculator.py  │  sizes each leg for equal profit on any outcome,
│  (engine/)           │  capped at MAX_STAKE_PCT of each account's balance
└──────────┬───────────┘
           │  opportunity + computed stake fields
           ▼
┌──────────────────────┐
│ simulator.py/logger  │  places the bet on the simulated accounts, logs it to
│  (paper_trader/)     │  paper_trades.csv, settles it after the game ends
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

- **25 simulated sportsbook accounts** (DraftKings, FanDuel, BetMGM, Caesars, BetOnline.ag, Hard Rock Bet, ...), each starting at $1,000, persisted in `paper_trader/accounts.json`
- **Only books you hold accounts at** are used for detection; any other books in the API response are ignored (listed with `DEBUG = True`)
- **Markets:** moneyline (2-way, and 3-way home/draw/away for soccer), spreads and totals
- **Realistic stakes:** each leg is capped at `MAX_STAKE_PCT` of that account's balance, and the arb is skipped if a leg can't be funded
- **Bets settle after the game:** open bets are kept in `paper_trader/pending_bets.json` and settle `SETTLE_AFTER_HOURS` after start time, so the money stays tied up meanwhile
- **No double-counting:** the same game, market, line and books is bet once unless the odds move more than 5% or `DUPLICATE_WINDOW_MINUTES` passes
- **Automatic rebalancing:** when an account drops below `LOW_BALANCE_THRESHOLD`, money is moved from the accounts with the most cash to bring it back to `AUTO_REBALANCE_TARGET`, the way you'd move money between your own books. Transfers don't count as profit or loss
- **Sanity filters:** same-book "arbs" and arbs above `MAX_REALISTIC_ROI` are rejected as bad data
- **Interactive commands** while the bot runs (see below)
- **Streamlit dashboard** with cumulative profit, the arb table, account balances, bankroll over time and win rate per book

---

## Tech Stack

| | Library | Purpose |
|---|---|---|
| ![Python](https://img.shields.io/badge/-Python-3776AB?logo=python&logoColor=white&style=flat-square) | `Python 3.10+` | Core runtime (3.9 also works) |
| ![Requests](https://img.shields.io/badge/-requests-grey?style=flat-square) | `requests 2.32.3` | HTTP calls to The Odds API |
| ![Pandas](https://img.shields.io/badge/-pandas-150458?logo=pandas&logoColor=white&style=flat-square) | `pandas 2.2.2` | CSV loading and aggregation in the dashboard |
| ![Streamlit](https://img.shields.io/badge/-Streamlit-FF4B4B?logo=streamlit&logoColor=white&style=flat-square) | `streamlit 1.37.1` | Interactive web dashboard |
| ![dotenv](https://img.shields.io/badge/-python--dotenv-ECD53F?style=flat-square) | `python-dotenv 0.21.0` | API key loading from `.env` |
| ![tabulate](https://img.shields.io/badge/-tabulate-grey?style=flat-square) | `tabulate 0.9.0` | Account balance tables in the terminal |

---

## Project Structure

```
arb-bot/
├── main.py                        # Entry point: polling loop, cycle output, commands
├── config.py                      # All tunable parameters
├── dashboard.py                   # Streamlit dashboard
├── requirements.txt               # Pinned dependencies
├── .env.example                   # Template for .env (your API key, never committed)
├── .gitignore
│
├── scrapers/
│   └── odds_fetcher.py            # Fetches odds from The Odds API
│
├── engine/
│   ├── arb_detector.py            # Detects arbs (h2h 2/3-way, spreads, totals)
│   └── stake_calculator.py        # Equal-profit stakes, capped by account balance
│
├── paper_trader/
│   ├── account_manager.py         # Simulated sportsbook accounts and transfers
│   ├── simulator.py               # Places, tracks and settles simulated bets
│   └── logger.py                  # paper_trades.csv logging and duplicate checks
│
├── backtest/
│   └── backtest.py                # Replays logged trades with slippage over a date range
│
└── tests/                         # pytest suite
```

Generated at runtime and git-ignored: `paper_trades.csv`, `paper_trader/accounts.json`, `paper_trader/pending_bets.json`, `paper_trader/simulation_trades.csv`.

---

## Setup & Installation

**1. Clone the repo**
```bash
git clone https://github.com/HudsonPifer1217/arb-bot.git
cd arb-bot
```

**2. Create your `.env` from the example**
```bash
cp .env.example .env
# Then open .env and put your key after API_KEY=
```
Get a free key at [the-odds-api.com](https://the-odds-api.com). The free tier has 500 credits a month; with the default settings a cycle costs about 12–14 credits.

**3. Install dependencies**
```bash
python -m pip install -r requirements.txt
```

**4. Run the bot**
```bash
python main.py
```

Stop it with Ctrl+C. To start a fresh session, move `paper_trades.csv`, `paper_trader/accounts.json` and `paper_trader/pending_bets.json` somewhere else; all accounts then start again at $1,000.

**5. Run the dashboard** *(in a separate terminal)*
```bash
streamlit run dashboard.py
```

**6. Run the tests**
```bash
pytest
```

**Backtest logged trades**
```bash
python backtest/backtest.py --start 2026-10-01 --end 2026-10-31
```

---

## Commands

Type these into the terminal while the bot is running:

| Command | What it does |
|---|---|
| `transfer` | Top up low accounts now (this also happens automatically when `AUTO_REBALANCE` is on) |
| `balances` | Print the full account balance table |
| `summary` | Print the session summary |
| `rebalance` | Same as `transfer`, asking for confirmation first |
| `status` | Show the cycle count, arbs found, profit and API credits remaining |
| `help` | List the commands |

---

## Configuration

All tunable parameters live in [config.py](config.py):

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | *(from `.env`)* | Your Odds API key |
| `POLLING_INTERVAL` | `300` | Seconds between cycles |
| `SPORTS` | NBA, MLB, NCAAB, NHL, Champions League, MMA, EPL | Sports to scan |
| `REGIONS` | `"us,us2"` | Bookmaker regions. Each region costs 1 credit per sport per market |
| `MARKETS` | `"h2h"` | Add `spreads,totals` if you have the credits (1 credit each per region per sport) |
| `ODDS_FORMAT` | `"american"` | Odds format returned by the API |
| `STARTING_BALANCE_PER_ACCOUNT` | `1000.00` | Starting balance of each simulated account |
| `MAX_STAKE_PCT` | `0.70` | Max share of an account's balance on one leg |
| `MIN_PROFIT_THRESHOLD` | `0.5` | Minimum guaranteed profit, in percent (0.5 = 0.5%). Thinner arbs are skipped |
| `MAX_REALISTIC_ROI` | `0.30` | Arbs above 30% are rejected as bad data |
| `LOW_BALANCE_THRESHOLD` | `250.00` | An account below this is topped up |
| `AUTO_REBALANCE` | `True` | Top up low accounts automatically at the start of each cycle and before placing an arb |
| `AUTO_REBALANCE_TARGET` | `500.00` | Low accounts are topped up to this; a donor account is never taken below it |
| `SETTLE_AFTER_HOURS` | `3.5` | Hours after start time that a bet settles |
| `DUPLICATE_WINDOW_MINUTES` | `720` | How long before the same arb can be bet again |
| `MAX_LINE_AGE_MINUTES` | `None` | Skip lines older than this (off by default) |
| `DEBUG` | `False` | Verbose per-sport tracing: games, books, closest arb, ignored books |

Player props need the per-event endpoint (one call per game), which the bot doesn't use yet, so `PROPS_SPORTS` is empty.
---

## Sample Output

**Terminal** *(from a real run, trimmed)*
```
 CYCLE 1  2026-10-12 21:20:31
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 basketball_nba     ✓  requests remaining: 498
 baseball_mlb       ✓  requests remaining: 496
 basketball_ncaab   ✗  requests remaining: 496
 icehockey_nhl      ✓  requests remaining: 494
 soccer_uefa_champs_league ✓  requests remaining: 492
 mma_mixed_martial_arts ✓  requests remaining: 490
 soccer_epl         ✓  requests remaining: 488

 🎯 ARB PLACED: Cristian Pérez @ Kyle Nelson (h2h)
    Hard Rock Bet Cristian Pérez ($700.00) vs BetOnline.ag Kyle Nelson ($247.93)
    Expected profit: $+6.60  |  Settles after 2026-10-18 05:30:00 UTC

 🎯 ARB PLACED: Alex Pereira @ Sergey Pavlovich (h2h)
    BetOnline.ag Alex Pereira ($119.97) vs Hard Rock Bet Sergey Pavlovich ($210.00)
    Expected profit: $+3.55  |  Settles after 2026-12-13 07:00:00 UTC

 Total arbs: 2  |  Expected profit: $10.15  |  Avg ROI: 0.89%
```

**Dashboard**

> Screenshot coming soon — will show cumulative P&L line chart, sortable arbitrage table with sport/game/books/ROI columns, and bookmaker frequency bar chart.

---

## Results

> First test run on the free tier. Longer paper-trading results pending.

| Metric | Value |
|---|---|
| Observation period | 2026-10-13, about 15 minutes |
| Total cycles run | 3 |
| Arbs placed | 2 (both MMA, Hard Rock Bet vs BetOnline.ag) |
| Total expected profit | $10.15 (not yet settled) |
| Average ROI per arb | 0.89% |
| API credits used | 36 |

---

## Disclaimer

This project is built for **educational and research purposes only**. Arbitrage betting may violate the terms of service of individual sportsbooks and can result in account limitations or closures. No real money is placed by this software. The authors accept no liability for any financial loss arising from use of this tool. Always verify local regulations and gamble responsibly within the laws of your jurisdiction.

