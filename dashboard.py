"""
Streamlit dashboard for the arb-bot paper trading session.

Two tabs:
  - Arb Opportunities: summary KPIs, cumulative profit chart, arb table,
    and bookmaker frequency chart.
  - Account Manager: per-account balance bar chart, stats table, bankroll
    over time, rebalance warnings, and win rate per bookmaker.

Run with:
    streamlit run dashboard.py
"""

import json
import os

import altair as alt
import pandas as pd
import streamlit as st

import config
from paper_trader import account_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "paper_trades.csv")
ACCOUNTS_PATH = os.path.join(BASE_DIR, "paper_trader", "accounts.json")
TRADES_PATH = os.path.join(BASE_DIR, "paper_trader", "simulation_trades.csv")

REBALANCE_THRESHOLD = config.LOW_BALANCE_THRESHOLD
PENDING_PATH = os.path.join(BASE_DIR, "paper_trader", "pending_bets.json")

st.set_page_config(page_title="Arb Bot Dashboard", layout="wide")
st.title("Arb Bot — Paper Trading Dashboard")

tab_arbs, tab_accounts = st.tabs(["Arb Opportunities", "Account Manager"])

# ── TAB 1: Arb Opportunities ──────────────────────────────────────────────────

with tab_arbs:
    if not os.path.exists(CSV_PATH):
        st.warning("No paper_trades.csv found. Run main.py to start logging arbs.")
    else:
        df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"])
        if df.empty:
            st.info("CSV exists but no trades have been logged yet.")
        else:
            df["guaranteed_profit"] = pd.to_numeric(df["guaranteed_profit"])
            df["roi_pct"] = pd.to_numeric(df["roi_pct"])
            df = df.sort_values("timestamp")

            total_opps = len(df)
            total_profit = df["guaranteed_profit"].sum()
            avg_roi = df["roi_pct"].mean()

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Opportunities", total_opps)
            col2.metric("Total Simulated Profit", f"${total_profit:,.2f}")
            col3.metric("Average ROI", f"{avg_roi:.4f}%")

            st.divider()

            st.subheader("Cumulative Profit Over Time")
            cumulative = df[["timestamp", "guaranteed_profit"]].copy()
            cumulative["cumulative_profit"] = cumulative["guaranteed_profit"].cumsum()
            st.line_chart(cumulative.set_index("timestamp")["cumulative_profit"])

            st.divider()

            st.subheader("All Logged Arbs (sorted by ROI)")
            display_cols = [
                "timestamp", "sport", "game", "team_a", "book_a", "odds_a",
                "team_b", "book_b", "odds_b", "stake_a", "stake_b",
                "guaranteed_profit", "roi_pct", "arb_pct", "status",
            ]
            available = [c for c in display_cols if c in df.columns]
            st.dataframe(
                df[available].sort_values("roi_pct", ascending=False).reset_index(drop=True),
                use_container_width=True,
            )

            st.divider()

            st.subheader("Bookmaker Appearances in Arbs")
            book_cols = [c for c in ("book_a", "book_b", "book_c") if c in df.columns]
            book_counts = (
                pd.concat([df[c] for c in book_cols]).dropna()
                .value_counts()
                .rename_axis("bookmaker")
                .reset_index(name="appearances")
            )
            st.bar_chart(book_counts.set_index("bookmaker")["appearances"])

# ── TAB 2: Account Manager ────────────────────────────────────────────────────

