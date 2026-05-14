"""Trade Journal dashboard page."""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def render():
    st.title("📓 Trade Journal")

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        pairs = ["All","EUR_USD","GBP_USD","USD_JPY","AUD_USD","USD_CHF","NZD_USD","USD_CAD","XAU_USD","GBP_JPY","EUR_JPY"]
        pair_filter = st.selectbox("Pair", pairs)
    with col2:
        strategies = ["All","price_action","smc_strategy","trend_following","breakout",
                      "mean_reversion","momentum","scalping","swing","ichimoku_strategy",
                      "vwap_strategy","wyckoff","harmonic_strategy","session_strategy",
                      "news_strategy","multi_tf_strategy"]
        strategy_filter = st.selectbox("Strategy", strategies)
    with col3:
        result_filter = st.selectbox("Result", ["All","WIN","LOSS","BREAKEVEN"])
    with col4:
        days_back = st.number_input("Days back", min_value=1, max_value=365, value=30)

    try:
        from database.db import DatabaseManager
        db = DatabaseManager()
        start_date = datetime.now() - timedelta(days=days_back)
        trades = db.get_trades(
            pair=None if pair_filter == "All" else pair_filter,
            strategy=None if strategy_filter == "All" else strategy_filter,
            result=None if result_filter == "All" else result_filter,
            start_date=start_date,
        )
    except Exception as e:
        st.error(f"Database error: {e}")
        trades = []

    if not trades:
        st.info("No trades found for the selected filters.")
        return

    rows = []
    for t in trades:
        rows.append({
            "ID": t.trade_id,
            "Time": str(t.entry_time)[:16] if t.entry_time else "",
            "Pair": t.pair,
            "TF": t.timeframe,
            "Dir": t.direction,
            "Entry": f"{t.entry_price:.5f}" if t.entry_price else "",
            "Exit": f"{t.exit_price:.5f}" if t.exit_price else "",
            "Strategy": t.strategy_name,
            "Score": f"{t.confluence_score:.1f}" if t.confluence_score else "",
            "SL Pips": f"{t.sl_pips:.1f}" if t.sl_pips else "",
            "Pips": f"{t.pips_result:+.1f}" if t.pips_result else "",
            "P&L $": f"${t.pnl_usd:+.2f}" if t.pnl_usd else "",
            "RR": f"{t.actual_rr:.2f}" if t.actual_rr else "",
            "Result": t.result or "",
            "Exit Reason": t.exit_reason or "",
        })

    df = pd.DataFrame(rows)

    # Summary stats
    total = len(trades)
    wins = sum(1 for t in trades if t.result == "WIN")
    losses = sum(1 for t in trades if t.result == "LOSS")
    total_pnl = sum(t.pnl_usd or 0 for t in trades)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Trades", total)
    c2.metric("Win Rate", f"{wins/total*100:.1f}%" if total else "—")
    c3.metric("Net P&L", f"${total_pnl:+.2f}")
    c4.metric("Wins/Losses", f"{wins}/{losses}")
    st.markdown("---")

    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "Result": st.column_config.TextColumn(
                "Result",
                help="WIN/LOSS/BREAKEVEN",
            ),
        }
    )

    # Export
    csv = df.to_csv(index=False)
    st.download_button(
        label="📥 Export to CSV",
        data=csv,
        file_name=f"trades_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

    # Trade detail expander
    if trades:
        st.subheader("Trade Detail")
        selected_id = st.selectbox("Select Trade ID", [t.trade_id for t in trades])
        trade = next((t for t in trades if t.trade_id == selected_id), None)
        if trade:
            with st.expander("Full Trade Details", expanded=True):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write(f"**ID:** {trade.trade_id}")
                    st.write(f"**Pair:** {trade.pair} | **TF:** {trade.timeframe}")
                    st.write(f"**Direction:** {trade.direction}")
                    st.write(f"**Strategy:** {trade.strategy_name}")
                    st.write(f"**Pattern:** {trade.pattern_detected or '—'}")
                    st.write(f"**SMC:** {trade.smc_concept or '—'}")
                    st.write(f"**Score:** {trade.confluence_score:.1f}/100")
                    st.write(f"**Session:** {trade.session or '—'}")
                with col_b:
                    st.write(f"**Entry:** {trade.entry_price:.5f} at {trade.entry_time}")
                    st.write(f"**SL:** {trade.sl_price:.5f} ({trade.sl_pips:.1f} pips)")
                    st.write(f"**TP1:** {trade.tp1_price:.5f}")
                    st.write(f"**TP2:** {trade.tp2_price:.5f}")
                    st.write(f"**TP3:** {trade.tp3_price:.5f}")
                    st.write(f"**Exit:** {trade.exit_price} | {trade.exit_reason}")
                    st.write(f"**Result:** {trade.result} | RR: {trade.actual_rr:.2f}")
                    st.write(f"**P&L:** ${trade.pnl_usd:+.2f} ({trade.pips_result:+.1f} pips)")
