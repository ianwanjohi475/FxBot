"""
Volatility indicators implemented in pure pandas/numpy (no ta-lib dependency).
All methods are static and operate on standard OHLCV DataFrames or Series.
"""

import numpy as np
import pandas as pd


class VolatilityIndicators:
    """Collection of volatility-based technical indicators."""

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Average True Range using Wilder's smoothing (exponential with alpha=1/period).

        True Range = max(high-low, |high-prev_close|, |low-prev_close|)

        Returns
        -------
        pd.Series
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)

        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        # Wilder smoothing equivalent: EWM with alpha = 1/period, adjust=False
        atr = tr.ewm(alpha=1 / period, adjust=False).mean()
        return atr.rename("atr")

    @staticmethod
    def bollinger_bands(
        close: pd.Series, period: int = 20, std_dev: float = 2.0
    ) -> dict:
        """
        Bollinger Bands.

        Middle  = SMA(close, period)
        Upper   = Middle + std_dev * StdDev(close, period)
        Lower   = Middle - std_dev * StdDev(close, period)
        Bandwidth = (Upper - Lower) / Middle
        %B      = (close - Lower) / (Upper - Lower)

        Returns
        -------
        dict with 'upper', 'middle', 'lower', 'bandwidth', 'percent_b'
        """
        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std(ddof=0)

        upper = middle + std_dev * std
        lower = middle - std_dev * std
        band_range = upper - lower

        bandwidth = band_range / middle.replace(0, np.nan)
        percent_b = (close - lower) / band_range.replace(0, np.nan)

        return {
            "upper": upper.rename("bb_upper"),
            "middle": middle.rename("bb_middle"),
            "lower": lower.rename("bb_lower"),
            "bandwidth": bandwidth.rename("bb_bandwidth"),
            "percent_b": percent_b.rename("bb_percent_b"),
        }

    @staticmethod
    def detect_bb_squeeze(bb: dict, threshold: float = 0.1) -> pd.Series:
        """
        Bollinger Band Squeeze: bandwidth below threshold indicates compression.

        Parameters
        ----------
        bb        : dict returned by bollinger_bands()
        threshold : bandwidth threshold below which a squeeze is declared (default 0.1)

        Returns
        -------
        pd.Series of bool: True = squeeze active
        """
        bandwidth = bb["bandwidth"]
        return (bandwidth < threshold).rename("bb_squeeze")

    @staticmethod
    def keltner_channel(
        df: pd.DataFrame,
        ema_period: int = 20,
        atr_period: int = 10,
        multiplier: float = 2.0,
    ) -> dict:
        """
        Keltner Channel.

        Middle = EMA(close, ema_period)
        Upper  = Middle + multiplier * ATR(atr_period)
        Lower  = Middle - multiplier * ATR(atr_period)

        Returns
        -------
        dict with 'upper', 'middle', 'lower'
        """
        close = df["close"]
        middle = close.ewm(span=ema_period, adjust=False).mean()
        atr = VolatilityIndicators.atr(df, atr_period)

        upper = middle + multiplier * atr
        lower = middle - multiplier * atr

        return {
            "upper": upper.rename("kc_upper"),
            "middle": middle.rename("kc_middle"),
            "lower": lower.rename("kc_lower"),
        }

    @staticmethod
    def donchian_channel(df: pd.DataFrame, period: int = 20) -> dict:
        """
        Donchian Channel.

        Upper  = rolling max of high over period
        Lower  = rolling min of low over period
        Middle = (Upper + Lower) / 2

        Returns
        -------
        dict with 'upper', 'middle', 'lower'
        """
        high = df["high"]
        low = df["low"]

        upper = high.rolling(window=period).max()
        lower = low.rolling(window=period).min()
        middle = (upper + lower) / 2

        return {
            "upper": upper.rename("dc_upper"),
            "middle": middle.rename("dc_middle"),
            "lower": lower.rename("dc_lower"),
        }

    @staticmethod
    def historical_volatility(
        close: pd.Series, period: int = 20, annualize: bool = True
    ) -> pd.Series:
        """
        Historical (realized) volatility using log returns.

        HV = StdDev(log(close/close[-1]), period)
        Annualized: HV * sqrt(252)

        Returns
        -------
        pd.Series (as a decimal, e.g. 0.15 = 15% annualized vol)
        """
        log_returns = np.log(close / close.shift(1))
        hv = log_returns.rolling(window=period).std(ddof=1)
        if annualize:
            hv = hv * np.sqrt(252)
        return hv.rename("historical_volatility")

    @staticmethod
    def detect_volatility_regime(atr: pd.Series, period: int = 20) -> pd.Series:
        """
        Classify volatility regime relative to a rolling SMA of ATR.

        'high'   : ATR > 1.5 * SMA(ATR, period)
        'low'    : ATR < 0.75 * SMA(ATR, period)
        'normal' : otherwise

        Returns
        -------
        pd.Series of str: 'high', 'normal', or 'low'
        """
        sma_atr = atr.rolling(window=period).mean()

        conditions = [
            atr > 1.5 * sma_atr,
            atr < 0.75 * sma_atr,
        ]
        choices = ["high", "low"]

        regime = pd.Series(
            np.select(conditions, choices, default="normal"),
            index=atr.index,
        )
        return regime.rename("volatility_regime")
