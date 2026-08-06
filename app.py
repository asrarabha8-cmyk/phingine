import streamlit as st
from data.database import get_database
from ui.charts import render_symbol_history_page, render_ranking_page, render_backtest_page

st.set_page_config(page_title="Phoenix Flow Engine", layout="wide")

db = get_database()

st.sidebar.title("Phoenix Flow Engine")
page = st.sidebar.radio("Page", ["Symbol History", "Ranking", "Backtest"])

if page == "Symbol History":
    symbol = st.text_input("Symbol", "AAPL")
    render_symbol_history_page(db, symbol)
elif page == "Ranking":
    render_ranking_page(db)
else:
    render_backtest_page(db)
