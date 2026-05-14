"""Live Overview dashboard page."""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def render():
    st.title("📊 Live Overview")

    # Account metrics row
    try:
        from database.db import DatabaseManager
        db = DatabaseManager()
        open_trades = db.get_open_trades()
        daily_stats = db.get_daily_stats(days=30)
    except Exception:
        open_trades = []
        daily_stats = []

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Account Balance", "$10,000.00", "+$0.00")
    with col2:
        st.metric("Open Trades", len(open_trades))
    with col3:
        today_pnl = sum(s.pnl_usd or 0 for s in daily_stats[-1:]) if daily_stats else 0
        st.metric("Today P&L", f"${today_pnl:+.2f}", delta_color="normal")
    with col4:
        st.metric("Mode", "PAPER" if os.getenv("PAPER_TRADING","true").lower()=="true" else "LIVE")

    st.markdown("---")

    # Equity curve
    st.subheader("Equity Curve")
    if daily_stats:
        dates = [s.date for s in daily_stats]
        balances = [s.ending_balance or 10000 for s in daily_stats]
    else:
        dates = [datetime.now().date()]
        balances = [10000]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=balances, mode="lines+markers",
        line=dict(color="#00d4ff", width=2),
        fill="tonexty", fillcolor="rgba(0,212,255,0.1)",
        name="Balance",
    ))
    fig.update_layout(
        template="plotly_dark", height=300,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="Date", yaxis_title="Balance ($)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Open trades table
    st.subheader("Open Trades")
    if open_trades:
        rows = []
        for t in open_trades:
            rows.append({
                "ID": t.trade_id,
                "Pair": t.pair,
                "Direction": t.direction,
                "Entry": f"{t.entry_price:.5f}",
                "SL": f"{t.sl_price:.5f}",
                "TP1": f"{t.tp1_price:.5f}",
                "Strategy": t.strategy_name,
                "Score": f"{t.confluence_score:.1f}",
                "Session": t.session or "",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No open trades")

    # Live prices
    st.subheader("Live Prices")
    pairs = ["EUR_USD","GBP_USD","USD_JPY","AUD_USD","USD_CHF","NZD_USD","USD_CAD","XAU_USD"]
    price_cols = st.columns(4)
    for i, pair in enumerate(pairs):
        with price_cols[i % 4]:
            st.metric(pair.replace("_","/"), "—", help="Live price from OANDA feed")

    st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S UTC')}")
    if st.button("🔄 Refresh"):
        st.rerun()
