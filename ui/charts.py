"""
Streamlit UI components for the Historical Institutional Flow Engine.
Meant to be imported into the existing Phoenix Scanner Streamlit app
(same pattern as its other pages) — this module only renders, it does not
own any business logic, which all lives in analysis/, ranking/, backtesting/.
"""
from __future__ import annotations
from ranking.ranking_engine import rank_symbols, RankedSymbol

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data.database import Database
from analysis.flow_trend import classify_flow_trend, FlowTrend
from analysis.detection import detect_early_accumulation, detect_distribution
from ranking.ranking_engine import rank_symbols
from backtesting.backtest_engine import run_backtest

_TREND_COLOR = {
    FlowTrend.STRONGLY_INCREASING: "#0f9d58",
    FlowTrend.INCREASING: "#34a853",
    FlowTrend.STABLE: "#9aa0a6",
    FlowTrend.WEAKENING: "#f4b400",
    FlowTrend.STRONGLY_WEAKENING: "#db4437",
    FlowTrend.INSUFFICIENT_DATA: "#9aa0a6",
}

_PERIOD_DAYS = {"7 Days": 7, "30 Days": 30, "90 Days": 90}


def render_symbol_history_page(db: Database, symbol: str) -> None:
    st.subheader(f"{symbol} — Institutional Flow History")

    period_label = st.radio("Period", list(_PERIOD_DAYS.keys()), horizontal=True, index=1)
    days = _PERIOD_DAYS[period_label]

    rows = db.get_history(symbol, days)
    if not rows:
        st.warning("No historical data stored for this symbol yet. Run the daily update pipeline first.")
        return

    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])

    flow_scores = df["institutional_flow_score"].dropna().tolist()
    prices = df["price"].dropna().tolist()
    relvols = df["relative_volume"].dropna().tolist()

    trend, slope = classify_flow_trend(flow_scores)
    _render_badges(trend, slope, flow_scores, prices, relvols)
    _render_chart(df, symbol)


def _render_badges(trend: FlowTrend, slope: float, flow_scores: list[float],
                    prices: list[float], relvols: list[float]) -> None:
    cols = st.columns(3)

    with cols[0]:
        color = _TREND_COLOR[trend]
        st.markdown(
            f"**Flow Trend:** <span style='color:{color};font-weight:600'>{trend.value}</span> "
            f"({slope:+.2f} pts/session)",
            unsafe_allow_html=True,
        )

    accumulation = detect_early_accumulation(flow_scores, prices, relvols)
    with cols[1]:
        if accumulation.triggered:
            st.success("🟢 Early Institutional Accumulation")
            st.caption(accumulation.reason)

    distribution = detect_distribution(flow_scores, prices, relvols)
    with cols[2]:
        if distribution.triggered:
            st.error("🔴 Institutional Distribution")
            st.caption(distribution.reason)


def _render_chart(df: pd.DataFrame, symbol: str) -> None:
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.4, 0.35, 0.25],
        subplot_titles=("Institutional Flow Score", "Price", "Volume"),
    )

    fig.add_trace(
        go.Scatter(x=df["date"], y=df["institutional_flow_score"], mode="lines",
                    line=dict(color="#4285f4", width=2), name="Flow Score"),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["date"], y=df["price"], mode="lines",
                    line=dict(color="#0f9d58", width=2), name="Price"),
        row=2, col=1,
    )
    fig.add_trace(
        go.Bar(x=df["date"], y=df["volume"], marker_color="#9aa0a6", name="Volume"),
        row=3, col=1,
    )

    fig.update_layout(height=650, showlegend=False, margin=dict(t=40, b=20),
                       title=f"{symbol} — Flow Score / Price / Volume")
    st.plotly_chart(fig, use_container_width=True)


def render_ranking_page(db: Database) -> None:
    st.subheader("Institutional Flow Ranking")
    st.caption("Ranked by Flow Score → Flow Trend → Relative Volume → Trend Strength → Momentum (not price).")

    hide_moved = st.checkbox("إخفاء الأسهم التي تحركت بالفعل بشكل كبير مؤخرًا (Already Moved)", value=False)

    ranked = rank_symbols(db)
    if not ranked:
        st.warning("No symbols in the database yet.")
        return

    if hide_moved:
        ranked = [r for r in ranked if not r.already_moved]
        ranked = [RankedSymbol(**{**vars(r), "rank": i + 1}) for i, r in enumerate(ranked)]

    table = pd.DataFrame([{
        "Rank": r.rank,
        "Symbol": r.symbol,
        "Flow Score": r.flow_score,
        "Flow Trend": r.flow_trend.value,
        "Accumulation Streak": r.accumulation_streak,
        "Recent Move %": r.recent_move_pct,
        "Already Moved": "⚠️ نعم" if r.already_moved else "لا",
        "Relative Volume": round(r.relative_volume, 2),
        "Trend Strength": round(r.trend_strength, 2),
        "Momentum %": round(r.momentum_pct, 2),
    } for r in ranked])

    st.dataframe(table, use_container_width=True, hide_index=True)


def render_backtest_page(db: Database) -> None:
    st.subheader("Strategy Backtest — Early Accumulation Signal")

    symbols = ["All symbols"] + db.get_all_symbols()
    choice = st.selectbox("Symbol", symbols)
    symbol = None if choice == "All symbols" else choice

    if st.button("Run Backtest"):
        with st.spinner("Replaying history..."):
            report = run_backtest(db, symbol)
        summary = report.summary()

        cols = st.columns(4)
        cols[0].metric("Signals", summary["total_signals"])
        cols[1].metric("Trades", summary["total_trades"])
        cols[2].metric("Win Rate", f"{summary['win_rate_pct']}%")
        cols[3].metric("Profit Factor", summary["profit_factor"])

        cols2 = st.columns(4)
        cols2[0].metric("Avg Profit", f"{summary['avg_profit_pct']}%")
        cols2[1].metric("Avg Loss", f"{summary['avg_loss_pct']}%")
        cols2[2].metric("Max Drawdown", f"{summary['max_drawdown_pct']}%")
        cols2[3].metric("Sharpe Ratio", summary["sharpe_ratio"])

        if report.trades:
            trades_df = pd.DataFrame([vars(t) for t in report.trades])
            st.dataframe(trades_df, use_container_width=True, hide_index=True)
        else:
            st.info("No trades were generated by this signal over the stored history.")
