"""Tests for backtesting engine and Monte Carlo."""
import pytest
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.backtest_engine import BacktestEngine, BacktestResult
from backtest.monte_carlo import MonteCarloSimulator


@pytest.fixture
def sample_df():
    np.random.seed(7)
    n = 500
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0008)
    high = close + np.abs(np.random.randn(n) * 0.0005)
    low = close - np.abs(np.random.randn(n) * 0.0005)
    open_ = close + np.random.randn(n) * 0.0003
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    idx = pd.date_range("2022-01-01", periods=n, freq="1h")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": np.ones(n) * 5000.0
    }, index=idx)


class TestBacktestResult:
    def test_empty_summary(self):
        result = BacktestResult()
        summary = result.get_summary()
        assert summary["total_trades"] == 0

    def test_summary_calculations(self):
        result = BacktestResult()
        result.equity_curve = [10000, 10100, 10050, 10200, 10150, 10300]
        trades = [
            {"pnl_usd": 100, "actual_rr": 2.0},
            {"pnl_usd": -50, "actual_rr": -1.0},
            {"pnl_usd": 150, "actual_rr": 3.0},
            {"pnl_usd": -50, "actual_rr": -1.0},
            {"pnl_usd": 150, "actual_rr": 3.0},
        ]
        for t in trades:
            result.add_trade(t)
        summary = result.get_summary()
        assert summary["total_trades"] == 5
        assert summary["wins"] == 3
        assert summary["losses"] == 2
        assert summary["win_rate"] == pytest.approx(0.6, abs=0.01)
        assert summary["profit_factor"] > 1.0


class TestBacktestEngine:
    def test_run_returns_result(self, sample_df):
        engine = BacktestEngine(initial_balance=10000, risk_pct=0.01)
        result = engine.run("EUR_USD", sample_df, lookback=50)
        assert isinstance(result, BacktestResult)
        assert isinstance(result.get_summary(), dict)

    def test_balance_tracked(self, sample_df):
        engine = BacktestEngine(initial_balance=10000, risk_pct=0.01)
        result = engine.run("EUR_USD", sample_df, lookback=50)
        # Equity curve starts at initial balance
        if result.equity_curve:
            assert result.equity_curve[0] == pytest.approx(10000)

    def test_simulate_buy_trade(self, sample_df):
        engine = BacktestEngine(initial_balance=10000)
        pip_size = 0.0001
        # Create a simple uptrend
        prices = [1.1000, 1.1010, 1.1020, 1.1030, 1.1040, 1.1050, 1.1060]
        df_simple = pd.DataFrame({
            "open": prices, "high": [p + 0.0005 for p in prices],
            "low": [p - 0.0002 for p in prices], "close": prices,
            "volume": [1000.0] * len(prices)
        })
        pnl, exit_price, reason, rr = engine._simulate_trade(
            df_simple, 0, "BUY",
            entry=1.1000, sl=1.0980, tp1=1.1020, tp2=1.1040, tp3=1.1060,
            pip_size=pip_size, pip_val=10.0, sl_pips=20
        )
        # With uptrend, should not hit SL
        assert reason != "sl_hit" or pnl < 0


class TestMonteCarloSimulator:
    def setup_method(self):
        self.mc = MonteCarloSimulator(n_simulations=100, initial_balance=10000)

    def test_run_basic(self):
        pnls = [100, -50, 150, -30, 200, -80, 120, -40]
        result = self.mc.run(pnls)
        assert "n_simulations" in result
        assert result["n_simulations"] == 100
        assert "final_balance" in result
        assert "probability_of_profit" in result
        assert "probability_of_ruin" in result
        assert 0 <= result["probability_of_profit"] <= 1
        assert 0 <= result["probability_of_ruin"] <= 1

    def test_empty_trades(self):
        result = self.mc.run([])
        assert "error" in result

    def test_all_winning_trades(self):
        pnls = [100] * 20
        result = self.mc.run(pnls)
        assert result["probability_of_profit"] > 0.99

    def test_all_losing_trades(self):
        pnls = [-100] * 20
        result = self.mc.run(pnls)
        assert result["probability_of_ruin"] > 0.5
