"""
Momentum indicators implemented in pure pandas/numpy (no ta-lib dependency).
All methods are static and operate on standard OHLCV DataFrames or Series.
"""

import numpy as np
import pandas as pd


class MomentumIndicators:
    """Collection of momentum-based technical indicators."""

    @staticmethod
    def rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """
        Relative Strength Index using Wilder's smoothing (SMMA / RMA).

        Parameters
        ----------
        close  : pd.Series of closing prices
        period : look-back window (default 14)

        Returns
        -------
        pd.Series of RSI values in [0, 100]
        """
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)

        # Wilder smoothing: SMA seed then recursive formula
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.rename("rsi")

    @staticmethod
    def detect_rsi_divergence(
        close: pd.Series, rsi: pd.Series, lookback: int = 14
    ) -> pd.Series:
        """
        Detect RSI divergence over a rolling lookback window.

        Bullish divergence  (1): price makes lower low but RSI makes higher low.
        Bearish divergence (-1): price makes higher high but RSI makes lower high.

        Returns
        -------
        pd.Series: 1=bullish, -1=bearish, 0=none
        """
        result = pd.Series(0, index=close.index, dtype=int)
        close_arr = close.values
        rsi_arr = rsi.values
        n = len(close_arr)

        for i in range(lookback, n):
            window_price = close_arr[i - lookback : i + 1]
            window_rsi = rsi_arr[i - lookback : i + 1]

            # Skip if any NaN in window
            if np.any(np.isnan(window_price)) or np.any(np.isnan(window_rsi)):
                continue

            # Find the index of the previous significant low/high (exclude current)
            prev_price = window_price[:-1]
            prev_rsi = window_rsi[:-1]

            curr_price = window_price[-1]
            curr_rsi = window_rsi[-1]

            prev_low_idx = np.argmin(prev_price)
            prev_high_idx = np.argmax(prev_price)

            # Bullish: current price lower than previous low, RSI higher than RSI at prev low
            if (
                curr_price < prev_price[prev_low_idx]
                and curr_rsi > prev_rsi[prev_low_idx]
            ):
                result.iloc[i] = 1

            # Bearish: current price higher than previous high, RSI lower than RSI at prev high
            elif (
                curr_price > prev_price[prev_high_idx]
                and curr_rsi < prev_rsi[prev_high_idx]
            ):
                result.iloc[i] = -1

        return result

    @staticmethod
    def stochastic(
        df: pd.DataFrame,
        k_period: int = 14,
        d_period: int = 3,
        smooth_k: int = 3,
    ) -> dict:
        """
        Full (slow) Stochastic Oscillator.

        %K = SMA(raw_k, smooth_k)  where raw_k = (close - lowest_low) / (highest_high - lowest_low)
        %D = SMA(%K, d_period)

        Returns
        -------
        dict with 'k' and 'd' (both pd.Series, values in [0, 100])
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()

        denom = highest_high - lowest_low
        raw_k = 100 * (close - lowest_low) / denom.replace(0, np.nan)

        k = raw_k.rolling(window=smooth_k).mean()
        d = k.rolling(window=d_period).mean()

        return {"k": k.rename("stoch_k"), "d": d.rename("stoch_d")}

    @staticmethod
    def stochastic_fast(
        df: pd.DataFrame, k_period: int = 5, d_period: int = 3
    ) -> dict:
        """
        Fast Stochastic Oscillator (no smoothing of %K).

        %K = (close - lowest_low) / (highest_high - lowest_low)
        %D = SMA(%K, d_period)

        Returns
        -------
        dict with 'k' and 'd' (both pd.Series, values in [0, 100])
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()

        denom = highest_high - lowest_low
        k = 100 * (close - lowest_low) / denom.replace(0, np.nan)
        d = k.rolling(window=d_period).mean()

        return {"k": k.rename("fast_stoch_k"), "d": d.rename("fast_stoch_d")}

    @staticmethod
    def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Commodity Channel Index.

        CCI = (Typical Price - SMA(TP, period)) / (0.015 * Mean Deviation)

        Returns
        -------
        pd.Series
        """
        tp = (df["high"] + df["low"] + df["close"]) / 3
        sma_tp = tp.rolling(window=period).mean()
        mad = tp.rolling(window=period).apply(
            lambda x: np.mean(np.abs(x - x.mean())), raw=True
        )
        cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
        return cci.rename("cci")

    @staticmethod
    def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Williams %R oscillator.

        %R = (highest_high - close) / (highest_high - lowest_low) * -100

        Returns
        -------
        pd.Series in [-100, 0]
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()

        denom = highest_high - lowest_low
        wr = -100 * (highest_high - close) / denom.replace(0, np.nan)
        return wr.rename("williams_r")

    @staticmethod
    def roc(close: pd.Series, period: int = 12) -> pd.Series:
        """
        Rate of Change.

        ROC = (close - close[n]) / close[n] * 100

        Returns
        -------
        pd.Series (percentage)
        """
        return (
            (close - close.shift(period)) / close.shift(period).replace(0, np.nan) * 100
        ).rename("roc")

    @staticmethod
    def momentum(close: pd.Series, period: int = 10) -> pd.Series:
        """
        Momentum indicator: absolute difference between current and past close.

        MOM = close - close[period]

        Returns
        -------
        pd.Series
        """
        return (close - close.shift(period)).rename("momentum")

    @staticmethod
    def trix(close: pd.Series, period: int = 14) -> pd.Series:
        """
        TRIX: percentage rate of change of a triple-smoothed EMA.

        Returns
        -------
        pd.Series (percentage change)
        """
        ema1 = close.ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        ema3 = ema2.ewm(span=period, adjust=False).mean()

        trix = (ema3 - ema3.shift(1)) / ema3.shift(1).replace(0, np.nan) * 100
        return trix.rename("trix")

    @staticmethod
    def detect_overbought_oversold(
        rsi: pd.Series,
        stoch_k: pd.Series,
        cci: pd.Series,
        rsi_ob: float = 70,
        rsi_os: float = 30,
        stoch_ob: float = 80,
        stoch_os: float = 20,
        cci_ob: float = 100,
        cci_os: float = -100,
    ) -> pd.Series:
        """
        Multi-indicator confluence signal for overbought/oversold conditions.

        Returns 1 when at least 2 of 3 indicators agree on overbought,
        -1 when at least 2 of 3 agree on oversold, 0 otherwise.

        Returns
        -------
        pd.Series: 1=overbought confluence, -1=oversold confluence, 0=neutral
        """
        ob_rsi = (rsi >= rsi_ob).astype(int)
        ob_stoch = (stoch_k >= stoch_ob).astype(int)
        ob_cci = (cci >= cci_ob).astype(int)

        os_rsi = (rsi <= rsi_os).astype(int)
        os_stoch = (stoch_k <= stoch_os).astype(int)
        os_cci = (cci <= cci_os).astype(int)

        ob_count = ob_rsi + ob_stoch + ob_cci
        os_count = os_rsi + os_stoch + os_cci

        result = pd.Series(0, index=rsi.index, dtype=int)
        result[ob_count >= 2] = 1
        result[os_count >= 2] = -1
        return result
