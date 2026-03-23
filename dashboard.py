"""
Streamlit dashboard for the arb-bot paper trading session.

Reads paper_trades.csv and renders three panels: summary KPI metrics,
a cumulative profit line chart over time, a sortable table of all logged
arb opportunities, and a bookmaker frequency bar chart. Run with:
    streamlit run dashboard.py
"""

import os

import pandas as pd
import streamlit as st

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trades.csv")

st.set_page_config(page_title="Arb Bot Dashboard", layout="wide")
st.title("Arb Bot — Paper Trading Dashboard")

# ── Load data ────────────────────────────────────────────────────────────────

if not os.path.exists(CSV_PATH):
    st.warning("No paper_trades.csv found. Run main.py to start logging arbs.")
    st.stop()

df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"])

if df.empty:
    st.info("CSV exists but no trades have been logged yet.")
    st.stop()

df["guaranteed_profit"] = pd.to_numeric(df["guaranteed_profit"])
df["roi_pct"] = pd.to_numeric(df["roi_pct"])
df = df.sort_values("timestamp")

# ── Summary metrics ──────────────────────────────────────────────────────────

total_opps = len(df)
total_profit = df["guaranteed_profit"].sum()
avg_roi = df["roi_pct"].mean()

col1, col2, col3 = st.columns(3)
col1.metric("Total Opportunities", total_opps)
col2.metric("Total Simulated Profit", f"${total_profit:,.2f}")
col3.metric("Average ROI", f"{avg_roi:.4f}%")

st.divider()

# ── Cumulative profit chart ───────────────────────────────────────────────────

st.subheader("Cumulative Profit Over Time")
cumulative = df[["timestamp", "guaranteed_profit"]].copy()
cumulative["cumulative_profit"] = cumulative["guaranteed_profit"].cumsum()
st.line_chart(cumulative.set_index("timestamp")["cumulative_profit"])

st.divider()

# ── All arbs table ────────────────────────────────────────────────────────────

st.subheader("All Logged Arbs (sorted by ROI)")
display_cols = [
    "timestamp", "sport", "game", "team_a", "book_a", "odds_a",
    "team_b", "book_b", "odds_b", "stake_a", "stake_b",
    "guaranteed_profit", "roi_pct", "arb_pct", "status",
]
st.dataframe(
    df[display_cols].sort_values("roi_pct", ascending=False).reset_index(drop=True),
    use_container_width=True,
)

st.divider()

# ── Bookmaker frequency ───────────────────────────────────────────────────────

st.subheader("Bookmaker Appearances in Arbs")
book_counts = (
    pd.concat([df["book_a"], df["book_b"]])
    .value_counts()
    .rename_axis("bookmaker")
    .reset_index(name="appearances")
)
st.bar_chart(book_counts.set_index("bookmaker")["appearances"])
