"""
Candlestick pattern detection using pure pandas/numpy.

All pattern methods accept a pd.DataFrame with columns: open, high, low, close
and return a pd.Series of signals: 1=bullish, -1=bearish, 0=neutral.
"""

import numpy as np
import pandas as pd
from typing import Dict


class CandlestickPatterns:
    """Detect single, double, and triple candlestick patterns."""

    # ------------------------------------------------------------------ #
    # Helper methods                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _body(df: pd.DataFrame) -> pd.Series:
        """Absolute body size (|close - open|)."""
        return (df["close"] - df["open"]).abs()

    @staticmethod
    def _upper_wick(df: pd.DataFrame) -> pd.Series:
        """Upper wick length."""
        return df["high"] - df[["open", "close"]].max(axis=1)

    @staticmethod
    def _lower_wick(df: pd.DataFrame) -> pd.Series:
        """Lower wick length."""
        return df[["open", "close"]].min(axis=1) - df["low"]

    @staticmethod
    def _is_bullish(df: pd.DataFrame) -> pd.Series:
        """True where close > open."""
        return df["close"] > df["open"]

    @staticmethod
    def _candle_range(df: pd.DataFrame) -> pd.Series:
        """Full candle range (high - low)."""
        return df["high"] - df["low"]

    @staticmethod
    def _avg_body(df: pd.DataFrame, period: int = 10) -> pd.Series:
        """Rolling mean of absolute body sizes."""
        return CandlestickPatterns._body(df).rolling(period).mean()

    # ------------------------------------------------------------------ #
    # Single-candle patterns                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def doji(df: pd.DataFrame, threshold: float = 0.1) -> pd.Series:
        """
        Doji: body is less than *threshold* fraction of the full candle range.
        Returns 0 (neutral) everywhere a doji is found; 1/−1 elsewhere are 0.
        Convention: doji by itself is neutral.
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        ratio = body / rng
        signal = pd.Series(0, index=df.index, dtype=int)
        return signal.where(ratio < threshold, 0)

    @staticmethod
    def gravestone_doji(df: pd.DataFrame) -> pd.Series:
        """
        Gravestone doji: open ≈ close ≈ low, long upper wick.
        Bearish reversal signal (-1).
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        lower = CandlestickPatterns._lower_wick(df)
        upper = CandlestickPatterns._upper_wick(df)

        is_doji = body / rng < 0.1
        no_lower = lower / rng < 0.05
        long_upper = upper / rng > 0.6

        mask = is_doji & no_lower & long_upper
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    @staticmethod
    def dragonfly_doji(df: pd.DataFrame) -> pd.Series:
        """
        Dragonfly doji: open ≈ close ≈ high, long lower wick.
        Bullish reversal signal (1).
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        lower = CandlestickPatterns._lower_wick(df)
        upper = CandlestickPatterns._upper_wick(df)

        is_doji = body / rng < 0.1
        no_upper = upper / rng < 0.05
        long_lower = lower / rng > 0.6

        mask = is_doji & no_upper & long_lower
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def long_legged_doji(df: pd.DataFrame) -> pd.Series:
        """
        Long-legged doji: tiny body, both wicks long (each > 30% of range).
        Neutral signal (0) – indecision.
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        lower = CandlestickPatterns._lower_wick(df)
        upper = CandlestickPatterns._upper_wick(df)

        is_doji = body / rng < 0.1
        both_long = (lower / rng > 0.3) & (upper / rng > 0.3)

        mask = is_doji & both_long
        return pd.Series(np.where(mask, 0, 0), index=df.index, dtype=int)

    @staticmethod
    def hammer(df: pd.DataFrame) -> pd.Series:
        """
        Hammer: small body at the TOP of the candle, lower wick >= 2× body,
        minimal upper wick.  Bullish reversal (1).
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        lower = CandlestickPatterns._lower_wick(df)
        upper = CandlestickPatterns._upper_wick(df)
        avg = CandlestickPatterns._avg_body(df)

        small_body = body < avg * 0.6
        long_lower = lower >= body * 2
        small_upper = upper <= body * 0.3
        # body should be in the upper part of the range
        body_in_upper = (df[["open", "close"]].min(axis=1) - df["low"]) / rng > 0.5

        mask = small_body & long_lower & small_upper & body_in_upper
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def inverted_hammer(df: pd.DataFrame) -> pd.Series:
        """
        Inverted hammer: small body at the BOTTOM, upper wick >= 2× body.
        Bullish potential (1).
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        upper = CandlestickPatterns._upper_wick(df)
        lower = CandlestickPatterns._lower_wick(df)
        avg = CandlestickPatterns._avg_body(df)

        small_body = body < avg * 0.6
        long_upper = upper >= body * 2
        small_lower = lower <= body * 0.3
        body_in_lower = (df["high"] - df[["open", "close"]].max(axis=1)) / rng > 0.5

        mask = small_body & long_upper & small_lower & body_in_lower
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def shooting_star(df: pd.DataFrame) -> pd.Series:
        """
        Shooting star: same shape as inverted hammer but after an uptrend.
        Bearish reversal (-1).
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        upper = CandlestickPatterns._upper_wick(df)
        lower = CandlestickPatterns._lower_wick(df)
        avg = CandlestickPatterns._avg_body(df)

        small_body = body < avg * 0.6
        long_upper = upper >= body * 2
        small_lower = lower <= body * 0.3
        body_in_lower = (df["high"] - df[["open", "close"]].max(axis=1)) / rng > 0.5

        # Uptrend: close has been rising over last 3 candles
        uptrend = df["close"].rolling(4).apply(
            lambda x: x[-1] > x[0], raw=True
        ).fillna(0).astype(bool)

        mask = small_body & long_upper & small_lower & body_in_lower & uptrend
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    @staticmethod
    def marubozu_bullish(df: pd.DataFrame, threshold: float = 0.95) -> pd.Series:
        """
        Bullish marubozu: bullish candle where body occupies >= threshold of range.
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        bullish = CandlestickPatterns._is_bullish(df)

        mask = bullish & (body / rng >= threshold)
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def marubozu_bearish(df: pd.DataFrame, threshold: float = 0.95) -> pd.Series:
        """
        Bearish marubozu: bearish candle where body occupies >= threshold of range.
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        bearish = ~CandlestickPatterns._is_bullish(df)

        mask = bearish & (body / rng >= threshold)
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    @staticmethod
    def spinning_top(df: pd.DataFrame) -> pd.Series:
        """
        Spinning top: small body relative to wicks, both wicks similar size.
        Neutral / indecision (0).
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        upper = CandlestickPatterns._upper_wick(df)
        lower = CandlestickPatterns._lower_wick(df)

        small_body = body / rng < 0.35
        both_wicks = (upper > body) & (lower > body)
        similar = (upper / lower.replace(0, np.nan)).between(0.5, 2.0)

        mask = small_body & both_wicks & similar
        return pd.Series(np.where(mask, 0, 0), index=df.index, dtype=int)

    # ------------------------------------------------------------------ #
    # Two-candle patterns                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def bullish_engulfing(df: pd.DataFrame) -> pd.Series:
        """Current bullish candle fully engulfs the previous bearish candle."""
        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)
        cur_open = df["open"]
        cur_close = df["close"]

        prev_bearish = prev_close < prev_open
        cur_bullish = cur_close > cur_open
        engulfs = (cur_open <= prev_close) & (cur_close >= prev_open)

        mask = prev_bearish & cur_bullish & engulfs
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def bearish_engulfing(df: pd.DataFrame) -> pd.Series:
        """Current bearish candle fully engulfs the previous bullish candle."""
        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)
        cur_open = df["open"]
        cur_close = df["close"]

        prev_bullish = prev_close > prev_open
        cur_bearish = cur_close < cur_open
        engulfs = (cur_open >= prev_close) & (cur_close <= prev_open)

        mask = prev_bullish & cur_bearish & engulfs
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    @staticmethod
    def bullish_harami(df: pd.DataFrame) -> pd.Series:
        """
        Bullish harami: large bearish candle followed by small bullish candle
        whose body is contained within the previous body.
        """
        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)
        cur_open = df["open"]
        cur_close = df["close"]
        avg = CandlestickPatterns._avg_body(df)

        prev_bearish = prev_close < prev_open
        prev_large = (prev_open - prev_close) > avg
        cur_bullish = cur_close > cur_open
        contained = (cur_open > prev_close) & (cur_close < prev_open)

        mask = prev_bearish & prev_large & cur_bullish & contained
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def bearish_harami(df: pd.DataFrame) -> pd.Series:
        """
        Bearish harami: large bullish candle followed by small bearish candle
        whose body is contained within the previous body.
        """
        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)
        cur_open = df["open"]
        cur_close = df["close"]
        avg = CandlestickPatterns._avg_body(df)

        prev_bullish = prev_close > prev_open
        prev_large = (prev_close - prev_open) > avg
        cur_bearish = cur_close < cur_open
        contained = (cur_open < prev_close) & (cur_close > prev_open)

        mask = prev_bullish & prev_large & cur_bearish & contained
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    @staticmethod
    def harami_cross(df: pd.DataFrame) -> pd.Series:
        """
        Harami cross: harami where the inner candle is a doji.
        Signal direction depends on outer candle: bullish outer → 1, bearish outer → -1.
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        inner_doji = body / rng < 0.1

        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)
        cur_open = df["open"]
        cur_close = df["close"]
        avg = CandlestickPatterns._avg_body(df)

        prev_bearish = prev_close < prev_open
        prev_bullish = prev_close > prev_open
        prev_large = CandlestickPatterns._body(df).shift(1) > avg

        contained_bear = (cur_open > prev_close) & (cur_close < prev_open)
        contained_bull = (cur_open < prev_close) & (cur_close > prev_open)

        bull_mask = prev_bearish & prev_large & inner_doji & contained_bear
        bear_mask = prev_bullish & prev_large & inner_doji & contained_bull

        signal = pd.Series(0, index=df.index, dtype=int)
        signal = signal.where(~bull_mask, 1)
        signal = signal.where(~bear_mask, -1)
        return signal

    @staticmethod
    def tweezer_tops(df: pd.DataFrame, tolerance: float = 0.001) -> pd.Series:
        """
        Tweezer tops: two candles share approximately the same high,
        first bullish, second bearish. Bearish reversal (-1).
        """
        prev_high = df["high"].shift(1)
        prev_bullish = df["close"].shift(1) > df["open"].shift(1)
        cur_bearish = df["close"] < df["open"]
        same_high = (df["high"] - prev_high).abs() / prev_high < tolerance

        mask = prev_bullish & cur_bearish & same_high
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    @staticmethod
    def tweezer_bottoms(df: pd.DataFrame, tolerance: float = 0.001) -> pd.Series:
        """
        Tweezer bottoms: two candles share approximately the same low,
        first bearish, second bullish. Bullish reversal (1).
        """
        prev_low = df["low"].shift(1)
        prev_bearish = df["close"].shift(1) < df["open"].shift(1)
        cur_bullish = df["close"] > df["open"]
        same_low = (df["low"] - prev_low).abs() / prev_low < tolerance

        mask = prev_bearish & cur_bullish & same_low
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def dark_cloud_cover(df: pd.DataFrame) -> pd.Series:
        """
        Dark cloud cover: second candle opens above previous high and closes
        below the midpoint of the previous bullish candle. Bearish (-1).
        """
        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)
        prev_high = df["high"].shift(1)
        prev_mid = (prev_open + prev_close) / 2

        prev_bullish = prev_close > prev_open
        cur_opens_above = df["open"] > prev_high
        cur_closes_below_mid = df["close"] < prev_mid
        cur_bearish = df["close"] < df["open"]

        mask = prev_bullish & cur_opens_above & cur_closes_below_mid & cur_bearish
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    @staticmethod
    def piercing_line(df: pd.DataFrame) -> pd.Series:
        """
        Piercing line: second candle opens below previous low and closes
        above the midpoint of the previous bearish candle. Bullish (1).
        """
        prev_open = df["open"].shift(1)
        prev_close = df["close"].shift(1)
        prev_low = df["low"].shift(1)
        prev_mid = (prev_open + prev_close) / 2

        prev_bearish = prev_close < prev_open
        cur_opens_below = df["open"] < prev_low
        cur_closes_above_mid = df["close"] > prev_mid
        cur_bullish = df["close"] > df["open"]

        mask = prev_bearish & cur_opens_below & cur_closes_above_mid & cur_bullish
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def inside_bar(df: pd.DataFrame) -> pd.Series:
        """
        Inside bar: current bar's high/low are within previous bar's range.
        Neutral signal (0) – potential breakout setup.
        """
        prev_high = df["high"].shift(1)
        prev_low = df["low"].shift(1)
        mask = (df["high"] <= prev_high) & (df["low"] >= prev_low)
        return pd.Series(np.where(mask, 0, 0), index=df.index, dtype=int)

    @staticmethod
    def outside_bar(df: pd.DataFrame) -> pd.Series:
        """
        Outside bar: current bar's high/low engulf previous bar's range.
        Direction follows current bar.
        """
        prev_high = df["high"].shift(1)
        prev_low = df["low"].shift(1)
        cur_bullish = df["close"] > df["open"]

        engulfs = (df["high"] > prev_high) & (df["low"] < prev_low)
        signal = pd.Series(0, index=df.index, dtype=int)
        signal = signal.where(~(engulfs & cur_bullish), 1)
        signal = signal.where(~(engulfs & ~cur_bullish), -1)
        return signal

    @staticmethod
    def pin_bar_bullish(df: pd.DataFrame) -> pd.Series:
        """
        Bullish pin bar: long lower tail, small body at top, minimal upper wick.
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        lower = CandlestickPatterns._lower_wick(df)
        upper = CandlestickPatterns._upper_wick(df)

        small_body = body / rng < 0.35
        long_lower = lower / rng > 0.6
        small_upper = upper / rng < 0.1

        mask = small_body & long_lower & small_upper
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def pin_bar_bearish(df: pd.DataFrame) -> pd.Series:
        """
        Bearish pin bar: long upper tail, small body at bottom, minimal lower wick.
        """
        body = CandlestickPatterns._body(df)
        rng = CandlestickPatterns._candle_range(df).replace(0, np.nan)
        upper = CandlestickPatterns._upper_wick(df)
        lower = CandlestickPatterns._lower_wick(df)

        small_body = body / rng < 0.35
        long_upper = upper / rng > 0.6
        small_lower = lower / rng < 0.1

        mask = small_body & long_upper & small_lower
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    # ------------------------------------------------------------------ #
    # Three-candle patterns                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def morning_star(df: pd.DataFrame) -> pd.Series:
        """
        Morning star: bearish candle, small/doji candle (gap down), bullish candle.
        Bullish reversal (1).
        """
        # Candle -2
        c2_open = df["open"].shift(2)
        c2_close = df["close"].shift(2)
        c2_bearish = c2_close < c2_open
        c2_body = (c2_open - c2_close).abs()

        # Candle -1 (middle star)
        c1_body = CandlestickPatterns._body(df).shift(1)
        avg = CandlestickPatterns._avg_body(df)
        c1_small = c1_body < avg * 0.5

        # Candle 0
        c0_open = df["open"]
        c0_close = df["close"]
        c0_bullish = c0_close > c0_open
        c0_body = (c0_close - c0_open).abs()
        # Current close should recover more than half of candle-2 body
        recovers = c0_close > c2_open - c2_body * 0.5

        mask = c2_bearish & c1_small & c0_bullish & recovers
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def evening_star(df: pd.DataFrame) -> pd.Series:
        """
        Evening star: bullish candle, small/doji candle (gap up), bearish candle.
        Bearish reversal (-1).
        """
        # Candle -2
        c2_open = df["open"].shift(2)
        c2_close = df["close"].shift(2)
        c2_bullish = c2_close > c2_open
        c2_body = (c2_close - c2_open).abs()

        # Candle -1 (middle star)
        c1_body = CandlestickPatterns._body(df).shift(1)
        avg = CandlestickPatterns._avg_body(df)
        c1_small = c1_body < avg * 0.5

        # Candle 0
        c0_open = df["open"]
        c0_close = df["close"]
        c0_bearish = c0_close < c0_open
        # Current close should erase more than half of candle-2 body
        retraces = c0_close < c2_open + c2_body * 0.5

        mask = c2_bullish & c1_small & c0_bearish & retraces
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    @staticmethod
    def three_white_soldiers(df: pd.DataFrame) -> pd.Series:
        """
        Three white soldiers: three consecutive bullish candles, each opening
        within the previous body and closing near its high. Bullish (1).
        """
        for_range = range(3)

        def _is_bull(shift):
            return df["close"].shift(shift) > df["open"].shift(shift)

        def _closes_near_high(shift, pct=0.25):
            body_top = df["close"].shift(shift)
            upper_wick = df["high"].shift(shift) - body_top
            body = CandlestickPatterns._body(df).shift(shift)
            return upper_wick <= body * pct

        def _opens_within_prev(shift):
            return (df["open"].shift(shift) > df["open"].shift(shift + 1)) & \
                   (df["open"].shift(shift) < df["close"].shift(shift + 1))

        c0_bull = _is_bull(0)
        c1_bull = _is_bull(1)
        c2_bull = _is_bull(2)

        c0_near_high = _closes_near_high(0)
        c1_near_high = _closes_near_high(1)
        c2_near_high = _closes_near_high(2)

        c0_opens_within = _opens_within_prev(0)
        c1_opens_within = _opens_within_prev(1)

        mask = (c2_bull & c1_bull & c0_bull &
                c2_near_high & c1_near_high & c0_near_high &
                c0_opens_within & c1_opens_within)
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def three_black_crows(df: pd.DataFrame) -> pd.Series:
        """
        Three black crows: three consecutive bearish candles, each opening
        within the previous body and closing near its low. Bearish (-1).
        """
        def _is_bear(shift):
            return df["close"].shift(shift) < df["open"].shift(shift)

        def _closes_near_low(shift, pct=0.25):
            body_bot = df["close"].shift(shift)
            lower_wick = body_bot - df["low"].shift(shift)
            body = CandlestickPatterns._body(df).shift(shift)
            return lower_wick <= body * pct

        def _opens_within_prev(shift):
            return (df["open"].shift(shift) < df["open"].shift(shift + 1)) & \
                   (df["open"].shift(shift) > df["close"].shift(shift + 1))

        c0_bear = _is_bear(0)
        c1_bear = _is_bear(1)
        c2_bear = _is_bear(2)

        c0_near_low = _closes_near_low(0)
        c1_near_low = _closes_near_low(1)
        c2_near_low = _closes_near_low(2)

        c0_opens_within = _opens_within_prev(0)
        c1_opens_within = _opens_within_prev(1)

        mask = (c2_bear & c1_bear & c0_bear &
                c2_near_low & c1_near_low & c0_near_low &
                c0_opens_within & c1_opens_within)
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    @staticmethod
    def abandoned_baby_bullish(df: pd.DataFrame) -> pd.Series:
        """
        Abandoned baby bullish: bearish candle, doji that gaps below, bullish candle
        that gaps above the doji. Bullish (1).
        """
        # Candle -2 bearish
        c2_bearish = df["close"].shift(2) < df["open"].shift(2)

        # Candle -1 is doji with gap below candle -2
        body1 = CandlestickPatterns._body(df).shift(1)
        rng1 = CandlestickPatterns._candle_range(df).shift(1).replace(0, np.nan)
        is_doji1 = body1 / rng1 < 0.1
        gap_below = df["high"].shift(1) < df["low"].shift(2)

        # Candle 0 is bullish with gap above doji
        c0_bullish = df["close"] > df["open"]
        gap_above = df["low"] > df["high"].shift(1)

        mask = c2_bearish & is_doji1 & gap_below & c0_bullish & gap_above
        return pd.Series(np.where(mask, 1, 0), index=df.index, dtype=int)

    @staticmethod
    def abandoned_baby_bearish(df: pd.DataFrame) -> pd.Series:
        """
        Abandoned baby bearish: bullish candle, doji that gaps above, bearish candle
        that gaps below the doji. Bearish (-1).
        """
        # Candle -2 bullish
        c2_bullish = df["close"].shift(2) > df["open"].shift(2)

        # Candle -1 is doji with gap above candle -2
        body1 = CandlestickPatterns._body(df).shift(1)
        rng1 = CandlestickPatterns._candle_range(df).shift(1).replace(0, np.nan)
        is_doji1 = body1 / rng1 < 0.1
        gap_above = df["low"].shift(1) > df["high"].shift(2)

        # Candle 0 is bearish with gap below doji
        c0_bearish = df["close"] < df["open"]
        gap_below = df["high"] < df["low"].shift(1)

        mask = c2_bullish & is_doji1 & gap_above & c0_bearish & gap_below
        return pd.Series(np.where(mask, -1, 0), index=df.index, dtype=int)

    # ------------------------------------------------------------------ #
    # Aggregate methods                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def detect_all(df: pd.DataFrame) -> Dict[str, pd.Series]:
        """Run all patterns and return a dict of {pattern_name: signal_series}."""
        cp = CandlestickPatterns
        return {
            "doji": cp.doji(df),
            "gravestone_doji": cp.gravestone_doji(df),
            "dragonfly_doji": cp.dragonfly_doji(df),
            "long_legged_doji": cp.long_legged_doji(df),
            "hammer": cp.hammer(df),
            "inverted_hammer": cp.inverted_hammer(df),
            "shooting_star": cp.shooting_star(df),
            "bullish_engulfing": cp.bullish_engulfing(df),
            "bearish_engulfing": cp.bearish_engulfing(df),
            "morning_star": cp.morning_star(df),
            "evening_star": cp.evening_star(df),
            "bullish_harami": cp.bullish_harami(df),
            "bearish_harami": cp.bearish_harami(df),
            "harami_cross": cp.harami_cross(df),
            "marubozu_bullish": cp.marubozu_bullish(df),
            "marubozu_bearish": cp.marubozu_bearish(df),
            "three_white_soldiers": cp.three_white_soldiers(df),
            "three_black_crows": cp.three_black_crows(df),
            "pin_bar_bullish": cp.pin_bar_bullish(df),
            "pin_bar_bearish": cp.pin_bar_bearish(df),
            "inside_bar": cp.inside_bar(df),
            "outside_bar": cp.outside_bar(df),
            "tweezer_tops": cp.tweezer_tops(df),
            "tweezer_bottoms": cp.tweezer_bottoms(df),
            "dark_cloud_cover": cp.dark_cloud_cover(df),
            "piercing_line": cp.piercing_line(df),
            "spinning_top": cp.spinning_top(df),
            "abandoned_baby_bullish": cp.abandoned_baby_bullish(df),
            "abandoned_baby_bearish": cp.abandoned_baby_bearish(df),
        }

    @staticmethod
    def get_strongest_signal(df: pd.DataFrame) -> dict:
        """
        Return the strongest signal at the last bar.

        Strength is measured by how many independent patterns agree,
        weighted by pattern type (3-bar patterns count double).

        Returns dict with keys: name, direction, count, patterns.
        """
        all_patterns = CandlestickPatterns.detect_all(df)
        three_bar = {"morning_star", "evening_star", "three_white_soldiers",
                     "three_black_crows", "abandoned_baby_bullish", "abandoned_baby_bearish"}

        bull_score = 0.0
        bear_score = 0.0
        bull_patterns: list = []
        bear_patterns: list = []

        for name, series in all_patterns.items():
            if len(series) == 0:
                continue
            sig = series.iloc[-1]
            weight = 2.0 if name in three_bar else 1.0
            if sig == 1:
                bull_score += weight
                bull_patterns.append(name)
            elif sig == -1:
                bear_score += weight
                bear_patterns.append(name)

        if bull_score == 0 and bear_score == 0:
            return {"name": "none", "direction": 0, "score": 0.0, "patterns": []}

        if bull_score >= bear_score:
            return {
                "name": "bullish_confluence",
                "direction": 1,
                "score": bull_score,
                "patterns": bull_patterns,
            }
        return {
            "name": "bearish_confluence",
            "direction": -1,
            "score": bear_score,
            "patterns": bear_patterns,
        }
