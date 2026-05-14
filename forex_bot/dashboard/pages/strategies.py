"""Strategy Performance dashboard page."""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def render():
    st.title("🧠 Strategy Performance")

    try:
        from scoring.adaptive_weighting import AdaptiveWeighting
        adaptive = AdaptiveWeighting()
        perf_table = adaptive.get_performance_table()
        weights = adaptive.get_all_weights()
    except Exception as e:
        st.error(f"Error loading strategy data: {e}")
        perf_table = []
        weights = {}

    if not perf_table:
        st.info("No strategy performance data yet. Run trades to populate this page.")
        _show_placeholder(weights)
        return

    df = pd.DataFrame(perf_table)

    # Summary table
    st.subheader("Strategy Performance Table")
    display_cols = ["strategy", "trades", "win_rate", "profit_factor", "avg_rr", "total_pnl", "weight"]
    available_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available_cols].style.format({
        "win_rate": "{:.1%}",
        "profit_factor": "{:.2f}",
        "avg_rr": "{:.2f}",
        "total_pnl": "${:+.2f}",
        "weight": "{:.2f}",
    }), use_container_width=True, hide_index=True)

    # Bar chart comparison
    if "total_pnl" in df.columns and "strategy" in df.columns:
        st.subheader("P&L by Strategy")
        fig = go.Figure(go.Bar(
            x=df["strategy"],
            y=df["total_pnl"],
            marker_color=["green" if v >= 0 else "red" for v in df.get("total_pnl", [])],
        ))
        fig.update_layout(template="plotly_dark", height=350, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    # Adaptive weights
    st.subheader("Adaptive Weights")
    if weights:
        weight_df = pd.DataFrame(
            [{"Strategy": k, "Weight": v, "Status": "Active" if v >= 0.3 else "Reduced"}
             for k, v in weights.items()]
        )
        fig2 = px.bar(weight_df, x="Strategy", y="Weight",
                      color="Status",
                      color_discrete_map={"Active": "#00d4ff", "Reduced": "#ff6b6b"},
                      template="plotly_dark", height=300)
        fig2.add_hline(y=1.0, line_dash="dash", line_color="white", annotation_text="Default")
        st.plotly_chart(fig2, use_container_width=True)

    if st.button("🔄 Update Adaptive Weights"):
        try:
            from scoring.adaptive_weighting import AdaptiveWeighting
            AdaptiveWeighting().update_weights()
            st.success("Weights updated!")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")


def _show_placeholder(weights):
    """Show weight display when no trades yet."""
    st.subheader("Strategy Weights (No trades yet)")
    if weights:
        df = pd.DataFrame(
            [{"Strategy": k, "Weight": v} for k, v in weights.items()]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        strategies = [
            "price_action","smc_strategy","trend_following","breakout",
            "mean_reversion","momentum","scalping","swing","ichimoku_strategy",
            "vwap_strategy","wyckoff","harmonic_strategy","session_strategy",
            "news_strategy","multi_tf_strategy","carry_trade","grid",
        ]
        df = pd.DataFrame([{"Strategy": s, "Weight": 1.0, "Trades": 0, "Win Rate": "—"} for s in strategies])
        st.dataframe(df, use_container_width=True, hide_index=True)
