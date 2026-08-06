import streamlit as st
from data.database import get_database
from data.providers.polygon_provider import PolygonProvider
from pipeline import run_daily_update
from ui.charts import render_symbol_history_page, render_ranking_page, render_backtest_page

st.set_page_config(page_title="Phoenix Flow Engine", layout="wide")

db = get_database()

st.sidebar.title("Phoenix Flow Engine")

st.sidebar.subheader("Daily Update")
symbols_input = st.sidebar.text_area("Symbols (comma separated)", "AAPL, TSLA, SILO")
if st.sidebar.button("Run Update Now"):
    symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
    provider = PolygonProvider()
    with st.spinner(f"Updating {len(symbols)} symbols..."):
        result = run_daily_update(symbols, provider)
    st.sidebar.success(f"Updated: {len(result['updated'])} | Failed: {len(result['failed'])}")
    if result["failed"]:
        st.sidebar.warning(f"Failed symbols: {result['failed']}")
    if result["alerts"]:
        st.sidebar.info(f"{len(result['alerts'])} alerts triggered")

st.sidebar.divider()
page = st.sidebar.radio("Page", ["Symbol History", "Ranking", "Backtest"])

if page == "Symbol History":
    symbol = st.text_input("Symbol", "AAPL")
    render_symbol_history_page(db, symbol)
elif page == "Ranking":
    render_ranking_page(db)
else:
    render_backtest_page(db)
