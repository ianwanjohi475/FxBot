"""
Volume indicators implemented in pure pandas/numpy (no ta-lib dependency).
All methods are static and operate on standard OHLCV DataFrames or Series.
"""

import numpy as np
import pandas as pd


class VolumeIndicators:
    """Collection of volume-based technical indicators."""

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """
        On Balance Volume.

        OBV[i] = OBV[i-1] + volume  if close > prev_close
               = OBV[i-1] - volume  if close < prev_close
               = OBV[i-1]           if close == prev_close

        Returns
        -------
        pd.Series
        """
        direction = np.sign(close.diff()).fillna(0)
        obv = (direction * volume).cumsum()
        return obv.rename("obv")

    @staticmethod
    def vwap(df: pd.DataFrame) -> pd.Series:
        """
        Volume Weighted Average Price with daily reset.

        Groups by calendar date, computes cumulative(TP * volume) / cumulative(volume)
        within each day independently.

        Requires columns: high, low, close, volume and a DatetimeIndex.

        Returns
        -------
        pd.Series
        """
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        tp_vol = typical_price * df["volume"]

        # Use the date component of the index for grouping
        if isinstance(df.index, pd.DatetimeIndex):
            date_key = df.index.date
        else:
            # Fallback: treat everything as one session
            date_key = np.zeros(len(df), dtype=int)

        date_series = pd.Series(date_key, index=df.index)

        cum_tp_vol = tp_vol.groupby(date_series).cumsum()
        cum_vol = df["volume"].groupby(date_series).cumsum()

        vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
        return vwap.rename("vwap")

    @staticmethod
    def chaikin_money_flow(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Chaikin Money Flow.

        Money Flow Multiplier = ((close - low) - (high - close)) / (high - low)
        Money Flow Volume     = MFM * volume
        CMF                   = sum(MFV, period) / sum(volume, period)

        Returns
        -------
        pd.Series in [-1, 1]
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        volume = df["volume"]

        hl_range = (high - low).replace(0, np.nan)
        mfm = ((close - low) - (high - close)) / hl_range
        mfv = mfm * volume

        cmf = mfv.rolling(window=period).sum() / volume.rolling(window=period).sum()
        return cmf.rename("cmf")

    @staticmethod
    def mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Money Flow Index — RSI applied to typical-price * volume flow.

        Typical Price   = (high + low + close) / 3
        Raw Money Flow  = Typical Price * volume
        Positive MF     = sum(RMF where TP > prev_TP, period)
        Negative MF     = sum(RMF where TP <= prev_TP, period)
        MFI             = 100 - 100 / (1 + Positive_MF / Negative_MF)

        Returns
        -------
        pd.Series in [0, 100]
        """
        tp = (df["high"] + df["low"] + df["close"]) / 3
        raw_mf = tp * df["volume"]

        prev_tp = tp.shift(1)
        positive_mf = raw_mf.where(tp > prev_tp, 0.0)
        negative_mf = raw_mf.where(tp <= prev_tp, 0.0)

        pos_sum = positive_mf.rolling(window=period).sum()
        neg_sum = negative_mf.rolling(window=period).sum()

        mfr = pos_sum / neg_sum.replace(0, np.nan)
        mfi = 100 - (100 / (1 + mfr))
        return mfi.rename("mfi")

    @staticmethod
    def volume_profile(df: pd.DataFrame, num_levels: int = 20) -> dict:
        """
        Volume Profile: distributes traded volume across a fixed number of price levels.

        Point of Control (POC): price level with the highest accumulated volume.
        High Volume Nodes (HVN): levels with volume above the mean level volume.

        Returns
        -------
        dict with:
            'poc'  : float — price of the point of control
            'hvn'  : list of float — high-volume-node price levels
            'levels' : dict { price_level: volume }
        """
        price_min = df["low"].min()
        price_max = df["high"].max()

        if price_min == price_max or num_levels < 1:
            mid = (price_min + price_max) / 2
            return {"poc": mid, "hvn": [mid], "levels": {mid: df["volume"].sum()}}

        bins = np.linspace(price_min, price_max, num_levels + 1)
        level_prices = (bins[:-1] + bins[1:]) / 2  # midpoint of each bin
        level_volume = np.zeros(num_levels)

        typical_price = (df["high"] + df["low"] + df["close"]) / 3

        for idx in range(len(df)):
            tp = typical_price.iloc[idx]
            vol = df["volume"].iloc[idx]
            # Find which bin this candle's typical price falls into
            bin_idx = int(np.searchsorted(bins[1:], tp, side="left"))
            bin_idx = min(bin_idx, num_levels - 1)
            level_volume[bin_idx] += vol

        poc_idx = int(np.argmax(level_volume))
        poc = float(level_prices[poc_idx])

        mean_vol = np.mean(level_volume[level_volume > 0]) if np.any(level_volume > 0) else 0
        hvn = [float(level_prices[i]) for i in range(num_levels) if level_volume[i] > mean_vol]

        levels = {float(level_prices[i]): float(level_volume[i]) for i in range(num_levels)}

        return {"poc": poc, "hvn": hvn, "levels": levels}

    @staticmethod
    def volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
        """
        Simple Moving Average of volume.

        Returns
        -------
        pd.Series
        """
        return volume.rolling(window=period).mean().rename("volume_sma")

    @staticmethod
    def detect_volume_spike(
        volume: pd.Series, period: int = 20, threshold: float = 2.0
    ) -> pd.Series:
        """
        Detect abnormally high volume relative to its recent average.

        A spike is flagged when:  volume > threshold * SMA(volume, period)

        Returns
        -------
        pd.Series of bool: True = spike
        """
        avg_vol = VolumeIndicators.volume_sma(volume, period)
        spike = volume > threshold * avg_vol
        return spike.rename("volume_spike")
