"""Tests for technical indicators."""
import pytest
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.trend import TrendIndicators
from indicators.momentum import MomentumIndicators
from indicators.volatility import VolatilityIndicators
from indicators.volume import VolumeIndicators
from indicators.oscillators import Oscillators


@pytest.fixture
def sample_df():
    np.random.seed(42)
    n = 300
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0005)
    high = close + np.random.uniform(0.0001, 0.0010, n)
    low = close - np.random.uniform(0.0001, 0.0010, n)
    open_ = close - np.random.randn(n) * 0.0003
    volume = np.random.randint(1000, 10000, n).astype(float)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": volume
    }, index=idx)


class TestTrendIndicators:
    def test_ema(self, sample_df):
        result = TrendIndicators.ema(sample_df["close"], 20)
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_df)
        assert not result.tail(100).isna().any()

    def test_sma(self, sample_df):
        result = TrendIndicators.sma(sample_df["close"], 20)
        assert isinstance(result, pd.Series)
        assert result.iloc[-1] > 0

    def test_macd(self, sample_df):
        result = TrendIndicators.macd(sample_df["close"])
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result
        assert len(result["macd"]) == len(sample_df)

    def test_adx(self, sample_df):
        result = TrendIndicators.adx(sample_df)
        assert "adx" in result
        assert "plus_di" in result
        assert "minus_di" in result
        adx_vals = result["adx"].dropna()
        assert (adx_vals >= 0).all()
        assert (adx_vals <= 100).all()

    def test_parabolic_sar(self, sample_df):
        result = TrendIndicators.parabolic_sar(sample_df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_df)

    def test_ichimoku(self, sample_df):
        result = TrendIndicators.ichimoku(sample_df)
        assert "tenkan_sen" in result
        assert "kijun_sen" in result
        assert "senkou_a" in result
        assert "senkou_b" in result
        assert "chikou_span" in result

    def test_supertrend(self, sample_df):
        result = TrendIndicators.supertrend(sample_df)
        assert "supertrend" in result
        assert "direction" in result
        dirs = result["direction"].dropna().unique()
        assert all(d in [-1, 1] for d in dirs)

    def test_ema_crossover(self, sample_df):
        result = TrendIndicators.detect_ema_crossover(sample_df, 9, 21)
        assert isinstance(result, pd.Series)
        assert result.isin([-1, 0, 1]).all()


class TestMomentumIndicators:
    def test_rsi(self, sample_df):
        result = MomentumIndicators.rsi(sample_df["close"], 14)
        vals = result.dropna()
        assert (vals >= 0).all()
        assert (vals <= 100).all()

    def test_stochastic(self, sample_df):
        result = MomentumIndicators.stochastic(sample_df)
        assert "k" in result
        assert "d" in result
        k_vals = result["k"].dropna()
        assert (k_vals >= 0).all()
        assert (k_vals <= 100).all()

    def test_cci(self, sample_df):
        result = MomentumIndicators.cci(sample_df)
        assert isinstance(result, pd.Series)
        assert not result.tail(100).isna().all()

    def test_williams_r(self, sample_df):
        result = MomentumIndicators.williams_r(sample_df)
        vals = result.dropna()
        assert (vals >= -100).all()
        assert (vals <= 0).all()

    def test_roc(self, sample_df):
        result = MomentumIndicators.roc(sample_df["close"])
        assert isinstance(result, pd.Series)

    def test_trix(self, sample_df):
        result = MomentumIndicators.trix(sample_df["close"])
        assert isinstance(result, pd.Series)


class TestVolatilityIndicators:
    def test_atr(self, sample_df):
        result = VolatilityIndicators.atr(sample_df)
        vals = result.dropna()
        assert (vals >= 0).all()

    def test_bollinger_bands(self, sample_df):
        result = VolatilityIndicators.bollinger_bands(sample_df["close"])
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert (result["upper"] >= result["middle"]).all()
        assert (result["middle"] >= result["lower"]).all()

    def test_keltner_channel(self, sample_df):
        result = VolatilityIndicators.keltner_channel(sample_df)
        assert "upper" in result and "lower" in result

    def test_donchian_channel(self, sample_df):
        result = VolatilityIndicators.donchian_channel(sample_df)
        assert "upper" in result and "lower" in result

    def test_historical_volatility(self, sample_df):
        result = VolatilityIndicators.historical_volatility(sample_df["close"])
        vals = result.dropna()
        assert (vals >= 0).all()


class TestVolumeIndicators:
    def test_obv(self, sample_df):
        result = VolumeIndicators.obv(sample_df["close"], sample_df["volume"])
        assert isinstance(result, pd.Series)

    def test_vwap(self, sample_df):
        result = VolumeIndicators.vwap(sample_df)
        assert isinstance(result, pd.Series)
        vals = result.dropna()
        assert (vals > 0).all()

    def test_mfi(self, sample_df):
        result = VolumeIndicators.mfi(sample_df)
        vals = result.dropna()
        assert (vals >= 0).all()
        assert (vals <= 100).all()

    def test_cmf(self, sample_df):
        result = VolumeIndicators.chaikin_money_flow(sample_df)
        vals = result.dropna()
        assert (vals >= -1).all()
        assert (vals <= 1).all()


class TestOscillators:
    def test_awesome_oscillator(self, sample_df):
        result = Oscillators.awesome_oscillator(sample_df)
        assert isinstance(result, pd.Series)

    def test_ac_oscillator(self, sample_df):
        result = Oscillators.ac_oscillator(sample_df)
        assert isinstance(result, pd.Series)

    def test_ultimate_oscillator(self, sample_df):
        result = Oscillators.ultimate_oscillator(sample_df)
        vals = result.dropna()
        assert (vals >= 0).all()
        assert (vals <= 100).all()

    def test_demarker(self, sample_df):
        result = Oscillators.demarker(sample_df)
        vals = result.dropna()
        assert (vals >= 0).all()
        assert (vals <= 1).all()
