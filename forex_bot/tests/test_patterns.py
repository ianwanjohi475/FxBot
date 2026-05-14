"""Tests for pattern recognition."""
import pytest
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patterns.candlestick import CandlestickPatterns
from patterns.chart_patterns import ChartPatterns
from patterns.smc import SmartMoneyConcepts
from patterns.elliott_wave import ElliottWave


@pytest.fixture
def sample_df():
    np.random.seed(99)
    n = 200
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0005)
    high = close + np.abs(np.random.randn(n) * 0.0005)
    low = close - np.abs(np.random.randn(n) * 0.0005)
    open_ = close + np.random.randn(n) * 0.0002
    # Fix OHLC relationships
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": np.ones(n) * 1000
    }, index=idx)


class TestCandlestickPatterns:
    def test_doji(self, sample_df):
        result = CandlestickPatterns.doji(sample_df)
        assert isinstance(result, pd.Series)
        assert result.isin([0, 1, -1]).all()

    def test_hammer(self, sample_df):
        result = CandlestickPatterns.hammer(sample_df)
        assert isinstance(result, pd.Series)

    def test_bullish_engulfing(self, sample_df):
        result = CandlestickPatterns.bullish_engulfing(sample_df)
        assert isinstance(result, pd.Series)

    def test_bearish_engulfing(self, sample_df):
        result = CandlestickPatterns.bearish_engulfing(sample_df)
        assert isinstance(result, pd.Series)

    def test_detect_all(self, sample_df):
        result = CandlestickPatterns.detect_all(sample_df)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_pin_bar_bullish(self, sample_df):
        result = CandlestickPatterns.pin_bar_bullish(sample_df)
        assert isinstance(result, pd.Series)

    def test_inside_bar(self, sample_df):
        result = CandlestickPatterns.inside_bar(sample_df)
        assert isinstance(result, pd.Series)


class TestSmartMoneyConcepts:
    def test_detect_order_blocks(self, sample_df):
        result = SmartMoneyConcepts.detect_order_blocks(sample_df)
        assert isinstance(result, list)
        for ob in result:
            assert "type" in ob
            assert ob["type"] in ("bullish_ob", "bearish_ob")
            assert "high" in ob and "low" in ob

    def test_detect_fvg(self, sample_df):
        result = SmartMoneyConcepts.detect_fvg(sample_df)
        assert isinstance(result, list)
        for fvg in result:
            assert "type" in fvg
            assert fvg["type"] in ("bullish_fvg", "bearish_fvg")
            assert fvg["top"] >= fvg["bottom"]

    def test_detect_bos(self, sample_df):
        result = SmartMoneyConcepts.detect_bos(sample_df)
        assert isinstance(result, list)

    def test_premium_discount_zone(self, sample_df):
        result = SmartMoneyConcepts.premium_discount_zone(sample_df)
        assert "equilibrium" in result
        assert "range_high" in result
        assert "range_low" in result
        assert result["range_high"] >= result["range_low"]

    def test_ote_zone(self):
        result = SmartMoneyConcepts.ote_zone(1.1000, 1.1200, "BUY")
        assert "ote_low" in result
        assert "ote_high" in result
        assert result["ote_high"] >= result["ote_low"]
        assert result["ote_low"] < 1.1200

    def test_kill_zone_active(self):
        from datetime import datetime
        import pytz
        est = pytz.timezone("America/New_York")
        # 3am EST = London open kill zone
        dt = datetime.now(tz=pytz.utc).replace(hour=8, minute=0)  # 3am EST = 8am UTC
        result = SmartMoneyConcepts.kill_zone_active(dt)
        assert "active" in result
        assert isinstance(result["active"], bool)

    def test_analyze_all(self, sample_df):
        result = SmartMoneyConcepts.analyze_all(sample_df)
        assert isinstance(result, dict)
        assert "order_blocks" in result
        assert "fvg" in result
        assert "bos" in result


class TestElliottWave:
    def test_find_pivots(self, sample_df):
        result = ElliottWave._find_pivots(sample_df)
        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "type" in result.columns
            assert "price" in result.columns

    def test_detect_impulse_wave(self, sample_df):
        result = ElliottWave.detect_impulse_wave(sample_df)
        assert isinstance(result, list)

    def test_detect_corrective_wave(self, sample_df):
        result = ElliottWave.detect_corrective_wave(sample_df)
        assert isinstance(result, list)

    def test_get_trading_signal_no_waves(self):
        result = ElliottWave.get_trading_signal([])
        assert result["signal"] is None
