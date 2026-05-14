"""Backtesting dashboard page."""
import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def render():
    st.title("🔬 Backtesting")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        pair = st.selectbox("Pair", [
            "EUR_USD","GBP_USD","USD_JPY","AUD_USD","USD_CHF",
            "NZD_USD","USD_CAD","XAU_USD","GBP_JPY","EUR_JPY",
        ])
    with col2:
        strategy = st.selectbox("Strategy", [
            "All","price_action","smc_strategy","trend_following","breakout",
            "mean_reversion","momentum","scalping","swing","ichimoku_strategy",
            "vwap_strategy","wyckoff","harmonic_strategy",
        ])
    with col3:
        years = st.slider("Years of data", 1, 10, 3)
    with col4:
        initial_balance = st.number_input("Initial Balance ($)", value=10000, step=1000)

    risk_pct = st.slider("Risk per trade (%)", 0.5, 3.0, 1.0, 0.5) / 100
    min_score = st.slider("Min confluence score", 50, 85, 65, 5)

    col_wf, col_mc = st.columns(2)
    with col_wf:
        run_walk_forward = st.checkbox("Walk-forward optimization (70/30 split)", value=False)
    with col_mc:
        run_monte_carlo = st.checkbox("Monte Carlo simulation (1000 runs)", value=False)

    if st.button("▶ Run Backtest", type="primary"):
        with st.spinner(f"Downloading {pair} data and running backtest..."):
            try:
                from backtest.data_downloader import DataDownloader
                from backtest.backtest_engine import BacktestEngine
                from backtest.report_generator import ReportGenerator

                downloader = DataDownloader()
                df = downloader.download_pair(pair, "H1", years, use_cache=True)

                if df.empty:
                    st.error("No data downloaded. Check your internet connection.")
                    return

                st.success(f"Downloaded {len(df)} bars for {pair}")

                engine = BacktestEngine(
                    initial_balance=initial_balance,
                    risk_pct=risk_pct,
                    min_score=min_score,
                )
                strategy_name = None if strategy == "All" else strategy
                result = engine.run(pair, df, strategy_name)
                summary = result.get_summary()

                reporter = ReportGenerator()

                # Summary metrics
                st.subheader("📊 Results")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Trades", summary.get("total_trades", 0))
                m2.metric("Win Rate", f"{summary.get('win_rate',0)*100:.1f}%")
                m3.metric("Profit Factor", f"{summary.get('profit_factor',0):.2f}")
                m4.metric("Net Profit", f"${summary.get('net_profit',0):+.2f}")

                m5, m6, m7, m8 = st.columns(4)
                m5.metric("Max Drawdown", f"{summary.get('max_drawdown_pct',0)*100:.1f}%")
                m6.metric("Sharpe Ratio", f"{summary.get('sharpe_ratio',0):.2f}")
                m7.metric("Sortino Ratio", f"{summary.get('sortino_ratio',0):.2f}")
                m8.metric("CAGR", f"{summary.get('cagr',0)*100:.1f}%")

                # Charts
                if result.equity_curve:
                    eq_fig = reporter._equity_curve_chart(result, pair)
                    st.plotly_chart(eq_fig, use_container_width=True)

                    dd_fig = reporter._drawdown_chart(result)
                    st.plotly_chart(dd_fig, use_container_width=True)

                if result.trades:
                    monthly_fig = reporter._monthly_heatmap(result)
                    if monthly_fig.data:
                        st.plotly_chart(monthly_fig, use_container_width=True)

                # Walk-forward
                if run_walk_forward:
                    st.subheader("🔄 Walk-Forward Optimization")
                    with st.spinner("Running walk-forward..."):
                        from backtest.walk_forward import WalkForwardOptimizer
                        wf = WalkForwardOptimizer(initial_balance=initial_balance, risk_pct=risk_pct)
                        wf_result = wf.run(pair, df, strategy_name)
                        st.json({
                            "best_threshold": wf_result["best_threshold"],
                            "test_summary": wf_result["test_summary"],
                            "is_robust": wf_result["is_robust"],
                        })

                # Monte Carlo
                if run_monte_carlo and result.trades:
                    st.subheader("🎲 Monte Carlo Simulation")
                    with st.spinner("Running 1000 simulations..."):
                        from backtest.monte_carlo import MonteCarloSimulator
                        mc = MonteCarloSimulator(1000, initial_balance)
                        mc_result = mc.run_from_backtest_result(result)
                        col_mc1, col_mc2, col_mc3 = st.columns(3)
                        col_mc1.metric("Prob. of Profit", f"{mc_result.get('probability_of_profit',0)*100:.1f}%")
                        col_mc2.metric("Prob. of Ruin (50% loss)", f"{mc_result.get('probability_of_ruin',0)*100:.1f}%")
                        col_mc3.metric("Expected Return", f"{mc_result.get('expected_return_pct',0):.1f}%")
                        fb = mc_result.get("final_balance", {})
                        st.write(f"Balance range (5th–95th pct): ${fb.get('p5',0):.0f} – ${fb.get('p95',0):.0f}")

                # Trade table
                if result.trades:
                    st.subheader("Trade Log")
                    trades_df = pd.DataFrame(result.trades)
                    st.dataframe(trades_df.head(200), use_container_width=True, hide_index=True)

            except Exception as e:
                st.error(f"Backtest error: {e}")
                import traceback
                st.code(traceback.format_exc())