with tab_accounts:
    if not os.path.exists(ACCOUNTS_PATH):
        st.warning("No accounts.json found. Run main.py once to initialise accounts.")
        st.stop()

    with open(ACCOUNTS_PATH) as f:
        raw_accounts = json.load(f)

    for acct in raw_accounts.values():
        acct.setdefault("transferred_in", 0.0)
        acct.setdefault("transferred_out", 0.0)
    acct_df = pd.DataFrame(raw_accounts.values())
    acct_df["net_profit"] = [account_manager.net_pl(a) for a in raw_accounts.values()]
    acct_df["roi_pct"] = (
        acct_df["net_profit"] / acct_df["total_deposited"] * 100
    ).round(4)

    STARTING_BANKROLL = account_manager.starting_bankroll(raw_accounts)
    open_stakes = 0.0
    if os.path.exists(PENDING_PATH):
        with open(PENDING_PATH) as f:
            open_stakes = round(sum(leg["stake"] for bet in json.load(f) for leg in bet["legs"]), 2)
    # Money in open bets is still yours until they settle
    current_bankroll = round(float(acct_df["balance"].sum()) + open_stakes, 2)
    net_total = round(current_bankroll - STARTING_BANKROLL, 2)
    total_bets = int(acct_df["bet_count"].sum())
    low_count = int((acct_df["balance"] < REBALANCE_THRESHOLD).sum())

    # ── KPI row ───────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Bankroll", f"${current_bankroll:,.2f}",
              delta=f"{'+' if net_total >= 0 else ''}{net_total:.2f}")
    k2.metric("Starting Bankroll", f"${STARTING_BANKROLL:,.2f}")
    k3.metric("Total Bets Placed", total_bets)
    k4.metric("Accounts Needing Rebalance", low_count,
              delta_color="inverse" if low_count > 0 else "off",
              delta=f"{low_count} below ${REBALANCE_THRESHOLD:.0f}" if low_count else "All healthy")

    st.divider()

    # ── Rebalance warning box ─────────────────────────────────────────────────
    low_accts = acct_df[acct_df["balance"] < REBALANCE_THRESHOLD].sort_values("balance")
    if not low_accts.empty:
        high_acct = acct_df.loc[acct_df["balance"].idxmax()]
        lines = []
        for _, row in low_accts.iterrows():
            needed = round(REBALANCE_THRESHOLD - row["balance"], 2)
            surplus = round(high_acct["balance"] - REBALANCE_THRESHOLD, 2)
            transfer = min(needed, surplus) if surplus > 0 else 0
            if transfer > 0:
                lines.append(
                    f"⚠️ **{row['name']}** — ${row['balance']:.2f} "
                    f"(transfer ${transfer:.2f} from {high_acct['name']} @ ${high_acct['balance']:.2f})"
                )
            else:
                lines.append(f"⚠️ **{row['name']}** — ${row['balance']:.2f} (no surplus available)")
        with st.container(border=True):
            st.markdown("### Rebalance Needed")
            for line in lines:
                st.markdown(line)
    else:
        st.success("All accounts are above the rebalance threshold.")

    st.divider()

    # ── Balance bar chart with threshold line ─────────────────────────────────
    st.subheader("Account Balances")

    bar = (
        alt.Chart(acct_df)
        .mark_bar()
        .encode(
            x=alt.X("name:N", sort="-y", title="Bookmaker",
                    axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("balance:Q", title="Balance ($)"),
            color=alt.condition(
                alt.datum.balance < REBALANCE_THRESHOLD,
                alt.value("#e74c3c"),
                alt.value("#2ecc71"),
            ),
            tooltip=["name", "balance", "net_profit", "bet_count"],
        )
    )
    threshold_line = (
        alt.Chart(pd.DataFrame({"threshold": [REBALANCE_THRESHOLD]}))
        .mark_rule(color="red", strokeDash=[6, 3], strokeWidth=2)
        .encode(y="threshold:Q")
    )
    st.altair_chart(bar + threshold_line, use_container_width=True)

    st.divider()

    # ── Per-account stats table ───────────────────────────────────────────────
    st.subheader("Account Statistics")
    table_df = acct_df[
        ["name", "balance", "bet_count", "total_wagered", "net_profit", "roi_pct"]
    ].copy()
    table_df.columns = ["Bookmaker", "Balance ($)", "Bets", "Total Wagered ($)", "Net Profit ($)", "ROI (%)"]
    table_df = table_df.sort_values("Balance ($)", ascending=False).reset_index(drop=True)
    st.dataframe(
        table_df.style.format({
            "Balance ($)": "{:.2f}",
            "Total Wagered ($)": "{:.2f}",
            "Net Profit ($)": "{:+.2f}",
            "ROI (%)": "{:.4f}",
        }),
        use_container_width=True,
    )

    st.divider()

    # ── Bankroll over time & win rate (require simulation_trades.csv) ─────────
    if not os.path.exists(TRADES_PATH):
        st.info("No simulation_trades.csv yet — run a few cycles to populate these charts.")
    else:
        sim_df = pd.read_csv(TRADES_PATH, parse_dates=["timestamp"])

        if sim_df.empty:
            st.info("simulation_trades.csv exists but has no rows yet.")
        else:
            # ── Total bankroll over time ──────────────────────────────────────
            st.subheader("Total Bankroll Over Time")
            bankroll_chart = (
                alt.Chart(sim_df.reset_index())
                .mark_line(point=True)
                .encode(
                    x=alt.X("timestamp:T", title="Time"),
                    y=alt.Y("total_bankroll_after:Q", title="Bankroll ($)",
                            scale=alt.Scale(zero=False)),
                    tooltip=["timestamp", "total_bankroll_after", "game", "net_profit"],
                )
            )
            start_line = (
                alt.Chart(pd.DataFrame({"start": [STARTING_BANKROLL]}))
                .mark_rule(color="gray", strokeDash=[4, 4])
                .encode(y="start:Q")
            )
            st.altair_chart(bankroll_chart + start_line, use_container_width=True)

            st.divider()

            # ── Win rate per bookmaker ────────────────────────────────────────
            st.subheader("Win Rate per Bookmaker")

            all_books = pd.concat([
                sim_df[[c, "winning_book"]].rename(columns={c: "book"})
                for c in ("book_a", "book_b", "book_c") if c in sim_df.columns
            ]).dropna(subset=["book"])
            all_books["won"] = all_books["book"] == all_books["winning_book"]
            win_rate = (
                all_books.groupby("book")["won"]
                .agg(wins="sum", total="count")
                .reset_index()
            )
            win_rate["win_rate_pct"] = (win_rate["wins"] / win_rate["total"] * 100).round(1)

            win_chart = (
                alt.Chart(win_rate)
                .mark_bar()
                .encode(
                    x=alt.X("book:N", sort="-y", title="Bookmaker",
                            axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y("win_rate_pct:Q", title="Win Rate (%)",
                            scale=alt.Scale(domain=[0, 100])),
                    color=alt.Color("win_rate_pct:Q",
                                    scale=alt.Scale(scheme="redyellowgreen",
                                                    domain=[30, 50, 70])),
                    tooltip=["book", "wins", "total", "win_rate_pct"],
                )
            )
            fifty_line = (
                alt.Chart(pd.DataFrame({"fifty": [50]}))
                .mark_rule(color="gray", strokeDash=[4, 4])
                .encode(y="fifty:Q")
            )
            st.altair_chart(win_chart + fifty_line, use_container_width=True)

            st.dataframe(
                win_rate.rename(columns={
                    "book": "Bookmaker",
                    "wins": "Wins",
                    "total": "Total Bets",
                    "win_rate_pct": "Win Rate (%)",
                }).sort_values("Win Rate (%)", ascending=False).reset_index(drop=True),
                use_container_width=True,
            )
