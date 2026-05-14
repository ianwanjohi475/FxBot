"""Risk Monitor dashboard page."""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def render():
    st.title("🛡️ Risk Monitor")

    try:
        from database.db import DatabaseManager
        db = DatabaseManager()
        open_trades = db.get_open_trades()
        daily_stats = db.get_daily_stats(days=7)
    except Exception:
        open_trades = []
        daily_stats = []

    # Daily P&L gauge
    initial_balance = 10000
    today_pnl = 0
    today_pnl_pct = 0
    if daily_stats:
        today = daily_stats[-1]
        today_pnl = today.pnl_usd or 0
        today_pnl_pct = today_pnl / initial_balance * 100

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Daily P&L")
        fig_pnl = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=today_pnl_pct,
            title={"text": "Daily P&L (%)"},
            delta={"reference": 0},
            gauge={
                "axis": {"range": [-5, 5]},
                "bar": {"color": "green" if today_pnl_pct >= 0 else "red"},
                "steps": [
                    {"range": [-5, -3], "color": "#ff4444"},
                    {"range": [-3, 0], "color": "#ff9944"},
                    {"range": [0, 3], "color": "#44bb44"},
                    {"range": [3, 5], "color": "#22aa22"},
                ],
                "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": -5},
            },
            number={"suffix": "%", "font": {"size": 30}},
        ))
        fig_pnl.update_layout(template="plotly_dark", height=300, margin=dict(l=20,r=20,t=30,b=0))
        st.plotly_chart(fig_pnl, use_container_width=True)

    with col2:
        st.subheader("Drawdown Meter")
        max_dd = 0  # Would calculate from equity curve
        fig_dd = go.Figure(go.Indicator(
            mode="gauge+number",
            value=abs(max_dd * 100),
            title={"text": "Max Drawdown (%)"},
            gauge={
                "axis": {"range": [0, 10]},
                "bar": {"color": "#ff6600"},
                "steps": [
                    {"range": [0, 3], "color": "#22aa22"},
                    {"range": [3, 5], "color": "#ff9944"},
                    {"range": [5, 10], "color": "#ff4444"},
                ],
                "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": 5},
            },
            number={"suffix": "%"},
        ))
        fig_dd.update_layout(template="plotly_dark", height=300, margin=dict(l=20,r=20,t=30,b=0))
        st.plotly_chart(fig_dd, use_container_width=True)

    st.markdown("---")

    # Warning / Stop indicators
    c1, c2, c3 = st.columns(3)
    with c1:
        warn_color = "🟡" if abs(today_pnl_pct) > 3 else "🟢"
        st.metric(f"{warn_color} Warning Threshold (3%)", f"{3.0:.1f}%")
    with c2:
        stop_color = "🔴" if abs(today_pnl_pct) >= 5 else "🟢"
        st.metric(f"{stop_color} Hard Stop (5%)", "5.0%")
    with c3:
        st.metric("Open Trade Risk", f"${len(open_trades) * initial_balance * 0.01:.0f}")

    st.markdown("---")

    # Open trades risk table
    st.subheader("Open Trade Exposure")
    if open_trades:
        rows = [{
            "ID": t.trade_id,
            "Pair": t.pair,
            "Direction": t.direction,
            "Risk $": f"${t.risk_amount_usd:.2f}" if t.risk_amount_usd else "—",
            "Risk %": f"{t.risk_pct*100:.2f}%" if t.risk_pct else "—",
        } for t in open_trades]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No open trades")

    # Correlation heatmap
    st.subheader("Pair Correlation Heatmap")
    pairs = ["EUR_USD","GBP_USD","USD_JPY","AUD_USD","USD_CHF","NZD_USD","USD_CAD","XAU_USD"]
    # Show a pre-computed approximate correlation matrix
    import numpy as np
    n = len(pairs)
    corr = np.eye(n)
    corr[0,1] = corr[1,0] = 0.85   # EUR/USD - GBP/USD
    corr[0,2] = corr[2,0] = -0.7   # EUR/USD - USD/JPY
    corr[3,6] = corr[6,3] = 0.75   # AUD/USD - NZD/USD
    corr[1,4] = corr[4,1] = -0.65  # GBP/USD - USD/CHF

    fig_corr = px.imshow(
        corr, x=pairs, y=pairs,
        color_continuous_scale="RdBu",
        color_continuous_midpoint=0,
        zmin=-1, zmax=1,
        title="Approximate Pair Correlation",
    )
    fig_corr.update_layout(template="plotly_dark", height=400)
    st.plotly_chart(fig_corr, use_container_width=True)

    if st.button("🔄 Refresh"):
        st.rerun()
