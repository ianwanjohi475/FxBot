"""Tests for confluence scoring."""
import pytest
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring.confluence_engine import ConfluenceEngine
from strategies import TradeSignal


@pytest.fixture
def sample_df():
    np.random.seed(42)
    n = 250
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0005)
    high = close + np.abs(np.random.randn(n) * 0.0003)
    low = close - np.abs(np.random.randn(n) * 0.0003)
    open_ = close + np.random.randn(n) * 0.0002
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": np.ones(n) * 5000
    }, index=idx)


@pytest.fixture
def signal():
    return TradeSignal(
        pair="EUR_USD",
        direction="BUY",
        strategy_name="price_action",
        timeframe="H1",
        entry_price=1.1050,
        sl_price=1.1000,
        tp1_price=1.1100,
        tp2_price=1.1150,
        tp3_price=1.1200,
        pattern_detected="hammer",
        smc_concept="bullish_bos",
    )


class TestConfluenceEngine:
    def setup_method(self):
        self.engine = ConfluenceEngine(min_score=65.0)

    def test_score_returns_0_to_100(self, signal, sample_df):
        data = {"H1": sample_df, "H4": sample_df, "D1": sample_df}
        context = {"session": "london", "news_risk_score": 0}
        score = self.engine.score_signal(signal, data, context)
        assert 0 <= score <= 100

    def test_pattern_adds_score(self, signal, sample_df):
        data = {"H1": sample_df}
        context = {"session": "london", "news_risk_score": 0}

        signal_with_pattern = TradeSignal(
            pair="EUR_USD", direction="BUY", strategy_name="test",
            timeframe="H1", entry_price=1.1, sl_price=1.09,
            tp1_price=1.11, tp2_price=1.12, tp3_price=1.13,
            pattern_detected="hammer",
        )
        signal_no_pattern = TradeSignal(
            pair="EUR_USD", direction="BUY", strategy_name="test",
            timeframe="H1", entry_price=1.1, sl_price=1.09,
            tp1_price=1.11, tp2_price=1.12, tp3_price=1.13,
        )
        score_with = self.engine.score_signal(signal_with_pattern, data, context)
        score_without = self.engine.score_signal(signal_no_pattern, data, context)
        assert score_with >= score_without

    def test_news_clear_adds_score(self, signal, sample_df):
        data = {"H1": sample_df}
        context_clear = {"session": "london", "news_risk_score": 0}
        context_risky = {"session": "london", "news_risk_score": 5}
        score_clear = self.engine.score_signal(signal, data, context_clear)
        # Reset score
        signal.confluence_score = 0
        score_risky = self.engine.score_signal(signal, data, context_risky)
        assert score_clear >= score_risky

    def test_is_tradeable(self):
        assert self.engine.is_tradeable(70) is True
        assert self.engine.is_tradeable(64) is False
        assert self.engine.is_tradeable(65) is True

    def test_update_weights(self):
        self.engine.update_weights({"trend_alignment": 25, "pattern": 10})
        assert self.engine.weights["trend_alignment"] == 25
        assert self.engine.weights["pattern"] == 10

    def test_score_breakdown_in_metadata(self, signal, sample_df):
        data = {"H1": sample_df}
        context = {"session": "london", "news_risk_score": 0}
        self.engine.score_signal(signal, data, context)
        assert "score_breakdown" in signal.metadata
        bd = signal.metadata["score_breakdown"]
        assert "trend_alignment" in bd
        assert "pattern" in bd


class TestTradeSignal:
    def test_rr_ratio(self):
        signal = TradeSignal(
            pair="EUR_USD", direction="BUY", strategy_name="test",
            timeframe="H1", entry_price=1.1000, sl_price=1.0950,
            tp1_price=1.1050, tp2_price=1.1100, tp3_price=1.1150,
        )
        assert signal.rr_ratio() == pytest.approx(1.0, abs=0.01)

    def test_to_dict(self):
        signal = TradeSignal(
            pair="EUR_USD", direction="BUY", strategy_name="test",
            timeframe="H1", entry_price=1.1, sl_price=1.09,
            tp1_price=1.11, tp2_price=1.12, tp3_price=1.13,
        )
        d = signal.to_dict()
        assert d["pair"] == "EUR_USD"
        assert d["direction"] == "BUY"
