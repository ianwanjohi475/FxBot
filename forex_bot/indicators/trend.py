"""
Trend indicators implemented in pure pandas/numpy (no ta-lib dependency).
All methods are static and operate on standard OHLCV DataFrames or Series.
"""

import numpy as np
import pandas as pd


class TrendIndicators:
    """Collection of trend-following technical indicators."""

    @staticmethod
    def ema(close: pd.Series, period: int) -> pd.Series:
        """
        Exponential Moving Average using pandas ewm with span=period.
        adjust=False gives the recursive Wilder/standard EMA formula.
        """
        return close.ewm(span=period, adjust=False).mean()

    @staticmethod
    def ema_multiple(close: pd.Series, periods: list = None) -> dict:
        """
        Compute EMA for multiple periods.

        Returns
        -------
        dict  { period: pd.Series }
        """
        if periods is None:
            periods = [9, 21, 50, 200]
        return {p: TrendIndicators.ema(close, p) for p in periods}

    @staticmethod
    def sma(close: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average."""
        return close.rolling(window=period).mean()

    @staticmethod
    def sma_multiple(close: pd.Series, periods: list = None) -> dict:
        """
        Compute SMA for multiple periods.

        Returns
        -------
        dict  { period: pd.Series }
        """
        if periods is None:
            periods = [20, 50, 200]
        return {p: TrendIndicators.sma(close, p) for p in periods}

    @staticmethod
    def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
        """
        Moving Average Convergence Divergence.

        Returns
        -------
        dict with keys 'macd', 'signal', 'histogram'
        """
        ema_fast = TrendIndicators.ema(close, fast)
        ema_slow = TrendIndicators.ema(close, slow)
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> dict:
        """
        Average Directional Index using Wilder's smoothing.

        Requires columns: high, low, close.

        Returns
        -------
        dict with keys 'adx', 'plus_di', 'minus_di'
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        prev_high = high.shift(1)
        prev_low = low.shift(1)
        prev_close = close.shift(1)

        # True Range
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Directional movement
        up_move = high - prev_high
        down_move = prev_low - low

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        plus_dm_s = pd.Series(plus_dm, index=df.index)
        minus_dm_s = pd.Series(minus_dm, index=df.index)

        # Wilder smoothing: initial sum then rolling update
        def wilder_smooth(series: pd.Series, n: int) -> pd.Series:
            result = pd.Series(np.nan, index=series.index)
            first_valid = series.first_valid_index()
            if first_valid is None:
                return result
            start_iloc = series.index.get_loc(first_valid)
            if start_iloc + n > len(series):
                return result
            initial = series.iloc[start_iloc : start_iloc + n].sum()
            result.iloc[start_iloc + n - 1] = initial
            for i in range(start_iloc + n, len(series)):
                prev_val = result.iloc[i - 1]
                result.iloc[i] = prev_val - (prev_val / n) + series.iloc[i]
            return result

        smooth_tr = wilder_smooth(tr, period)
        smooth_plus_dm = wilder_smooth(plus_dm_s, period)
        smooth_minus_dm = wilder_smooth(minus_dm_s, period)

        plus_di = 100 * smooth_plus_dm / smooth_tr
        minus_di = 100 * smooth_minus_dm / smooth_tr

        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = wilder_smooth(dx.fillna(0), period)

        return {
            "adx": adx.clip(0, 100),
            "plus_di": plus_di,
            "minus_di": minus_di,
        }

    @staticmethod
    def parabolic_sar(
        df: pd.DataFrame,
        af_start: float = 0.02,
        af_step: float = 0.02,
        af_max: float = 0.2,
    ) -> pd.Series:
        """
        Full Parabolic SAR implementation.

        Requires columns: high, low, close.

        Returns
        -------
        pd.Series of SAR values
        """
        high = df["high"].values
        low = df["low"].values
        n = len(high)

        sar = np.full(n, np.nan)
        # Initial trend: assume bullish
        trend = 1  # 1 = bullish, -1 = bearish
        ep = high[0]  # extreme point
        af = af_start
        sar[0] = low[0]

        for i in range(1, n):
            prev_sar = sar[i - 1]
            if trend == 1:
                # Bullish: SAR is below price
                sar[i] = prev_sar + af * (ep - prev_sar)
                # SAR must be <= two prior lows
                sar[i] = min(sar[i], low[i - 1])
                if i >= 2:
                    sar[i] = min(sar[i], low[i - 2])

                if low[i] < sar[i]:
                    # Reversal to bearish
                    trend = -1
                    sar[i] = ep
                    ep = low[i]
                    af = af_start
                else:
                    if high[i] > ep:
                        ep = high[i]
                        af = min(af + af_step, af_max)
            else:
                # Bearish: SAR is above price
                sar[i] = prev_sar + af * (ep - prev_sar)
                # SAR must be >= two prior highs
                sar[i] = max(sar[i], high[i - 1])
                if i >= 2:
                    sar[i] = max(sar[i], high[i - 2])

                if high[i] > sar[i]:
                    # Reversal to bullish
                    trend = 1
                    sar[i] = ep
                    ep = high[i]
                    af = af_start
                else:
                    if low[i] < ep:
                        ep = low[i]
                        af = min(af + af_step, af_max)

        return pd.Series(sar, index=df.index, name="parabolic_sar")

    @staticmethod
    def ichimoku(
        df: pd.DataFrame,
        tenkan: int = 9,
        kijun: int = 26,
        senkou_b: int = 52,
    ) -> dict:
        """
        Ichimoku Kinko Hyo cloud indicator.

        Requires columns: high, low, close.

        Returns
        -------
        dict with 'tenkan_sen', 'kijun_sen', 'senkou_a', 'senkou_b', 'chikou_span'
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        def midpoint(h: pd.Series, l: pd.Series, period: int) -> pd.Series:
            return (h.rolling(period).max() + l.rolling(period).min()) / 2

        tenkan_sen = midpoint(high, low, tenkan)
        kijun_sen = midpoint(high, low, kijun)

        # Senkou Span A: average of Tenkan and Kijun, shifted forward kijun periods
        senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun)

        # Senkou Span B: midpoint of senkou_b periods, shifted forward kijun periods
        senkou_b_line = midpoint(high, low, senkou_b).shift(kijun)

        # Chikou Span: close shifted back kijun periods
        chikou_span = close.shift(-kijun)

        return {
            "tenkan_sen": tenkan_sen,
            "kijun_sen": kijun_sen,
            "senkou_a": senkou_a,
            "senkou_b": senkou_b_line,
            "chikou_span": chikou_span,
        }

    @staticmethod
    def supertrend(
        df: pd.DataFrame, period: int = 10, multiplier: float = 3.0
    ) -> dict:
        """
        Supertrend indicator based on ATR.

        Requires columns: high, low, close.

        Returns
        -------
        dict with 'supertrend' (pd.Series) and 'direction' (pd.Series, 1=up, -1=down)
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # ATR using Wilder smoothing
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.ewm(alpha=1 / period, adjust=False).mean()

        hl2 = (high + low) / 2
        upper_band = hl2 + multiplier * atr
        lower_band = hl2 - multiplier * atr

        supertrend = pd.Series(np.nan, index=df.index)
        direction = pd.Series(np.nan, index=df.index)

        upper_arr = upper_band.values.copy()
        lower_arr = lower_band.values.copy()
        close_arr = close.values
        st_arr = np.full(len(close), np.nan)
        dir_arr = np.full(len(close), np.nan)

        # Find first non-nan index
        first_valid = 0
        while first_valid < len(close) and np.isnan(atr.values[first_valid]):
            first_valid += 1

        if first_valid < len(close):
            st_arr[first_valid] = upper_arr[first_valid]
            dir_arr[first_valid] = -1

            for i in range(first_valid + 1, len(close)):
                # Update lower band: cannot decrease
                if lower_arr[i] > lower_arr[i - 1] or close_arr[i - 1] < lower_arr[i - 1]:
                    final_lower = lower_arr[i]
                else:
                    final_lower = lower_arr[i - 1]

                # Update upper band: cannot increase
                if upper_arr[i] < upper_arr[i - 1] or close_arr[i - 1] > upper_arr[i - 1]:
                    final_upper = upper_arr[i]
                else:
                    final_upper = upper_arr[i - 1]

                upper_arr[i] = final_upper
                lower_arr[i] = final_lower

                # Determine direction
                prev_st = st_arr[i - 1]
                prev_dir = dir_arr[i - 1]

                if prev_dir == -1:
                    # Was bearish (using upper band)
                    if close_arr[i] > final_upper:
                        st_arr[i] = final_lower
                        dir_arr[i] = 1
                    else:
                        st_arr[i] = final_upper
                        dir_arr[i] = -1
                else:
                    # Was bullish (using lower band)
                    if close_arr[i] < final_lower:
                        st_arr[i] = final_upper
                        dir_arr[i] = -1
                    else:
                        st_arr[i] = final_lower
                        dir_arr[i] = 1

        return {
            "supertrend": pd.Series(st_arr, index=df.index, name="supertrend"),
            "direction": pd.Series(dir_arr, index=df.index, name="direction"),
        }

    @staticmethod
    def detect_ema_crossover(
        df: pd.DataFrame, fast_period: int = 9, slow_period: int = 21
    ) -> pd.Series:
        """
        Detect EMA crossovers.

        Returns
        -------
        pd.Series: 1=golden cross, -1=death cross, 0=no cross
        """
        close = df["close"]
        fast = TrendIndicators.ema(close, fast_period)
        slow = TrendIndicators.ema(close, slow_period)

        above = fast > slow
        cross = above.astype(int).diff()

        result = pd.Series(0, index=df.index)
        result[cross == 1] = 1   # fast crossed above slow -> golden cross
        result[cross == -1] = -1  # fast crossed below slow -> death cross
        return result

    @staticmethod
    def detect_macd_crossover(macd: pd.Series, signal: pd.Series) -> pd.Series:
        """
        Detect MACD line crossovers with the signal line.

        Returns
        -------
        pd.Series: 1=bullish cross, -1=bearish cross, 0=none
        """
        above = macd > signal
        cross = above.astype(int).diff()

        result = pd.Series(0, index=macd.index)
        result[cross == 1] = 1    # macd crossed above signal
        result[cross == -1] = -1  # macd crossed below signal
        return result
